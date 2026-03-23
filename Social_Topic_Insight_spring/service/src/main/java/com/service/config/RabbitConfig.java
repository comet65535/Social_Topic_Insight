package com.service.config;

import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.support.converter.Jackson2JsonMessageConverter;
import org.springframework.amqp.support.converter.MessageConverter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * RabbitMQ 拓扑配置。
 * <p>
 * 统一声明任务下发与聚类回调所需的交换机、队列、路由键，
 * 保证 Java 与 Python Worker 对同一消息通道的认知一致。
 */
@Configuration
public class RabbitConfig {

    public static final String TASK_QUEUE = "task.queue";
    public static final String TASK_EXCHANGE = "task.exchange";
    public static final String TASK_ROUTING_KEY = "task.routing";

    public static final String CLUSTER_DONE_QUEUE = "cluster.done.queue";
    public static final String CLUSTER_EXCHANGE = "cluster.exchange";
    public static final String CLUSTER_DONE_ROUTING_KEY = "cluster.done";

    /**
     * 任务队列：Python Worker 消费该队列执行任务。
     *
     * @return 任务队列定义
     */
    @Bean
    public Queue taskQueue() {
        return new Queue(TASK_QUEUE, true);
    }

    /**
     * 任务交换机（Direct）。
     *
     * @return 任务交换机
     */
    @Bean
    public DirectExchange taskExchange() {
        return new DirectExchange(TASK_EXCHANGE, true, false);
    }

    /**
     * 绑定任务队列与任务交换机。
     *
     * @param taskQueue 任务队列
     * @param taskExchange 任务交换机
     * @return 绑定关系
     */
    @Bean
    public Binding taskBinding(Queue taskQueue, DirectExchange taskExchange) {
        return BindingBuilder.bind(taskQueue).to(taskExchange).with(TASK_ROUTING_KEY);
    }

    /**
     * 聚类完成回调队列：Java 监听该队列触发 LLM 摘要与缓存预热。
     *
     * @return 聚类完成队列
     */
    @Bean
    public Queue clusterDoneQueue() {
        return new Queue(CLUSTER_DONE_QUEUE, true);
    }

    /**
     * 聚类回调交换机（Direct）。
     *
     * @return 聚类回调交换机
     */
    @Bean
    public DirectExchange clusterExchange() {
        return new DirectExchange(CLUSTER_EXCHANGE, true, false);
    }

    /**
     * 绑定聚类完成队列与回调交换机。
     *
     * @param clusterDoneQueue 聚类完成队列
     * @param clusterExchange 聚类回调交换机
     * @return 绑定关系
     */
    @Bean
    public Binding clusterDoneBinding(Queue clusterDoneQueue, DirectExchange clusterExchange) {
        return BindingBuilder.bind(clusterDoneQueue).to(clusterExchange).with(CLUSTER_DONE_ROUTING_KEY);
    }

    /**
     * 全局消息转换器：JSON <-> Java 对象。
     *
     * @return Jackson 消息转换器
     */
    @Bean
    public MessageConverter jacksonMessageConverter() {
        return new Jackson2JsonMessageConverter();
    }
}
