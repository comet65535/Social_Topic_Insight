package com.service;

import lombok.extern.slf4j.Slf4j;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.CrossOrigin;

/**
 * Spring Boot 服务启动入口。
 */
@CrossOrigin // 允许跨域请求（便于前端本地调试）
@SpringBootApplication // 声明为 Spring Boot 自动装配应用
@Slf4j
public class TopicApplication {

    /**
     * 应用主函数。
     *
     * @param args 启动参数
     */
    public static void main(String[] args) {
        log.info("spring 启动 ~~");
        SpringApplication.run(TopicApplication.class, args);
    }
}
