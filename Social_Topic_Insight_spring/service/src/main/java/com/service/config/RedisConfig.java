package com.service.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.serializer.GenericJackson2JsonRedisSerializer;
import org.springframework.data.redis.serializer.StringRedisSerializer;

/**
 * Redis 模板配置。
 * <p>
 * 该配置统一了 key/value 的序列化方案，避免不同模块因序列化格式不一致导致缓存不可读。
 */
@Configuration
public class RedisConfig {

    /**
     * 注册 RedisTemplate。
     *
     * @param connectionFactory Redis 连接工厂
     * @return 可直接读写 JSON 对象的 RedisTemplate
     */
    @Bean
    public RedisTemplate<String, Object> redisTemplate(
            RedisConnectionFactory connectionFactory
    ) {
        // Step 1: 创建模板并注入连接工厂
        RedisTemplate<String, Object> template = new RedisTemplate<>();
        template.setConnectionFactory(connectionFactory);

        // Step 2: 使用 Jackson 通用序列化器处理 value/hashValue
        GenericJackson2JsonRedisSerializer serializer = new GenericJackson2JsonRedisSerializer();

        // Step 3: key/hashKey 使用字符串序列化，便于排查与运维工具查看
        template.setKeySerializer(new StringRedisSerializer());
        template.setValueSerializer(serializer);
        template.setHashKeySerializer(new StringRedisSerializer());
        template.setHashValueSerializer(serializer);

        // Step 4: 初始化模板
        template.afterPropertiesSet();
        return template;
    }
}
