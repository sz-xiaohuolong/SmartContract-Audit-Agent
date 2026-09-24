package com.xhl.audit;

import java.net.URI;
import java.time.Duration;
import java.util.Map;
import java.util.Properties;

/** 只在选中供应商时解析凭证，避免未使用配置阻挡离线启动。 */
public final class ProviderRegistry {
    private final Properties properties = new Properties();
    private final Map<String,String> environment;
    public ProviderRegistry(Properties properties, Map<String,String> environment) {
        this.properties.putAll(properties); this.environment = Map.copyOf(environment);
    }
    public Provider resolve(String name) {
        String selected = name == null ? properties.getProperty("default-provider", "ark") : name;
        if (!selected.matches("[a-zA-Z0-9_-]+")) throw new IllegalArgumentException("供应商标识无效");
        String prefix = "providers." + selected + ".";
        String base = required(prefix + "base-url");
        URI uri;
        try {uri = URI.create(base);} catch (IllegalArgumentException e) {throw new IllegalArgumentException("供应商地址无效");}
        boolean loopback = "127.0.0.1".equals(uri.getHost()) || "localhost".equals(uri.getHost()) || "[::1]".equals(uri.getHost());
        if (uri.getHost() == null || uri.getUserInfo() != null || uri.getQuery() != null || uri.getFragment() != null
            || !("https".equals(uri.getScheme()) || ("http".equals(uri.getScheme()) && loopback)))
            throw new IllegalArgumentException("供应商需 HTTPS 地址；仅本地测试允许 HTTP");
        String key = properties.getProperty(prefix + "api-key");
        if (key == null || key.isBlank()) {
            String variable = properties.getProperty(prefix + "api-key-env");
            if (variable != null && !variable.isBlank()) key = environment.get(variable.trim());
        }
        if (key == null || key.isBlank()) throw new IllegalArgumentException("所选供应商缺少 API Key");
        return new Provider(selected, base.replaceAll("/+$", ""), required(prefix + "model"), key,
            Duration.ofSeconds(positive(prefix + "timeout-seconds", 60, 600)), positive(prefix + "max-output-tokens", 2048, 32768));
    }
    private String required(String key) {
        String value = properties.getProperty(key);
        if (value == null || value.isBlank()) throw new IllegalArgumentException("缺少配置项：" + key);
        return value.trim();
    }
    private int positive(String key, int fallback, int max) {
        int value;
        try {value = Integer.parseInt(properties.getProperty(key, Integer.toString(fallback)));}
        catch (NumberFormatException e) {throw new IllegalArgumentException("数值配置无效：" + key);}
        if (value < 1 || value > max) throw new IllegalArgumentException("数值配置超出范围：" + key);
        return value;
    }
    public record Provider(String name, String baseUrl, String model, String apiKey, Duration timeout, int maxOutputTokens) {
        @Override public String toString() {return "Provider[name="+name+", model="+model+", apiKey=<redacted>]";}
    }
}
