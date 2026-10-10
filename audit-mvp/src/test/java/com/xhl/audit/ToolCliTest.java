package com.xhl.audit;

import org.junit.jupiter.api.Test;
import java.io.ByteArrayOutputStream;
import java.io.PrintStream;
import java.nio.file.Files;
import static org.junit.jupiter.api.Assertions.*;

class ToolCliTest {
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
