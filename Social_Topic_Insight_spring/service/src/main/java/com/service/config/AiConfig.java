package com.service.config;

import org.springframework.ai.chat.client.ChatClient;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * Spring AI 客户端配置。
 * <p>
 * 通过注入 {@link ChatClient}，统一管理大模型调用入口。
 */
@Configuration
public class AiConfig {

    /**
     * 注册 ChatClient Bean。
     *
     * @param builder Spring AI 提供的客户端构建器
     * @return 可复用的 ChatClient
     */
    @Bean
    public ChatClient chatClient(ChatClient.Builder builder) {
        return builder.build();
    }
}
