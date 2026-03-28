package com.service.config;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.serializer.Jackson2JsonRedisSerializer;
import org.springframework.data.redis.serializer.StringRedisSerializer;

/**
 * Redis template configuration.
 *
 * <p>Use plain JSON for values to avoid polymorphic type metadata in cache payloads.
 */
@Configuration
public class RedisConfig {

    /**
     * Register RedisTemplate.
     *
     * @param connectionFactory Redis connection factory
     * @return RedisTemplate for JSON object read/write
     */
    @Bean
    public RedisTemplate<String, Object> redisTemplate(RedisConnectionFactory connectionFactory) {
        // Step 1: Create template and inject connection factory.
        RedisTemplate<String, Object> template = new RedisTemplate<>();
        template.setConnectionFactory(connectionFactory);

        // Step 2: Configure ObjectMapper without polymorphic default typing.
        ObjectMapper objectMapper = new ObjectMapper();
        objectMapper.registerModule(new JavaTimeModule());
        objectMapper.disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);

        // Step 3: Serialize values as plain JSON (no "@class" metadata).
        Jackson2JsonRedisSerializer<Object> valueSerializer = new Jackson2JsonRedisSerializer<>(Object.class);
        valueSerializer.setObjectMapper(objectMapper);

        // Step 4: Key serializers use string for readability in Redis CLI.
        StringRedisSerializer keySerializer = new StringRedisSerializer();
        template.setKeySerializer(keySerializer);
        template.setHashKeySerializer(keySerializer);
        template.setValueSerializer(valueSerializer);
        template.setHashValueSerializer(valueSerializer);

        // Step 5: Initialize template.
        template.afterPropertiesSet();
        return template;
    }
}
