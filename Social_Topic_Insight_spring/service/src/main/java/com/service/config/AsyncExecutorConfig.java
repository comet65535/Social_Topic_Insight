package com.service.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

import java.util.concurrent.Executor;
import java.util.concurrent.ThreadPoolExecutor;

/**
 * 异步线程池配置。
 * <p>
 * 为 LLM 摘要场景提供独立线程池，避免阻塞 Web 请求线程。
 */
@Configuration
@EnableAsync // 开启 Spring 的 @Async 异步执行能力
public class AsyncExecutorConfig {

    /**
     * LLM 摘要线程池。
     *
     * @return 供 LlmSummaryService 并发任务复用的线程池执行器
     */
    @Bean("llmSummaryExecutor")
    public Executor llmSummaryExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        // 核心线程数：常驻处理并发摘要任务
        executor.setCorePoolSize(10);
        // 最大线程数：高峰时可扩容
        executor.setMaxPoolSize(20);
        // 队列容量：削峰填谷，防止瞬时任务抖动
        executor.setQueueCapacity(200);
        executor.setThreadNamePrefix("llm-summary-");
        // 拒绝策略：由调用线程执行，避免任务直接丢弃
        executor.setRejectedExecutionHandler(new ThreadPoolExecutor.CallerRunsPolicy());
        executor.initialize();
        return executor;
    }
}
