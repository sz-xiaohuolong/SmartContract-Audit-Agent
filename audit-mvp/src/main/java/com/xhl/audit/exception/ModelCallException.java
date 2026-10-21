package com.xhl.audit.exception;

/** 模型调用失败时保留实际请求次数，供业务服务记录；不在消息中暴露供应商正文。 */
public final class ModelCallException extends RuntimeException {
    private final int requestAttempts;

    public ModelCallException(RuntimeException cause, int requestAttempts) {
        super("模型调用重试耗尽", cause);
        this.requestAttempts = requestAttempts;
    }

    public int requestAttempts() {
        return requestAttempts;
    }
}
