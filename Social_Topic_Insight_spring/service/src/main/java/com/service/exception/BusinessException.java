package com.service.exception;

/**
 * 业务异常。
 * <p>
 * 该异常用于“可预期”的业务失败场景（例如参数非法、重复任务提交等），
 * 同时携带 HTTP 状态码，便于在全局异常处理中返回真实网络层状态。
 */
public class BusinessException extends RuntimeException {

    /**
     * 对应的 HTTP 状态码（如 400、409）。
     */
    private final int httpStatus;

    /**
     * 构造默认 400 的业务异常。
     *
     * @param message 业务错误信息
     */
    public BusinessException(String message) {
        this(message, 400);
    }

    /**
     * 构造可指定 HTTP 状态码的业务异常。
     *
     * @param message 业务错误信息
     * @param httpStatus HTTP 状态码
     */
    public BusinessException(String message, int httpStatus) {
        super(message);
        this.httpStatus = httpStatus;
    }

    /**
     * 获取该异常对应的 HTTP 状态码。
     *
     * @return HTTP 状态码
     */
    public int getHttpStatus() {
        return httpStatus;
    }
}
