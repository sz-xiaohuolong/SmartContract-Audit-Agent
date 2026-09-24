package com.xhl.audit.retrieval;

import com.xhl.audit.ProcessRunner;
import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.MessageDigest;
import java.time.Duration;
import java.util.*;
import static com.xhl.audit.retrieval.RetrievalData.*;

/** 使用受控本地子进程提取事实；错误、截断或摘要不符不注入检索。 */
public final class PythonFactsExtractor {
    private final String python;
    private final Path worker;
    private final Duration timeout;
    public PythonFactsExtractor(String python, Path worker, Duration timeout) {
        this.python = python; this.worker = worker.toAbsolutePath().normalize(); this.timeout = timeout;
    }
    public ProgramFacts extract(String source) {
        String hash;
        try {hash = HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(source.getBytes(StandardCharsets.UTF_8)));}
        catch (Exception e) {throw new IllegalArgumentException("源码无效");}
        Path directory = null;
        try {
            if (source.isBlank() || source.getBytes(StandardCharsets.UTF_8).length > 1_048_576) throw new IllegalArgumentException();
            directory = Files.createTempDirectory("d1-facts-");
            Path input = directory.resolve("source.sol"); Files.writeString(input, source, StandardCharsets.UTF_8);
            var result = new ProcessRunner().run(List.of(python, worker.toString(), "--source", input.toString()), directory, timeout, 2_097_152);
            if (result.status() != ProcessRunner.Status.OK || result.truncated() || !result.cleanedUp()) throw new IllegalArgumentException();
            var mapper = new ObjectMapper().enable(JsonParser.Feature.STRICT_DUPLICATE_DETECTION)
                .enable(DeserializationFeature.FAIL_ON_TRAILING_TOKENS).enable(DeserializationFeature.FAIL_ON_NULL_FOR_PRIMITIVES).enable(DeserializationFeature.FAIL_ON_MISSING_CREATOR_PROPERTIES);
            ProgramFacts facts = mapper.readValue(result.stdout(), ProgramFacts.class);
            if (!"1".equals(facts.schemaVersion()) || !hash.equals(facts.sourceHash()) || facts.facts() == null
                || facts.scopes() == null || facts.stateVariables() == null || facts.limitations() == null
                || !Set.of("COMPLETE", "PARTIAL", "FAILED").contains(facts.status())) throw new IllegalArgumentException();
            long lines = source.lines().count();
            if (facts.facts().stream().anyMatch(f -> f.line() < 1 || f.line() > lines)) throw new IllegalArgumentException();
            return facts;
        } catch (Exception e) {
            return new ProgramFacts("1", hash, "FAILED", List.of(), List.of(), List.of(), List.of("事实提供器失败、超时、截断或输出无效"));
        } finally {
            if (directory != null) {
                try {Files.deleteIfExists(directory.resolve("source.sol")); Files.deleteIfExists(directory);}
                catch (Exception ignored) { /* 清理失败不把已有失败事实改为成功。 */ }
            }
        }
    }
}
