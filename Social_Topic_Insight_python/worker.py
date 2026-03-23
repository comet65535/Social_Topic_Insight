import json
import time

import pika

from core.config import settings
from core.database import db
from core.logger import logger
from modules.crawler.engine import CrawlerEngine


def build_connection() -> pika.BlockingConnection:
    logger.info(
        "[Worker] Connecting RabbitMQ host=%s port=%s vhost=%s user=%s",
        settings.RABBITMQ_HOST,
        settings.RABBITMQ_PORT,
        settings.RABBITMQ_VHOST,
        settings.RABBITMQ_USER,
    )
    credentials = pika.PlainCredentials(settings.RABBITMQ_USER, settings.RABBITMQ_PASS)
    parameters = pika.ConnectionParameters(
        host=settings.RABBITMQ_HOST,
        port=settings.RABBITMQ_PORT,
        virtual_host=settings.RABBITMQ_VHOST,
        credentials=credentials,
        heartbeat=120,
        connection_attempts=3,
        retry_delay=2,
        blocked_connection_timeout=300,
    )
    return pika.BlockingConnection(parameters)


def ensure_topology(channel: pika.adapters.blocking_connection.BlockingChannel) -> None:
    channel.exchange_declare(exchange=settings.TASK_EXCHANGE, exchange_type="direct", durable=True)
    channel.queue_declare(queue=settings.TASK_QUEUE, durable=True)
    channel.queue_bind(
        queue=settings.TASK_QUEUE,
        exchange=settings.TASK_EXCHANGE,
        routing_key=settings.TASK_ROUTING_KEY,
    )

    channel.exchange_declare(exchange=settings.CLUSTER_EXCHANGE, exchange_type="direct", durable=True)


def publish_cluster_done(channel, task_id: str) -> None:
    if not task_id:
        return

    payload = json.dumps({"taskId": task_id}, ensure_ascii=False)
    channel.basic_publish(
        exchange=settings.CLUSTER_EXCHANGE,
        routing_key=settings.CLUSTER_DONE_ROUTING_KEY,
        body=payload.encode("utf-8"),
        properties=pika.BasicProperties(
            content_type="application/json",
            delivery_mode=2,
        ),
    )


def handle_task(
    channel: pika.adapters.blocking_connection.BlockingChannel,
    method,
    properties,
    body: bytes,
) -> None:
    try:
        payload = json.loads(body.decode("utf-8"))
    except Exception as ex:
        logger.error(f"Invalid task message body: {ex}")
        channel.basic_ack(delivery_tag=method.delivery_tag)
        return

    task_id = payload.get("taskId") or payload.get("task_id")
    task_config = {
        "task_id": task_id,
        "name": payload.get("name"),
        "platforms": payload.get("platforms", []),
        "mode": payload.get("mode", "hot_list"),
        "keywords": payload.get("keywords", []),
    }

    logger.info(f"[Worker] Received task: {task_id}, mode={task_config['mode']}")

    try:
        CrawlerEngine.run(task_config)
        publish_cluster_done(channel, task_id)
        channel.basic_ack(delivery_tag=method.delivery_tag)
        logger.info(f"[Worker] Task finished and callback sent: {task_id}")
    except Exception as ex:
        logger.exception(f"[Worker] Task failed: {task_id}, error={ex}")
        CrawlerEngine.update_task_status(task_id, "failed", log=f"Worker failed: {str(ex)}")
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)


def main() -> None:
    db.connect()

    while True:
        connection = None
        try:
            connection = build_connection()
            channel = connection.channel()
            ensure_topology(channel)

            channel.basic_qos(prefetch_count=1)
            channel.basic_consume(queue=settings.TASK_QUEUE, on_message_callback=handle_task)

            logger.info(
                "[Worker] Waiting for task messages on queue=%s (exchange=%s, routing=%s)...",
                settings.TASK_QUEUE,
                settings.TASK_EXCHANGE,
                settings.TASK_ROUTING_KEY,
            )
            channel.start_consuming()
        except KeyboardInterrupt:
            logger.info("[Worker] Stopped by keyboard interrupt")
            break
        except Exception as ex:
            logger.exception(f"[Worker] RabbitMQ connection error: {ex}. Retry in 5s")
            time.sleep(5)
        finally:
            if connection and connection.is_open:
                connection.close()


if __name__ == "__main__":
    main()
