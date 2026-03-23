package com.common.result;

import lombok.Data;

/**
 * 统一接口响应模型。
 *
 * @param <T> data 字段的数据类型
 */
@Data
public class Result<T> {
    /**
     * 业务状态码。
     * 约定：200=成功，4xx/5xx=失败。
     */
    private Integer code;

    /**
     * 响应描述信息。
     */
    private String msg;

    /**
     * 响应数据载荷。
     */
    private T data;

    /**
     * 构造成功响应。
     *
     * @param data 响应数据
     * @return 成功结果对象
     * @param <T> data 类型
     */
    public static <T> Result<T> success(T data) {
        Result<T> result = new Result<>();
        result.setCode(200);
        result.setMsg("success");
        result.setData(data);
        return result;
    }

    /**
     * 构造无数据的成功响应。
     *
     * @return 成功结果对象
     * @param <T> data 类型
     */
    public static <T> Result<T> success() {
        return success(null);
    }

    /**
     * 构造失败响应，默认使用 400。
     *
     * @param msg 错误信息
     * @return 失败结果对象
     * @param <T> data 类型
     */
    public static <T> Result<T> error(String msg) {
        return error(400, msg);
    }

    /**
     * 构造失败响应（可指定业务码）。
     *
     * @param code 业务状态码
     * @param msg 错误信息
     * @return 失败结果对象
     * @param <T> data 类型
     */
    public static <T> Result<T> error(int code, String msg) {
        Result<T> result = new Result<>();
        result.setCode(code);
        result.setMsg(msg);
        return result;
    }
}
