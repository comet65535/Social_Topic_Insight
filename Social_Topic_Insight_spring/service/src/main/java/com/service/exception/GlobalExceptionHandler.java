package com.service.exception;

import com.common.result.Result;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

/**
 * 全局异常处理器。
 * <p>
 * 负责将系统中的异常统一转换成前端可识别的标准响应格式，
 * 并返回真实的 HTTP 状态码，避免“HTTP 200 + 业务失败”的语义歧义。
 */
@Slf4j
@RestControllerAdvice // 让异常处理逻辑对所有 RestController 生效
public class GlobalExceptionHandler {

    /**
     * 处理业务异常。
     *
     * @param ex 业务异常对象
     * @return 带真实 HTTP 状态码的错误响应
     */
    @ExceptionHandler(BusinessException.class)
    public ResponseEntity<Result<?>> handleBusinessException(BusinessException ex) {
        HttpStatus status = HttpStatus.resolve(ex.getHttpStatus());
        if (status == null) {
            status = HttpStatus.BAD_REQUEST;
        }
        return ResponseEntity.status(status).body(Result.error(status.value(), ex.getMessage()));
    }

    /**
     * 处理 Spring 参数校验失败异常。
     *
     * @param ex 参数校验异常
     * @return HTTP 400 错误响应
     */
    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<Result<?>> handleMethodArgumentNotValidException(MethodArgumentNotValidException ex) {
        String message = ex.getBindingResult().getFieldError() == null
                ? "参数校验失败"
                : ex.getBindingResult().getFieldError().getDefaultMessage();
        return ResponseEntity.badRequest().body(Result.error(HttpStatus.BAD_REQUEST.value(), message));
    }

    /**
     * 处理兜底异常。
     *
     * @param ex 未处理异常
     * @return HTTP 500 错误响应
     */
    @ExceptionHandler(Exception.class)
    public ResponseEntity<Result<?>> handleException(Exception ex) {
        log.error("Unhandled exception", ex);
        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                .body(Result.error(HttpStatus.INTERNAL_SERVER_ERROR.value(), "服务内部异常，请稍后重试"));
    }
}
