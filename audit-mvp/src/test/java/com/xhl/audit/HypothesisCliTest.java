package com.xhl.audit;

import org.junit.jupiter.api.Test;
import java.io.ByteArrayOutputStream;
import java.io.PrintStream;
import java.nio.file.Files;
import java.util.Map;
import static org.junit.jupiter.api.Assertions.*;

class HypothesisCliTest {
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
