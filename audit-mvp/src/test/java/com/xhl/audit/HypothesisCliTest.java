package com.xhl.audit;

import org.junit.jupiter.api.Test;
import java.io.ByteArrayOutputStream;
import java.io.PrintStream;
import java.nio.file.Files;
import java.util.Map;
import static org.junit.jupiter.api.Assertions.*;

class HypothesisCliTest {
    @Test void 显式权限事实提示实际消费与回执一致并拒绝漂移和超预算() throws Exception {
        var directory = Files.createTempDirectory("permission-guidance-test-");
        try {
            String content = "contract C { uint x; function f() public { x = 1; } }";
            var source = directory.resolve("Contract.sol");
            Files.writeString(source, content);
            var catalog = RiskCatalogFixture.catalog(content);
            RiskCatalogFixture.operation(catalog, content, "C", "f", "x = 1", "WRITE", "a".repeat(64));
            var node = RiskCatalogFixture.MAPPER.createObjectNode();
            node.put("schemaVersion", "1").put("modelSource", content).put("scope", "FULL")
                .put("lineStart", 1).put("lineEnd", 1).put("mechanism", "ACCESS_CONTROL")
                .put("function", "f").put("context", "");
            node.putArray("evidenceIds");
            node.set("riskCatalog", catalog);
            var captured = new java.util.ArrayList<String>();
            ModelGateway fake = (p, s, u) -> {
                captured.add(u);
                return new GatewayReply("{\"schemaVersion\":\"2\",\"hypotheses\":[]}", "fixture", "fixture", null, null, 1);
            };
            var request = directory.resolve("request.json");
            for (boolean enabled : new boolean[]{false, true}) {
                if (enabled) node.set("factGuidance", RiskCatalogFixture.guidance(catalog, "检查读取状态：x；没有完整保护证明。"));
                Files.writeString(request, node.toString());
                var output = new ByteArrayOutputStream();
                int status = HypothesisCli.run(new String[]{"--source", source.toString(), "--request", request.toString(),
                    "--provider", "fixture"}, Map.of(), new PrintStream(output), System.err, fake);
                assertEquals(0, status);
                var receipt = RiskCatalogFixture.MAPPER.readTree(output.toString()).path("requestConsumptionReceipt");
                assertEquals(enabled, receipt.has("factGuidance"));
                if (enabled) {
                    assertEquals(node.path("factGuidance"), receipt.path("factGuidance"));
                    assertTrue(captured.getLast().contains(receipt.path("factGuidance").path("text").asText()));
                    assertTrue(captured.getLast().contains(content));
                }
            }
            for (String field : java.util.List.of("sourceHash", "receiptDigest", "textSha256")) {
                var broken = node.deepCopy();
                ((com.fasterxml.jackson.databind.node.ObjectNode) broken.path("factGuidance")).put(field, "0".repeat(64));
                Files.writeString(request, broken.toString());
                assertEquals(1, HypothesisCli.run(new String[]{"--source", source.toString(), "--request", request.toString(),
                    "--provider", "fixture"}, Map.of(), new PrintStream(new ByteArrayOutputStream()), System.err, fake));
            }
            node.put("maxPromptBytes", 1);
            Files.writeString(request, node.toString());
            var blocked = new ByteArrayOutputStream();
            assertEquals(1, HypothesisCli.run(new String[]{"--source", source.toString(), "--request", request.toString(),
                "--provider", "fixture"}, Map.of(), new PrintStream(blocked), System.err, fake));
            assertTrue(blocked.toString().contains("INPUT_BUDGET_EXCEEDED"));
            assertEquals(2, captured.size());
        } finally {
            try (var files = Files.walk(directory)) {
                for (var path : files.sorted(java.util.Comparator.reverseOrder()).toList()) Files.deleteIfExists(path);
            }
        }
    }
    @Test void 旧请求与可选源码摘要风险目录均可离线重放且拒绝未知字段() throws Exception {
        var directory = Files.createTempDirectory("hypothesis-catalog-test-");
        try {
            String content = "contract C { uint x; function f() public { x = 1; } }";
            var source = directory.resolve("Contract.sol");
            Files.writeString(source, content);
            var catalog = RiskCatalogFixture.catalog(content);
            RiskCatalogFixture.operation(catalog, content, "C", "f", "x = 1", "WRITE", "a".repeat(64));
            var node = RiskCatalogFixture.MAPPER.createObjectNode();
            node.put("schemaVersion", "1").put("modelSource", content).put("scope", "FULL")
                .put("lineStart", 1).put("lineEnd", 1).put("mechanism", "ACCESS_CONTROL")
                .put("function", "f").put("context", "").putArray("evidenceIds");
            var raw = directory.resolve("raw.json");
            Files.writeString(raw, "{\"schemaVersion\":\"2\",\"hypotheses\":[{\"vulnerabilityType\":\"ACCESS_CONTROL\","
                + "\"contract\":\"C\",\"function\":\"f\",\"riskLine\":1,\"riskOperation\":\"WRITE\",\"reason\":\"待核查\",\"evidenceIds\":[]}]}");
            var request = directory.resolve("request.json");
            for (int variant = 0; variant < 4; variant++) {
                var input = node.deepCopy();
                if (variant == 1 || variant == 3) input.put("sourceHash", catalog.path("sourceHash").asText());
                if (variant >= 2) input.set("riskCatalog", catalog);
                Files.writeString(request, input.toString());
                var output = new ByteArrayOutputStream();
                int status = HypothesisCli.run(new String[]{"--source", source.toString(), "--request", request.toString(),
                    "--replay-response", raw.toString()}, Map.of(), new PrintStream(output), System.err);
                assertEquals(0, status, "请求变体 " + variant);
                var result = RiskCatalogFixture.MAPPER.readTree(output.toString());
                assertEquals(0, result.path("requestAttempts").asInt());
                assertEquals(variant >= 2, result.path("hypotheses").get(0).has("riskFactId"));
            }
            node.put("不支持的字段", "不能忽略");
            Files.writeString(request, node.toString());
            assertEquals(2, HypothesisCli.run(new String[]{"--source", source.toString(), "--request", request.toString(),
                "--replay-response", raw.toString()}, Map.of(), new PrintStream(new ByteArrayOutputStream()),
                new PrintStream(new ByteArrayOutputStream())));
        } finally {
            try (var files = Files.walk(directory)) {
                for (var path : files.sorted(java.util.Comparator.reverseOrder()).toList()) Files.deleteIfExists(path);
            }
        }
    }
    @Test void separateCliValidatesScopeWithoutChangingLegacyEntry() throws Exception {
        var directory = Files.createTempDirectory("hypothesis-cli-test-");
        try {
            var source = directory.resolve("Contract.sol");
            Files.writeString(source, "contract C { function f() public {} }");
            var request = directory.resolve("request.json");
            Files.writeString(request, """
                {"schemaVersion":"1","modelSource":"contract C { function f() public {} }",
                "scope":"FULL","lineStart":1,"lineEnd":1,"mechanism":"ACCESS_CONTROL",
                "function":"f","context":"","evidenceIds":[]}
                """);
            var output = new ByteArrayOutputStream();
            int status = HypothesisCli.run(new String[]{"--source", source.toString(), "--request", request.toString(),
                "--provider", "fixture"}, Map.of(), new PrintStream(output), System.err,
                (p, s, u) -> new GatewayReply("{\"schemaVersion\":\"2\",\"hypotheses\":[]}", "fixture", "fixture", null, null, 1));
            assertEquals(0, status);
            assertTrue(output.toString().contains("NO_CONFIRMED_FINDINGS"));
            assertEquals(0, AuditCli.run(new String[]{"--help"}, Map.of(), new PrintStream(new ByteArrayOutputStream()), System.err));
        } finally {
            try (var files = Files.walk(directory)) {
                for (var path : files.sorted(java.util.Comparator.reverseOrder()).toList()) Files.deleteIfExists(path);
            }
        }
    }
    @Test void diagnosticOutputKeepsInvalidResponseLocal() throws Exception {
        var directory = Files.createTempDirectory("hypothesis-diagnostic-test-");
        try {
            var source = directory.resolve("Contract.sol");
            Files.writeString(source, "contract C { function f() public {} }");
            var request = directory.resolve("request.json");
            Files.writeString(request, """
                {"schemaVersion":"1","modelSource":"contract C { function f() public {} }",
                "scope":"FULL","lineStart":1,"lineEnd":1,"mechanism":"ACCESS_CONTROL",
                "function":"f","context":"","evidenceIds":[]}
                """);
            var diagnostic = directory.resolve("raw.txt");
            var output = new ByteArrayOutputStream();
            int status = HypothesisCli.run(new String[]{"--source", source.toString(), "--request", request.toString(),
                "--provider", "fixture", "--diagnostic-output", diagnostic.toString()}, Map.of(),
                new PrintStream(output), System.err,
                (p, s, u) -> new GatewayReply("[]", "fixture", "fixture", 8, 4, 1));
            assertEquals(1, status);
            assertEquals("[]", Files.readString(diagnostic));
            assertTrue(output.toString().contains("MODEL_OUTPUT_INVALID"));
        } finally {
            try (var files = Files.walk(directory)) {
                for (var path : files.sorted(java.util.Comparator.reverseOrder()).toList()) Files.deleteIfExists(path);
            }
        }
    }    @Test void localReplayNeverNeedsProviderAndReportsZeroRequests() throws Exception {
        var directory = Files.createTempDirectory("hypothesis-replay-test-");
        try {
            var source = directory.resolve("Contract.sol");
            Files.writeString(source, "contract C { function f() public {} }");
            var request = directory.resolve("request.json");
            Files.writeString(request, """
                {"schemaVersion":"1","modelSource":"contract C { function f() public {} }",
                "scope":"FULL","lineStart":1,"lineEnd":1,"mechanism":"ACCESS_CONTROL",
                "function":"f","context":"","evidenceIds":[]}
                """);
            var raw = directory.resolve("raw.txt");
            Files.writeString(raw, "```json\n{\"schemaVersion\":\"2\",\"hypotheses\":[]}\n```");
            var output = new ByteArrayOutputStream();
            int status = HypothesisCli.run(new String[]{"--source", source.toString(), "--request", request.toString(),
                "--replay-response", raw.toString()}, Map.of(), new PrintStream(output), System.err);
            assertEquals(0, status);
            assertTrue(output.toString().contains("\"requestAttempts\":0"));
        } finally {
            try (var files = Files.walk(directory)) {
                for (var path : files.sorted(java.util.Comparator.reverseOrder()).toList()) Files.deleteIfExists(path);
            }
        }
    }

}
