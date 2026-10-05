package com.xhl.audit;

import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.Test;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import java.util.Properties;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;
import static org.junit.jupiter.api.Assertions.*;

class GatewayTest {
    @Test void deepseekRequestCapsReasoningAndAnswerTogether() throws Exception {
        var request = new AtomicReference<String>();
        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/api/plan/v3/chat/completions", exchange -> {
            request.set(new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8));
            byte[] body = """
                {"id":"test","object":"chat.completion","created":1,"model":"deepseek-v4-flash","choices":[{"index":0,"message":{"role":"assistant","content":"ok"},"finish_reason":"length"}]}
                """.getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set("Content-Type", "application/json");
            exchange.sendResponseHeaders(200, body.length);
            exchange.getResponseBody().write(body); exchange.close();
        });
        server.start();
        try {
            var props = new Properties();
            props.setProperty("providers.ark.base-url", "http://127.0.0.1:" + server.getAddress().getPort() + "/api/plan/v3");
            props.setProperty("providers.ark.model", "deepseek-v4-flash");
            props.setProperty("providers.ark.api-key", "fixture");
            props.setProperty("providers.ark.max-output-tokens", "512");
            props.setProperty("providers.ark.response-format", "json_schema");
            props.setProperty("providers.ark.thinking", "disabled");
            var reply = new SpringAiGateway(new ProviderRegistry(props, Map.of())).complete("ark", "系统", "测试");
            assertEquals("LENGTH", reply.finishReason());
            var json = new com.fasterxml.jackson.databind.ObjectMapper().readTree(request.get());
            assertEquals(512, json.path("max_completion_tokens").asInt());
            assertFalse(json.has("max_tokens"));
            assertEquals("json_schema", json.path("response_format").path("type").asText());
            assertTrue(json.path("response_format").path("json_schema").path("strict").asBoolean());
            assertEquals(3, json.path("response_format").path("json_schema").path("schema").path("required").size(), json.path("response_format").toString());
            assertEquals("disabled", json.path("thinking").path("type").asText());
            assertFalse(json.has("reasoning_effort"));
            new SpringAiGateway(new ProviderRegistry(props, Map.of())).completeHypotheses("ark", "系统", "测试");
            var hypothesisRequest = new com.fasterxml.jackson.databind.ObjectMapper().readTree(request.get());
            var hypothesisSchema = hypothesisRequest.path("response_format").path("json_schema").path("schema");
            assertEquals(2, hypothesisSchema.path("required").size());
            assertEquals(3, hypothesisSchema.path("properties").path("hypotheses").path("maxItems").asInt());
            assertFalse(hypothesisSchema.path("properties").path("hypotheses").path("items").path("additionalProperties").asBoolean(true));
            props.remove("providers.ark.response-format");
            props.remove("providers.ark.thinking");
            new SpringAiGateway(new ProviderRegistry(props, Map.of())).complete("ark", "系统", "测试");
            var ordinary = new com.fasterxml.jackson.databind.ObjectMapper().readTree(request.get());
            assertFalse(ordinary.has("response_format"));
            assertFalse(ordinary.has("thinking"));
        } finally { server.stop(0); }
    }
    @Test void usesSelectedProviderPathModelAndPreservesUsage() throws Exception {
        var request = new AtomicReference<String>();
        var auth = new AtomicReference<String>();
        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/api/plan/v3/chat/completions", exchange -> {
            request.set(new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8));
            auth.set(exchange.getRequestHeaders().getFirst("Authorization"));
            byte[] body = """
                {"id":"test","object":"chat.completion","created":1,"model":"model-a","choices":[{"index":0,"message":{"role":"assistant","content":"hello"},"finish_reason":"stop"}],"usage":{"prompt_tokens":7,"completion_tokens":2,"total_tokens":9}}
                """.getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set("Content-Type", "application/json");
            exchange.sendResponseHeaders(200, body.length);
            exchange.getResponseBody().write(body); exchange.close();
        });
        var second = new AtomicInteger();
        server.createContext("/other/chat/completions", exchange -> {
            second.incrementAndGet();
            exchange.getRequestBody().readAllBytes();
            byte[] body = """
                {"id":"test2","object":"chat.completion","created":1,"model":"model-b","choices":[{"index":0,"message":{"role":"assistant","content":"other"},"finish_reason":"stop"}]}
                """.getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set("Content-Type", "application/json");
            exchange.sendResponseHeaders(200, body.length); exchange.getResponseBody().write(body); exchange.close();
        });
        server.start();
        try {
            var props = new Properties();
            props.setProperty("default-provider", "ark");
            props.setProperty("providers.ark.base-url", "http://127.0.0.1:" + server.getAddress().getPort() + "/api/plan/v3");
            props.setProperty("providers.ark.model", "model-a");
            props.setProperty("providers.ark.api-key-env", "TEST_KEY");
            props.setProperty("providers.other.base-url", "http://127.0.0.1:" + server.getAddress().getPort() + "/other");
            props.setProperty("providers.other.model", "model-b");
            props.setProperty("providers.other.api-key-env", "SECOND_KEY");
            var registry = new ProviderRegistry(props, Map.of("TEST_KEY", "local-test", "SECOND_KEY", "second"));
            var gateway = new SpringAiGateway(registry);
            var reply = gateway.complete(null, "系统提示", "测试");
            assertEquals("hello", reply.content());
            assertEquals(7, reply.inputTokens()); assertEquals(2, reply.outputTokens());
            assertEquals("ark", reply.provider()); assertEquals("Bearer local-test", auth.get());
            assertTrue(request.get().contains("model-a"));
            var defaultRequest = new com.fasterxml.jackson.databind.ObjectMapper().readTree(request.get());
            assertFalse(defaultRequest.has("response_format"));
            assertFalse(defaultRequest.has("thinking"));
            var other = gateway.complete("other", "系统提示", "测试");
            assertEquals("other", other.content()); assertEquals(1, second.get());
            assertNull(other.inputTokens(), "缺失 usage 不应被记成零");
        } finally { server.stop(0); }
    }
    @Test void rejectsMissingKeyAndRemotePlainHttpWithoutLeakingConfiguration() {
        var p = new Properties();p.setProperty("default-provider", "ark");
        p.setProperty("providers.ark.base-url", "https://example.com/api/plan/v3");
        p.setProperty("providers.ark.model", "m");p.setProperty("providers.ark.api-key-env", "KEY");
        assertThrows(IllegalArgumentException.class, () -> new ProviderRegistry(p, Map.of()).resolve(null));
        p.setProperty("providers.ark.base-url", "http://example.com");
        assertThrows(IllegalArgumentException.class, () -> new ProviderRegistry(p, Map.of("KEY", "secret")).resolve(null));
    }
}
