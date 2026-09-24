package com.xhl.audit.retrieval;

import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.time.Duration;
import java.util.*;
import static com.xhl.audit.retrieval.RetrievalData.*;

/** 可单独运行 D1/传统检索，不装配模型和 D2。 */
public final class RetrievalCli {
    private RetrievalCli() {}
    public record Request(Target target, CandidatePool pool, Budget budget) {}
    public static int run(String[] args, PrintStream out, PrintStream err) {
        if (args.length == 0 || Arrays.equals(args, new String[]{"--help"})) {
            out.println("用法：--retrieval --source 合约.sol --request 检索请求.json --worker program_facts.py [--python python3] [--strategy dense|hybrid|contrastive|d1|compare]");
            out.println("仅提取事实和比较检索，不调用模型；预算单位为实际上下文 UTF-8 字节。");
            return 0;
        }
        try {
            var options = new HashMap<String, String>();
            for (int i = 0; i < args.length; i += 2) {
                if (i + 1 >= args.length || !Set.of("--source", "--request", "--worker", "--python", "--strategy").contains(args[i])
                    || options.putIfAbsent(args[i], args[i + 1]) != null) throw new IllegalArgumentException();
            }
            for (String required : List.of("--source", "--request", "--worker")) if (!options.containsKey(required)) throw new IllegalArgumentException();
            String source = StandardCharsets.UTF_8.newDecoder().decode(java.nio.ByteBuffer.wrap(read(Path.of(options.get("--source")), 1_048_576))).toString();
            var mapper = new ObjectMapper().enable(JsonParser.Feature.STRICT_DUPLICATE_DETECTION)
                .enable(DeserializationFeature.FAIL_ON_TRAILING_TOKENS).enable(DeserializationFeature.FAIL_ON_NULL_FOR_PRIMITIVES).enable(DeserializationFeature.FAIL_ON_MISSING_CREATOR_PROPERTIES);
            Request request = mapper.readValue(read(Path.of(options.get("--request")), 8_388_608), Request.class);
            ProgramFacts facts = new PythonFactsExtractor(options.getOrDefault("--python", "python3"), Path.of(options.get("--worker")), Duration.ofSeconds(10)).extract(source);
            if (facts.status().equals("FAILED")) {
                out.println(mapper.writeValueAsString(Map.of("facts", facts, "results", List.of())));
                return 1;
            }
            var strategies = new LinkedHashMap<String, RetrievalStrategy>();
            strategies.put("dense", new DenseRetriever()); strategies.put("hybrid", new HybridRetriever());
            strategies.put("contrastive", new ContrastiveRetriever()); strategies.put("d1", new D1Retriever());
            String selected = options.getOrDefault("--strategy", "d1");
            if (!selected.equals("compare") && !strategies.containsKey(selected)) throw new IllegalArgumentException();
            var results = new ArrayList<EvidenceBundle>();
            for (var entry : strategies.entrySet()) if (selected.equals("compare") || selected.equals(entry.getKey()))
                results.add(entry.getValue().retrieve(facts, request.target(), request.pool(), request.budget()));
            out.println(mapper.writeValueAsString(Map.of("facts", facts, "results", results)));
            return 0;
        } catch (Exception e) {
            err.println("检索输入无效：检查源码、候选池、角色绑定、预算和事实提供器路径。");
            return 2;
        }
    }
    private static byte[] read(Path path, int limit) throws Exception {
        try (var stream = Files.newInputStream(path)) {
            byte[] bytes = stream.readNBytes(limit + 1);
            if (bytes.length > limit) throw new IllegalArgumentException();
            return bytes;
        }
    }
}
