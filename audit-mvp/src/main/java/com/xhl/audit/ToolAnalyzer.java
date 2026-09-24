package com.xhl.audit;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.core.JsonParser;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.List;

/** 工具成功仅表示执行和解析成功，空报警不构成安全证明。 */
public final class ToolAnalyzer {
    public enum Engine { SLITHER, MYTHRIL }
    public enum Status { OK, TIMEOUT, PROCESS_ERROR, TOOL_ERROR, PARSE_ERROR, OUTPUT_TRUNCATED, CLEANUP_ERROR }
    public record Result(Engine engine, Status status, JsonNode issues, ProcessRunner.Result process) {}
    private final ProcessRunner runner;
    private final ObjectMapper mapper = new ObjectMapper()
        .enable(JsonParser.Feature.STRICT_DUPLICATE_DETECTION)
        .enable(DeserializationFeature.FAIL_ON_TRAILING_TOKENS);

    public ToolAnalyzer(ProcessRunner runner) { this.runner = runner; }

    public Result parse(Engine engine, ProcessRunner.Result process) {
        if (process.status() == ProcessRunner.Status.TIMEOUT) return failure(engine, Status.TIMEOUT, process);
        if (process.status() != ProcessRunner.Status.OK) return failure(engine, Status.PROCESS_ERROR, process);
        if (!process.cleanedUp()) return failure(engine, Status.CLEANUP_ERROR, process);
        if (process.truncated()) return failure(engine, Status.OUTPUT_TRUNCATED, process);
        try {
            JsonNode root = mapper.readTree(process.stdout());
            if (root == null || !root.isObject()) return failure(engine, Status.PARSE_ERROR, process);
            if (root.has("success") && root.get("success").isBoolean() && !root.get("success").booleanValue())
                return failure(engine, Status.TOOL_ERROR, process);
            if (!root.path("success").isBoolean() || !root.path("success").booleanValue())
                return failure(engine, Status.PARSE_ERROR, process);
            if (engine == Engine.SLITHER && !root.path("results").isObject())
                return failure(engine, Status.PARSE_ERROR, process);
            JsonNode issues = engine == Engine.SLITHER ? root.path("results").path("detectors") : root.path("issues");
            if (engine == Engine.SLITHER && issues.isMissingNode()) issues = mapper.createArrayNode();
            if (!issues.isArray()) return failure(engine, Status.PARSE_ERROR, process);
            for (JsonNode issue : issues) if (!issue.isObject()) return failure(engine, Status.PARSE_ERROR, process);
            return new Result(engine, Status.OK, issues, process);
        } catch (Exception e) { return failure(engine, Status.PARSE_ERROR, process); }
    }

    public Result analyze(Engine engine, String executable, String source, Duration timeout) throws java.io.IOException {
        if (source == null || source.isBlank()) throw new IllegalArgumentException("源码不能为空");
        // 将相对可执行文件路径在进入临时目录前固定；命令名仍由 PATH 解析。
        String command = executable.contains("/") ? Path.of(executable).toAbsolutePath().toString() : executable;
        Path directory = Files.createTempDirectory("verirag-tool-");
        try {
            Path contract = directory.resolve("Contract.sol");
            Files.writeString(contract, source);
            List<String> args = command(engine, command, contract);
            return parse(engine, runner.run(args, directory, timeout, 2 * 1024 * 1024));
        } finally {
            try (var paths = Files.walk(directory)) {
                for (Path path : paths.sorted(java.util.Comparator.reverseOrder()).toList()) Files.deleteIfExists(path);
            }
        }
    }

    static List<String> command(Engine engine, String executable, Path contract) {
        return engine == Engine.SLITHER
            ? List.of(executable, contract.toString(), "--json", "-", "--fail-none")
            : List.of(executable, "analyze", contract.toString(), "-o", "json");
    }

    private Result failure(Engine engine, Status status, ProcessRunner.Result process) {
        return new Result(engine, status, mapper.createArrayNode(), process);
    }
}
