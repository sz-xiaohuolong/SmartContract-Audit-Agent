package com.xhl.audit;

import org.junit.jupiter.api.Test;
import java.io.ByteArrayOutputStream;
import java.io.PrintStream;
import java.nio.file.Files;
import java.nio.file.Path;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.io.TempDir;
import static org.junit.jupiter.api.Assertions.*;

class ToolCliTest {
    @TempDir Path directory;

    private JsonNode run(String toolBody, String compilerBody, String extraConfiguration) throws Exception {
        Path source = directory.resolve("Source.sol");
        Files.writeString(source, "pragma solidity ^0.4.0; contract C {}\n");
        Path tool = directory.resolve("tool.sh");
        Files.writeString(tool, "#!/bin/sh\nif [ \"$1\" = \"--version\" ]; then echo fixture-1; exit 0; fi\n" + toolBody);
        assertTrue(tool.toFile().setExecutable(true));
        Path compiler = directory.resolve("solc.sh");
        Files.writeString(compiler, "#!/bin/sh\n" + compilerBody);
        assertTrue(compiler.toFile().setExecutable(true));
        Path config = directory.resolve("tools.properties");
        Files.writeString(config, "tools.slither.executable=" + tool + "\ntools.slither.solc=" + compiler + "\n" + extraConfiguration);
        var output = new ByteArrayOutputStream();
        var errors = new ByteArrayOutputStream();
        int code = ToolCli.run(new String[]{"--source", source.toString(), "--config", config.toString()},
            new PrintStream(output), new PrintStream(errors));
        assertNotEquals(2, code, errors.toString());
        return new ObjectMapper().readTree(output.toString());
    }

    @Test void passesAndBindsExactCompilerBinaryWithoutChangingLegacyFields() throws Exception {
        var result = run("found=0\nwhile [ \"$#\" -gt 0 ]; do\n"
            + " if [ \"$1\" = \"--solc\" ]; then shift; [ \"$1\" = \"" + directory.toRealPath() + "/solc.sh\" ] || exit 9; found=1; fi\n"
            + " shift\ndone\n[ \"$found\" = 1 ] || exit 8\necho '{\"success\":true,\"results\":{\"detectors\":[]}}'\n",
            "echo 'Version: 0.4.25+commit.fixture'\n", "");
        assertEquals("OK", result.path("status").asText());
        assertEquals("0.4.25", result.path("compiler").path("version").asText());
        Path compiler = directory.resolve("solc.sh").toRealPath();
        assertEquals(compiler.toString(), result.path("compiler").path("path").asText());
        String digest = java.util.HexFormat.of().formatHex(java.security.MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(compiler)));
        assertEquals(digest, result.path("compiler").path("sha256").asText());
        assertEquals(0, result.path("process").path("exitCode").asInt(-1));
        assertTrue(result.path("compilationArguments").toString().contains("--solc"));
        assertEquals("Contract.sol", result.path("sourceFile").asText());
        assertEquals("fixture-1", result.path("version").asText());
    }

    @Test void preservesNonzeroCompilerDiagnosticWithSecretRedaction() throws Exception {
        var result = run("echo 'Source file requires different compiler version' >&2\n"
            + "echo 'api_key=fixture-secret https://user:password@example.invalid/?token=secret-token' >&2\nexit 7\n",
            "echo 'Version: 0.4.25+commit.fixture'\n", "providers.ark.api-key=fixture-secret\n");
        assertEquals("PROCESS_ERROR", result.path("status").asText());
        assertEquals("COMPILER_MISMATCH", result.path("errorCategory").asText());
        assertEquals(7, result.path("process").path("exitCode").asInt());
        assertTrue(result.path("process").path("stderr").asText().contains("different compiler version"));
        for (String secret : new String[]{"fixture-secret", "password", "secret-token"})
            assertFalse(result.toString().contains(secret));
        assertFalse(result.path("configSummary").toString().contains("providers"));
    }

    @Test void categorizesMissingImportsEvenWithJsonToolFailure() throws Exception {
        var result = run("echo '{\"success\":false,\"error\":\"Source dependency.sol not found: File not found.\"}'\n",
            "echo 'Version: 0.4.25+commit.fixture'\n", "");
        assertEquals("TOOL_ERROR", result.path("status").asText());
        assertEquals("MISSING_IMPORT", result.path("errorCategory").asText());
        assertTrue(result.path("process").path("stdout").asText().contains("dependency.sol"));
    }

    @Test void distinguishesSolcCompilationFailureFromToolFailure() throws Exception {
        var compilation = run("echo 'crytic_compile.platform.exceptions.InvalidCompilation: Invalid solc compilation' >&2\n"
            + "echo 'Contract.sol:1: ParserError: Expected identifier' >&2\nexit 1\n",
            "echo 'Version: 0.4.25+commit.fixture'\n", "");
        assertEquals("PROCESS_ERROR", compilation.path("status").asText());
        assertEquals("COMPILATION_FAILED", compilation.path("errorCategory").asText());
        var tool = run("echo '内部工具计算失败' >&2\nexit 1\n",
            "echo 'Version: 0.4.25+commit.fixture'\n", "");
        assertEquals("PROCESS_ERROR", tool.path("errorCategory").asText());
    }

    @Test void configurationHashChangesWhenUnknownPropertyOrCompilerBytesChange() throws Exception {
        String success = "echo '{\"success\":true,\"results\":{\"detectors\":[]}}'\n";
        var first = run(success, "echo 'Version: 0.4.25+commit.fixture'\n", "custom.future=A\n");
        var changedConfig = run(success, "echo 'Version: 0.4.25+commit.fixture'\n", "custom.future=B\n");
        assertNotEquals(first.path("configHash").asText(), changedConfig.path("configHash").asText());
        var changedBinary = run(success, "echo 'Version: 0.4.25+commit.fixture'\n# 新二进制\n", "custom.future=B\n");
        assertNotEquals(changedConfig.path("configHash").asText(), changedBinary.path("configHash").asText());
    }

    @Test void rejectsFailedCompilerProbeBeforeToolExecution() throws Exception {
        var result = run("echo '本应不启动' > \"" + directory.resolve("started") + "\"\n",
            "echo 'token=probe-secret' >&2\nexit 5\n", "");
        assertEquals("COMPILER_PROBE_FAILED", result.path("errorCategory").asText());
        assertFalse(Files.exists(directory.resolve("started")));
        assertFalse(result.toString().contains("probe-secret"));
    }

    @Test void boundsDiagnosticOutputAndMarksTruncation() throws Exception {
        var result = run("i=0\nwhile [ \"$i\" -lt 9000 ]; do printf x >&2; i=$((i+1)); done\nexit 3\n",
            "echo 'Version: 0.4.25+commit.fixture'\n", "");
        assertTrue(result.path("process").path("stderr").asText().length() <= 8192);
        assertTrue(result.path("process").path("diagnosticsTruncated").asBoolean());
    }

    @Test void passesWhitelistedAbsoluteImportConfigurationAsToolArguments() throws Exception {
        String dependencies = directory.toRealPath().toString();
        var result = run("found=0\nwhile [ \"$#\" -gt 0 ]; do\n"
            + " if [ \"$1\" = \"--solc-remaps\" ]; then shift; [ \"$1\" = \"lib/=" + dependencies + "\" ] || exit 10; found=$((found+1)); fi\n"
            + " if [ \"$1\" = \"--solc-args\" ]; then shift; [ \"$1\" = \"--base-path " + dependencies + " --include-path " + dependencies + " --optimize\" ] || exit 11; found=$((found+1)); fi\n"
            + " shift\ndone\n[ \"$found\" = 2 ] || exit 12\necho '{\"success\":true,\"results\":{\"detectors\":[]}}'\n",
            "echo 'Version: 0.4.25+commit.fixture'\n", "tools.slither.solc-remaps=lib/=" + dependencies
            + "\ntools.slither.solc-args=--base-path " + dependencies + " --include-path " + dependencies + " --optimize\n");
        assertEquals("OK", result.path("status").asText());
        assertTrue(result.path("compilationArguments").toString().contains("--include-path"));
        assertTrue(result.path("configSummary").toString().contains("tools.slither.solc-remaps"));
    }

    @Test void rejectsUnapprovedCompilerArgumentsBeforeToolExecution() throws Exception {
        Path source = directory.resolve("Source.sol");
        Files.writeString(source, "contract C {}");
        Path marker = directory.resolve("unexpected");
        Path tool = directory.resolve("tool.sh");
        Files.writeString(tool, "#!/bin/sh\necho called > '" + marker + "'\n");
        assertTrue(tool.toFile().setExecutable(true));
        Path config = directory.resolve("tools.properties");
        Files.writeString(config, "tools.slither.executable=" + tool + "\ntools.slither.solc-args=--output-dir /tmp/unapproved\n");
        assertEquals(2, ToolCli.run(new String[]{"--source", source.toString(), "--config", config.toString()},
            new PrintStream(new ByteArrayOutputStream()), new PrintStream(new ByteArrayOutputStream())));
        assertFalse(Files.exists(marker));
    }

    @Test void redactsStructuredDiagnosticSecretsAndFindingDescriptions() throws Exception {
        var result = run("echo '{\"api_key\":\"structured-secret\"}' >&2\n"
            + "echo '{\"success\":true,\"results\":{\"detectors\":[{\"description\":\"Authorization: Bearer finding-secret\"}]}}'\n",
            "echo 'Version: 0.4.25+commit.fixture'\n", "");
        assertEquals("OK", result.path("status").asText());
        assertFalse(result.toString().contains("structured-secret"));
        assertFalse(result.toString().contains("finding-secret"));
    }

    @Test void rejectsCompilerDriftDuringVersionProbeBeforeLaunchingTool() throws Exception {
        Path marker = directory.resolve("drift-started");
        var result = run("echo called > '" + marker + "'\n",
            "echo 'Version: 0.4.25+commit.fixture'\necho '# 改变二进制' >> \"$0\"\n", "");
        assertEquals("ENVIRONMENT_CHANGED", result.path("errorCategory").asText());
        assertEquals("PROCESS_ERROR", result.path("status").asText());
        assertFalse(Files.exists(marker));
    }

    @Test void rejectsCompilerDriftDuringToolExecutionDespiteSuccessfulJson() throws Exception {
        var result = run("echo '# 工具改变二进制' >> '" + directory.resolve("solc.sh") + "'\n"
            + "echo '{\"success\":true,\"results\":{\"detectors\":[]}}'\n",
            "echo 'Version: 0.4.25+commit.fixture'\n", "");
        assertEquals("ENVIRONMENT_CHANGED", result.path("errorCategory").asText());
        assertEquals("PROCESS_ERROR", result.path("status").asText());
    }

    @Test void localToolEvidenceDoesNotProveSafetyWhenEmpty() throws Exception {
        var directory = Files.createTempDirectory("tool-cli-test-");
        try {
            var source = directory.resolve("C.sol");
            Files.writeString(source, "contract C {}");
            var script = directory.resolve("slither.sh");
            Files.writeString(script, "#!/bin/sh\nif [ \"$1\" = \"--version\" ]; then echo fixture-1; else echo '{\"success\":true,\"results\":{\"detectors\":[]}}'; fi\n");
            assertTrue(script.toFile().setExecutable(true));
            var config = directory.resolve("tools.properties");
            Files.writeString(config, "tools.slither.executable=" + script + "\n");
            var output = new ByteArrayOutputStream();
            int code = ToolCli.run(new String[]{"--source", source.toString(), "--config", config.toString()},
                                   new PrintStream(output), System.err);
            assertEquals(0, code);
            assertTrue(output.toString().contains("\"status\":\"OK\""));
            assertTrue(output.toString().contains("\"issues\":[]"));
            assertTrue(output.toString().contains("\"sourceFile\":\"Contract.sol\""));
            assertTrue(output.toString().contains("\"sourceHash\""));
            assertFalse(output.toString().contains("SAFE"));
            Files.writeString(script, "#!/bin/sh\necho broken-json\n");
            output.reset();
            ToolCli.run(new String[]{"--source", source.toString(), "--config", config.toString()},
                        new PrintStream(output), System.err);
            assertTrue(output.toString().contains("PARSE_ERROR"));
            Files.writeString(script, "#!/bin/sh\nif [ \"$1\" = \"--version\" ]; then echo fixture-1; else echo '{\"success\":true,\"issues\":[]}'; fi\n");
            Files.writeString(config, "tools.slither.executable=" + script + "\ntools.mythril.executable=" + script + "\n");
            output.reset();
            assertEquals(0, ToolCli.run(new String[]{"--source", source.toString(), "--config", config.toString(),
                "--engine", "mythril"}, new PrintStream(output), System.err));
            assertTrue(output.toString().contains("\"engine\":\"MYTHRIL\""));
        } finally {
            try (var files = Files.walk(directory)) {
                for (var path : files.sorted(java.util.Comparator.reverseOrder()).toList()) Files.deleteIfExists(path);
            }
        }
    }
}
