package com.xhl.audit;

import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.PrintStream;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Properties;
import java.util.Set;

/** 新版假设入口与历史三字段审计入口相互独立。 */
public final class HypothesisCli {
    private HypothesisCli() {}
    public static int run(String[] args, Map<String,String> env, PrintStream out, PrintStream err) {
        return run(args, env, out, err, null);
    }
    public static int run(String[] args, Map<String,String> env, PrintStream out, PrintStream err, ModelGateway injected) {
        try {
            Map<String,String> options = options(args, Set.of("--source", "--request", "--config", "--provider", "--diagnostic-output", "--replay-response"));
            if (!options.containsKey("--source") || !options.containsKey("--request")) throw new IllegalArgumentException();
            String source = read(options.get("--source"), 1_048_576);
            String requestText = read(options.get("--request"), 32_768);
            ObjectMapper mapper = new ObjectMapper().enable(JsonParser.Feature.STRICT_DUPLICATE_DETECTION)
                .enable(DeserializationFeature.FAIL_ON_TRAILING_TOKENS);
            JsonNode node = mapper.readTree(requestText);
            if (node == null || !node.isObject() || (node.size() != 9 && node.size() != 10)
                || !"1".equals(node.path("schemaVersion").asText())
                || !node.path("modelSource").isTextual() || !node.path("scope").isTextual()
                || !node.path("lineStart").isIntegralNumber() || !node.path("lineEnd").isIntegralNumber()
                || !node.path("mechanism").isTextual() || !node.path("function").isTextual()
                || !node.path("context").isTextual() || !node.path("evidenceIds").isArray()) throw new IllegalArgumentException();
            if (node.size() == 10 && (!node.path("sourceHash").isTextual()
                || !node.path("sourceHash").asText().matches("[0-9a-f]{64}"))) throw new IllegalArgumentException();
            List<String> ids = new ArrayList<>();
            for (JsonNode id : node.path("evidenceIds")) {
                if (!id.isTextual() || ids.contains(id.asText())) throw new IllegalArgumentException();
                ids.add(id.asText());
            }
            var request = new HypothesisService.Request(source, node.path("modelSource").asText(),
                node.has("sourceHash") ? node.path("sourceHash").asText() : null,
                node.path("scope").asText(), node.path("lineStart").intValue(), node.path("lineEnd").intValue(),
                node.path("mechanism").asText(), node.path("function").asText(), node.path("context").asText(), ids);
            String providerName = options.get("--provider");
            ModelGateway gateway = injected;
            if (options.containsKey("--replay-response")) {
                if (gateway != null || options.containsKey("--config") || options.containsKey("--provider"))
                    throw new IllegalArgumentException();
                String content = read(options.get("--replay-response"), 131_072);
                // 重放入口只校验本机原文，不能发起真实网络请求。
                gateway = (name, system, user) -> new GatewayReply(content, "replay", "replay", null, null, 0, "stop", 0);
            }
            if (gateway == null) {
                if (!options.containsKey("--config")) throw new IllegalArgumentException();
                Properties properties = new Properties();
                try (var reader = Files.newBufferedReader(Path.of(options.get("--config")), StandardCharsets.UTF_8)) {
                    properties.load(reader);
                }
                ProviderRegistry registry = new ProviderRegistry(properties, env);
                var provider = registry.resolve(providerName);
                if (!"json_schema".equals(provider.responseFormat())) throw new IllegalArgumentException();
                providerName = provider.name();
                SpringAiGateway real = new SpringAiGateway(registry);
                gateway = real::completeHypotheses;
            }
            if (options.containsKey("--diagnostic-output")) {
                Path diagnostic = Path.of(options.get("--diagnostic-output"));
                ModelGateway original = gateway;
                gateway = (name, system, user) -> {
                    var reply = original.complete(name, system, user);
                    // 仅写入调用者指定的新文件；诊断写入失败不改变模型结论。
                    try {
                        if (reply.content() != null && reply.content().length() <= 16_384)
                            Files.writeString(diagnostic, reply.content(), StandardCharsets.UTF_8,
                                java.nio.file.StandardOpenOption.CREATE_NEW, java.nio.file.StandardOpenOption.WRITE);
                    } catch (java.io.IOException ignored) { }
                    return reply;
                };
            }
            var result = new HypothesisService(gateway).analyze(request, providerName);
            out.println(mapper.writeValueAsString(result));
            return "COMPLETED".equals(result.status()) ? 0 : 1;
        } catch (Exception e) {
            err.println("假设输入或配置无效：请检查参数、UTF-8 源码、请求 JSON 与结构化输出配置。");
            return 2;
        }
    }
    static Map<String,String> options(String[] args, Set<String> allowed) {
        Map<String,String> result = new HashMap<>();
        for (int i=0; i<args.length; i+=2) {
            if (i+1>=args.length || !allowed.contains(args[i]) || result.putIfAbsent(args[i],args[i+1])!=null)
                throw new IllegalArgumentException();
        }
        return result;
    }
    static String read(String path, int limit) throws Exception {
        byte[] bytes;
        try (var input = Files.newInputStream(Path.of(path))) { bytes = input.readNBytes(limit+1); }
        if (bytes.length > limit) throw new IllegalArgumentException();
        return StandardCharsets.UTF_8.newDecoder().decode(ByteBuffer.wrap(bytes)).toString();
    }
}
