#!/usr/bin/env python3
"""
End-to-end verification script for Social Topic Insight.

Covers:
1) Task creation + duplicate-protection validation
2) MongoDB task state validation + RabbitMQ observable hints
3) cluster.done trigger + Redis cache key + hot-topics response-time checks
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from urllib.parse import quote
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass
class StepResult:
    name: str
    passed: bool
    details: str
    severity: str = "normal"  # normal | warn


@dataclass
class TestContext:
    java_base_url: str
    mongo_uri: str
    mongo_db: str
    redis_host: str
    redis_port: int
    redis_password: str
    redis_db: int
    rabbit_host: str
    rabbit_port: int
    rabbit_user: str
    rabbit_pass: str
    rabbit_vhost: str
    rabbit_http_api: str
    redis_cache_key: str
    speed_threshold_ms: float
    results: list[StepResult] = field(default_factory=list)

    def add(self, name: str, passed: bool, details: str, severity: str = "normal") -> None:
        self.results.append(StepResult(name=name, passed=passed, details=details, severity=severity))
        status = "PASS" if passed else ("WARN" if severity == "warn" else "FAIL")
        print(f"[{status}] {name}: {details}")


@dataclass
class HttpResult:
    status: Optional[int]
    elapsed_ms: float
    body_text: str
    json_body: Optional[dict[str, Any]]
    error: Optional[str] = None


def http_json(method: str, url: str, payload: Optional[dict[str, Any]] = None, timeout: int = 10) -> HttpResult:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = Request(url=url, data=data, method=method.upper(), headers=headers)
    start = time.perf_counter()

    try:
        with urlopen(request, timeout=timeout) as resp:
            body_bytes = resp.read()
            status = getattr(resp, "status", None)
    except HTTPError as e:
        status = e.code
        body_bytes = e.read()
    except URLError as e:
        elapsed_ms = (time.perf_counter() - start) * 1000
        return HttpResult(
            status=None,
            elapsed_ms=elapsed_ms,
            body_text="",
            json_body=None,
            error=f"URLError: {e}",
        )
    except Exception as e:
        elapsed_ms = (time.perf_counter() - start) * 1000
        return HttpResult(
            status=None,
            elapsed_ms=elapsed_ms,
            body_text="",
            json_body=None,
            error=f"{type(e).__name__}: {e}",
        )

    elapsed_ms = (time.perf_counter() - start) * 1000
    body_text = body_bytes.decode("utf-8", errors="replace")
    parsed = None
    try:
        parsed = json.loads(body_text) if body_text else None
    except json.JSONDecodeError:
        parsed = None

    return HttpResult(
        status=status,
        elapsed_ms=elapsed_ms,
        body_text=body_text,
        json_body=parsed if isinstance(parsed, dict) else None,
    )


def rabbit_http_json(
    base_api: str,
    method: str,
    path: str,
    user: str,
    password: str,
    payload: Optional[dict[str, Any]] = None,
    timeout: int = 8,
) -> HttpResult:
    import base64

    url = base_api.rstrip("/") + "/" + path.lstrip("/")
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"

    token = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")
    headers["Authorization"] = f"Basic {token}"

    req = Request(url=url, data=data, method=method.upper(), headers=headers)
    start = time.perf_counter()
    try:
        with urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            status = getattr(resp, "status", None)
    except HTTPError as e:
        status = e.code
        body = e.read().decode("utf-8", errors="replace")
    except Exception as e:
        elapsed_ms = (time.perf_counter() - start) * 1000
        return HttpResult(None, elapsed_ms, "", None, error=f"{type(e).__name__}: {e}")

    elapsed_ms = (time.perf_counter() - start) * 1000
    parsed = None
    try:
        parsed = json.loads(body) if body else None
    except json.JSONDecodeError:
        parsed = None
    return HttpResult(status, elapsed_ms, body, parsed if isinstance(parsed, dict) else None)


def now_iso() -> str:
    # Use explicit UTC timestamp to avoid timezone ambiguity between services.
    return datetime.now(timezone.utc).isoformat()


def body_code(body: Optional[dict[str, Any]]) -> Optional[int]:
    if not isinstance(body, dict):
        return None
    code = body.get("code")
    return code if isinstance(code, int) else None


def body_msg(body: Optional[dict[str, Any]]) -> str:
    if not isinstance(body, dict):
        return ""
    msg = body.get("msg")
    return str(msg) if msg is not None else ""


def extract_task_id(body: Optional[dict[str, Any]]) -> Optional[str]:
    if not isinstance(body, dict):
        return None
    data = body.get("data")
    if isinstance(data, dict):
        for k in ("taskId", "task_id", "id"):
            if isinstance(data.get(k), str) and data.get(k):
                return data[k]
    return None


def _redis_send(sock: socket.socket, args: list[str]) -> None:
    parts = [f"*{len(args)}\r\n".encode("utf-8")]
    for arg in args:
        encoded = arg.encode("utf-8")
        parts.append(f"${len(encoded)}\r\n".encode("utf-8"))
        parts.append(encoded + b"\r\n")
    sock.sendall(b"".join(parts))


def _redis_readline(sock: socket.socket) -> bytes:
    data = b""
    while not data.endswith(b"\r\n"):
        chunk = sock.recv(1)
        if not chunk:
            raise RuntimeError("Redis socket closed unexpectedly")
        data += chunk
    return data[:-2]


def _redis_read_reply(sock: socket.socket) -> Any:
    prefix = sock.recv(1)
    if not prefix:
        raise RuntimeError("Empty Redis reply")
    if prefix == b"+":
        return _redis_readline(sock).decode("utf-8", errors="replace")
    if prefix == b"-":
        raise RuntimeError(f"Redis error: {_redis_readline(sock).decode('utf-8', errors='replace')}")
    if prefix == b":":
        return int(_redis_readline(sock))
    if prefix == b"$":
        length = int(_redis_readline(sock))
        if length == -1:
            return None
        data = b""
        while len(data) < length + 2:
            chunk = sock.recv(length + 2 - len(data))
            if not chunk:
                raise RuntimeError("Redis bulk reply interrupted")
            data += chunk
        return data[:-2]
    if prefix == b"*":
        n = int(_redis_readline(sock))
        return [_redis_read_reply(sock) for _ in range(n)]
    raise RuntimeError(f"Unsupported Redis reply type: {prefix!r}")


def redis_exists_and_ttl(
    host: str, port: int, key: str, password: str = "", db: int = 0, timeout: int = 5
) -> tuple[bool, Optional[int]]:
    with socket.create_connection((host, port), timeout=timeout) as sock:
        if password:
            _redis_send(sock, ["AUTH", password])
            _redis_read_reply(sock)
        if db:
            _redis_send(sock, ["SELECT", str(db)])
            _redis_read_reply(sock)

        _redis_send(sock, ["EXISTS", key])
        exists_int = _redis_read_reply(sock)
        exists = bool(exists_int)

        ttl_val = None
        if exists:
            _redis_send(sock, ["TTL", key])
            ttl_val = int(_redis_read_reply(sock))

        return exists, ttl_val


def stage_1_create_and_duplicate(ctx: TestContext) -> tuple[Optional[str], str]:
    print("\n=== Stage 1: Task creation + duplicate-protection ===")
    task_name = f"qa-e2e-{int(time.time())}-{uuid.uuid4().hex[:8]}"
    task_payload = {
        "name": task_name,
        "platforms": ["weibo"],
        "mode": "hot_list",
        "keywords": [],
        "startTime": now_iso(),
        "endTime": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
    }

    tasks_url = f"{ctx.java_base_url}/api/tasks"
    first = http_json("POST", tasks_url, payload=task_payload, timeout=12)
    if first.error:
        ctx.add(
            "1.1 create task",
            False,
            f"Request error: {first.error}. url={tasks_url}",
        )
        return None, task_name

    first_ok = first.status in (200, 201) and body_code(first.json_body) == 200
    task_id = extract_task_id(first.json_body)
    first_detail = (
        f"http={first.status}, body.code={body_code(first.json_body)}, "
        f"msg={body_msg(first.json_body)!r}, elapsed={first.elapsed_ms:.1f}ms, task_id={task_id}"
    )
    ctx.add("1.1 create task", first_ok and bool(task_id), first_detail)

    if not (first_ok and task_id):
        return None, task_name

    # Immediate duplicate request (within ~1 second).
    second = http_json("POST", tasks_url, payload=task_payload, timeout=12)
    if second.error:
        ctx.add("1.2 duplicate create", False, f"Request error: {second.error}")
        return task_id, task_name

    msg2 = body_msg(second.json_body).lower()
    duplicate_blocked = (
        (second.status is not None and second.status >= 400)
        or (body_code(second.json_body) is not None and body_code(second.json_body) != 200)
        or ("duplicate" in msg2)
        or ("同类任务" in body_msg(second.json_body))
        or ("正在执行" in body_msg(second.json_body))
    )
    details = (
        f"http={second.status}, body.code={body_code(second.json_body)}, "
        f"msg={body_msg(second.json_body)!r}, elapsed={second.elapsed_ms:.1f}ms"
    )
    ctx.add("1.2 duplicate create", duplicate_blocked, details)

    if duplicate_blocked and second.status == 200 and body_code(second.json_body) and body_code(second.json_body) != 200:
        ctx.add(
            "1.2.a http semantics note",
            False,
            "Duplicate is blocked in business code, but HTTP status is still 200. "
            "Recommend returning 409/400 via @ResponseStatus or ResponseEntity.",
            severity="warn",
        )

    return task_id, task_name


def stage_2_mongo_and_rabbit(ctx: TestContext, task_id: Optional[str], task_name: str) -> None:
    print("\n=== Stage 2: MongoDB state + RabbitMQ observation ===")
    try:
        from pymongo import MongoClient
        from bson import ObjectId
    except Exception as e:
        ctx.add(
            "2.1 mongo task status",
            False,
            f"pymongo/bson not available: {type(e).__name__}: {e}. "
            f"Install with: pip install pymongo",
        )
    else:
        try:
            client = MongoClient(ctx.mongo_uri, serverSelectionTimeoutMS=5000)
            coll = client[ctx.mongo_db]["crawler_tasks"]
            doc = None
            if task_id:
                try:
                    doc = coll.find_one({"_id": ObjectId(task_id)})
                except Exception:
                    doc = coll.find_one({"_id": task_id})
            if doc is None:
                doc = coll.find_one({"name": task_name}, sort=[("create_time", -1)])

            if not doc:
                ctx.add(
                    "2.1 mongo task status",
                    False,
                    f"Task not found in MongoDB collection crawler_tasks (name={task_name}, id={task_id}).",
                )
            else:
                status = str(doc.get("status", ""))
                log_val = str(doc.get("log", ""))
                strict_ok = status in {"pending", "running"}
                if strict_ok:
                    ctx.add(
                        "2.1 mongo task status",
                        True,
                        f"status={status!r}, log={log_val!r}",
                    )
                else:
                    ctx.add(
                        "2.1 mongo task status",
                        False,
                        f"status={status!r}, log={log_val!r}. "
                        f"Expected pending/running (it may have already advanced quickly).",
                        severity="warn",
                    )
        except Exception as e:
            ctx.add("2.1 mongo task status", False, f"MongoDB query failed: {type(e).__name__}: {e}")

    print(
        "INFO 2.2: 请查看 Python Worker 终端日志，确认出现了类似 "
        "'Received task' / 'Starting Crawler Task' / 'Task finished' 的记录。"
    )

    # Optional: inspect RabbitMQ queue depth with pika (if installed).
    try:
        import pika
    except Exception:
        vhost = quote(ctx.rabbit_vhost, safe="")
        q_task = rabbit_http_json(
            ctx.rabbit_http_api,
            "GET",
            f"/queues/{vhost}/{quote('task.queue', safe='')}",
            ctx.rabbit_user,
            ctx.rabbit_pass,
        )
        q_done = rabbit_http_json(
            ctx.rabbit_http_api,
            "GET",
            f"/queues/{vhost}/{quote('cluster.done.queue', safe='')}",
            ctx.rabbit_user,
            ctx.rabbit_pass,
        )
        if q_task.error or q_done.error:
            ctx.add(
                "2.2 rabbit queue snapshot",
                False,
                "Neither pika nor RabbitMQ HTTP API queue inspection is available. "
                "Manual worker log check required.",
                severity="warn",
            )
            return

        task_messages = q_task.json_body.get("messages")
        task_consumers = q_task.json_body.get("consumers")
        done_messages = q_done.json_body.get("messages")
        done_consumers = q_done.json_body.get("consumers")
        details = (
            f"task.queue(message_count={q_task.json_body.get('messages')}, "
            f"consumers={q_task.json_body.get('consumers')}), "
            f"cluster.done.queue(message_count={q_done.json_body.get('messages')}, "
            f"consumers={q_done.json_body.get('consumers')})"
        )
        if isinstance(task_consumers, int) and task_consumers <= 0:
            ctx.add(
                "2.2 rabbit queue snapshot",
                False,
                details + " -> task.queue has no active consumer; worker may be down.",
                severity="warn",
            )
        elif isinstance(task_messages, int) and task_messages > 0:
            ctx.add(
                "2.2 rabbit queue snapshot",
                False,
                details + " -> task.queue still has backlog; verify worker throughput/logs.",
                severity="warn",
            )
        else:
            ctx.add("2.2 rabbit queue snapshot", True, details)
        return

    try:
        credentials = pika.PlainCredentials(ctx.rabbit_user, ctx.rabbit_pass)
        params = pika.ConnectionParameters(
            host=ctx.rabbit_host,
            port=ctx.rabbit_port,
            virtual_host=ctx.rabbit_vhost,
            credentials=credentials,
            heartbeat=30,
            blocked_connection_timeout=10,
            socket_timeout=5,
        )
        conn = pika.BlockingConnection(params)
        ch = conn.channel()
        q1 = ch.queue_declare(queue="task.queue", passive=True).method
        q2 = ch.queue_declare(queue="cluster.done.queue", passive=True).method
        conn.close()

        details = (
            "task.queue(message_count="
            f"{q1.message_count}, consumers={q1.consumer_count}), "
            "cluster.done.queue(message_count="
            f"{q2.message_count}, consumers={q2.consumer_count})"
        )
        if q1.consumer_count <= 0:
            ctx.add(
                "2.2 rabbit queue snapshot",
                False,
                details + " -> task.queue has no active consumer; worker may be down.",
                severity="warn",
            )
        elif q1.message_count > 0:
            ctx.add(
                "2.2 rabbit queue snapshot",
                False,
                details + " -> task.queue still has backlog; verify worker throughput/logs.",
                severity="warn",
            )
        else:
            ctx.add("2.2 rabbit queue snapshot", True, details)
    except Exception as e:
        ctx.add(
            "2.2 rabbit queue snapshot",
            False,
            f"RabbitMQ inspection failed: {type(e).__name__}: {e}. Manual worker log check remains required.",
            severity="warn",
        )


def publish_cluster_done(ctx: TestContext, task_id: str) -> bool:
    try:
        import pika
    except Exception:
        vhost = quote(ctx.rabbit_vhost, safe="")
        payload = {
            "properties": {},
            "routing_key": "cluster.done",
            "payload": json.dumps({"taskId": task_id}, ensure_ascii=False),
            "payload_encoding": "string",
        }
        r = rabbit_http_json(
            base_api=ctx.rabbit_http_api,
            method="POST",
            path=f"/exchanges/{vhost}/{quote('cluster.exchange', safe='')}/publish",
            user=ctx.rabbit_user,
            password=ctx.rabbit_pass,
            payload=payload,
        )
        if r.error or not r.json_body:
            return False
        return bool(r.json_body.get("routed", False))

    try:
        credentials = pika.PlainCredentials(ctx.rabbit_user, ctx.rabbit_pass)
        params = pika.ConnectionParameters(
            host=ctx.rabbit_host,
            port=ctx.rabbit_port,
            virtual_host=ctx.rabbit_vhost,
            credentials=credentials,
            heartbeat=30,
            blocked_connection_timeout=10,
            socket_timeout=5,
        )
        conn = pika.BlockingConnection(params)
        ch = conn.channel()
        payload = json.dumps({"taskId": task_id}, ensure_ascii=False).encode("utf-8")
        ch.basic_publish(
            exchange="cluster.exchange",
            routing_key="cluster.done",
            body=payload,
            properties=pika.BasicProperties(content_type="application/json", delivery_mode=2),
        )
        conn.close()
        return True
    except Exception:
        return False


def stage_3_done_redis_perf(ctx: TestContext, task_id: Optional[str]) -> None:
    print("\n=== Stage 3: cluster.done + Redis + API response-time ===")
    if task_id:
        sent = publish_cluster_done(ctx, task_id)
        if sent:
            ctx.add(
                "3.1 publish cluster.done",
                True,
                f"Published synthetic cluster.done for taskId={task_id}.",
            )
        else:
            ctx.add(
                "3.1 publish cluster.done",
                False,
                "Could not publish cluster.done automatically (likely pika/RabbitMQ connectivity issue). "
                "Proceeding with passive Redis checks.",
                severity="warn",
            )
    else:
        ctx.add(
            "3.1 publish cluster.done",
            False,
            "No taskId from stage 1; skipped synthetic callback publish.",
            severity="warn",
        )

    # Wait briefly for async consumer + cache warm.
    cache_ready = False
    cache_ttl = None
    for _ in range(30):
        try:
            exists, ttl = redis_exists_and_ttl(
                host=ctx.redis_host,
                port=ctx.redis_port,
                key=ctx.redis_cache_key,
                password=ctx.redis_password,
                db=ctx.redis_db,
                timeout=4,
            )
            if exists:
                cache_ready = True
                cache_ttl = ttl
                break
        except Exception:
            pass
        time.sleep(1.0)

    ctx.add(
        "3.2 redis cache key",
        cache_ready,
        f"key={ctx.redis_cache_key!r}, exists={cache_ready}, ttl={cache_ttl}",
    )

    hot_url = f"{ctx.java_base_url}/api/analysis/hot-topics"
    elapsed = []
    valid_payloads = 0

    for i in range(3):
        r = http_json("GET", hot_url, payload=None, timeout=10)
        elapsed.append(r.elapsed_ms)
        is_valid = r.error is None and r.status in (200, 201) and body_code(r.json_body) == 200
        if is_valid:
            valid_payloads += 1
        print(
            f"GET hot-topics #{i + 1}: http={r.status}, body.code={body_code(r.json_body)}, "
            f"elapsed={r.elapsed_ms:.1f}ms, msg={body_msg(r.json_body)!r}, error={r.error}"
        )
        time.sleep(0.2)

    speed_ok = len(elapsed) == 3 and elapsed[1] <= ctx.speed_threshold_ms and elapsed[2] <= ctx.speed_threshold_ms
    ctx.add(
        "3.3 hot-topics api validity",
        valid_payloads == 3,
        f"valid_responses={valid_payloads}/3",
    )
    ctx.add(
        "3.4 hot-topics cache-hit speed",
        speed_ok,
        f"threshold={ctx.speed_threshold_ms:.1f}ms, observed=[{elapsed[0]:.1f}, {elapsed[1]:.1f}, {elapsed[2]:.1f}]ms",
    )


def print_diagnostics(ctx: TestContext) -> None:
    print("\n=== Diagnostics & Suggested Fixes ===")
    failed = [r for r in ctx.results if not r.passed and r.severity != "warn"]
    warned = [r for r in ctx.results if not r.passed and r.severity == "warn"]

    if not failed and not warned:
        print("All checks passed cleanly.")
        return

    if any(r.name.startswith("1.1") for r in failed):
        print(
            "- Stage 1 create failed: verify Spring service is listening on "
            f"{ctx.java_base_url} and `POST /api/tasks` contract matches TaskCreateDTO."
        )
    if any(r.name.startswith("1.2") for r in failed):
        print(
            "- Duplicate request was not blocked: check Redisson config, lock key composition "
            "(mode + task name), and whether lock is unintentionally released too early."
        )
    if any("http semantics note" in r.name for r in warned):
        print(
            "- Business error currently returns HTTP 200 with body.code=400. "
            "Consider returning proper HTTP 4xx/5xx using ResponseEntity or @ResponseStatus."
        )
    if any(r.name.startswith("2.1") for r in failed):
        print(
            "- Mongo verification failed: check `spring.data.mongodb.uri`, collection name `crawler_tasks`, "
            "and whether task persistence occurs before MQ dispatch."
        )
    if any(r.name.startswith("2.2") for r in failed):
        print(
            "- Rabbit observable checks failed: confirm RabbitMQ credentials/vhost and that worker binds `task.queue`."
        )
    if any(r.name.startswith("2.2") for r in warned):
        print(
            "- Rabbit queue warning: `task.queue` has backlog or no consumer. "
            "Check whether `python worker.py` is running and successfully connected to RabbitMQ."
        )
    if any(r.name.startswith("3.1") for r in failed):
        print(
            "- Synthetic cluster.done publish failed: verify exchange `cluster.exchange` and routing key `cluster.done`."
        )
    if any(r.name.startswith("3.2") for r in failed):
        print(
            "- Redis key missing: likely `LlmSummaryService.onClusterDone` not executed or failed before "
            "`refreshHotTopicsCache()`. Check Spring listener logs and LLM call exceptions."
        )
    if any(r.name.startswith("3.4") for r in failed):
        print(
            "- Cache speed target not met: validate Redis hit path in AnalysisController, JVM serialization overhead, "
            "and local network/host load."
        )


def build_context_from_args() -> TestContext:
    parser = argparse.ArgumentParser(description="Run E2E verification for Social Topic Insight")
    parser.add_argument("--java-base-url", default=os.getenv("JAVA_BASE_URL", "http://localhost:8080"))
    parser.add_argument("--mongo-uri", default=os.getenv("MONGO_URI", "mongodb://localhost:27017"))
    parser.add_argument("--mongo-db", default=os.getenv("MONGO_DB", "social_media_analysis"))
    parser.add_argument("--redis-host", default=os.getenv("REDIS_HOST", "localhost"))
    parser.add_argument("--redis-port", type=int, default=int(os.getenv("REDIS_PORT", "6379")))
    parser.add_argument("--redis-password", default=os.getenv("REDIS_PASSWORD", ""))
    parser.add_argument("--redis-db", type=int, default=int(os.getenv("REDIS_DB", "0")))
    parser.add_argument("--rabbit-host", default=os.getenv("RABBITMQ_HOST", "localhost"))
    parser.add_argument("--rabbit-port", type=int, default=int(os.getenv("RABBITMQ_PORT", "5672")))
    parser.add_argument("--rabbit-user", default=os.getenv("RABBITMQ_USERNAME", "guest"))
    parser.add_argument("--rabbit-pass", default=os.getenv("RABBITMQ_PASSWORD", "guest"))
    parser.add_argument("--rabbit-vhost", default=os.getenv("RABBITMQ_VHOST", "/"))
    parser.add_argument("--rabbit-http-api", default=os.getenv("RABBITMQ_HTTP_API", "http://localhost:15672/api"))
    parser.add_argument(
        "--redis-cache-key",
        default=os.getenv("HOT_TOPICS_CACHE_KEY", "dashboard:hot_topics:top50"),
    )
    parser.add_argument(
        "--speed-threshold-ms",
        type=float,
        default=float(os.getenv("HOT_TOPICS_SPEED_THRESHOLD_MS", "50")),
        help="Expected max response time for request #2 and #3",
    )
    args = parser.parse_args()

    return TestContext(
        java_base_url=args.java_base_url.rstrip("/"),
        mongo_uri=args.mongo_uri,
        mongo_db=args.mongo_db,
        redis_host=args.redis_host,
        redis_port=args.redis_port,
        redis_password=args.redis_password,
        redis_db=args.redis_db,
        rabbit_host=args.rabbit_host,
        rabbit_port=args.rabbit_port,
        rabbit_user=args.rabbit_user,
        rabbit_pass=args.rabbit_pass,
        rabbit_vhost=args.rabbit_vhost,
        rabbit_http_api=args.rabbit_http_api,
        redis_cache_key=args.redis_cache_key,
        speed_threshold_ms=args.speed_threshold_ms,
    )


def main() -> int:
    ctx = build_context_from_args()
    print("Running E2E verification with config:")
    print(
        json.dumps(
            {
                "java_base_url": ctx.java_base_url,
                "mongo_uri": ctx.mongo_uri,
                "mongo_db": ctx.mongo_db,
                "redis": f"{ctx.redis_host}:{ctx.redis_port}/{ctx.redis_db}",
                "rabbit": f"{ctx.rabbit_user}@{ctx.rabbit_host}:{ctx.rabbit_port}{ctx.rabbit_vhost}",
                "rabbit_http_api": ctx.rabbit_http_api,
                "cache_key": ctx.redis_cache_key,
                "speed_threshold_ms": ctx.speed_threshold_ms,
            },
            ensure_ascii=False,
            indent=2,
        )
    )

    task_id, task_name = stage_1_create_and_duplicate(ctx)
    stage_2_mongo_and_rabbit(ctx, task_id, task_name)
    stage_3_done_redis_perf(ctx, task_id)

    passed_count = sum(1 for r in ctx.results if r.passed)
    fail_count = sum(1 for r in ctx.results if not r.passed and r.severity != "warn")
    warn_count = sum(1 for r in ctx.results if not r.passed and r.severity == "warn")

    print("\n=== Summary ===")
    print(f"PASS={passed_count}, FAIL={fail_count}, WARN={warn_count}, TOTAL={len(ctx.results)}")

    print_diagnostics(ctx)
    return 1 if fail_count > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
