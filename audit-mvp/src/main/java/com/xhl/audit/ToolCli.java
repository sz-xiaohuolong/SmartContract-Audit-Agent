package com.xhl.audit;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.PrintStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Properties;
import java.util.Set;

/** 仅运行本机固定配置的静态工具；空告警不表示合约安全。 */
public final class ToolCli {
    private ToolCli() {}
    public static int run(String[] args, PrintStream out, PrintStream err) {
        try {
            var options = HypothesisCli.options(args, Set.of("--source", "--config", "--engine"));
            if (!options.containsKey("--source") || !options.containsKey("--config")) throw new IllegalArgumentException();
            String source = HypothesisCli.read(options.get("--source"), 1_048_576);
            if (source.isBlank()) throw new IllegalArgumentException();
            Properties properties = new Properties();
            try (var reader = Files.newBufferedReader(Path.of(options.get("--config")))) { properties.load(reader); }
            String selected = options.getOrDefault("--engine", "slither");
            ToolAnalyzer.Engine engine = switch (selected) {
                case "slither" -> ToolAnalyzer.Engine.SLITHER;
                case "mythril" -> ToolAnalyzer.Engine.MYTHRIL;
                default -> throw new IllegalArgumentException();
            };
            String executable = properties.getProperty("tools." + selected + ".executable");
            if (executable == null || executable.isBlank()) throw new IllegalArgumentException();
            String command = executable.contains("/") ? Path.of(executable).toAbsolutePath().toString() : executable;
            var runner = new ProcessRunner();
            var versionRun = runner.run(java.util.List.of(command, "--version"), Path.of(System.getProperty("java.io.tmpdir")),
                Duration.ofSeconds(3), 1024);
            String version = versionRun.status() == ProcessRunner.Status.OK ? versionRun.stdout().strip() : null;
            var result = new ToolAnalyzer(runner).analyze(engine, command, source,
                Duration.ofSeconds(engine == ToolAnalyzer.Engine.SLITHER ? 30 : 60));
            Map<String,Object> output = new LinkedHashMap<>();
            output.put("engine", result.engine().name());
            output.put("sourceHash", java.util.HexFormat.of().formatHex(java.security.MessageDigest.getInstance("SHA-256")
                .digest(source.getBytes(java.nio.charset.StandardCharsets.UTF_8))));
            output.put("sourceFile", "Contract.sol");
            output.put("status", result.status().name());
            output.put("issues", result.issues());
            output.put("durationMs", result.process().durationMs());
            output.put("version", version);
            out.println(new ObjectMapper().writeValueAsString(output));
            return result.status() == ToolAnalyzer.Status.OK ? 0 : 1;
        } catch (Exception e) {
            err.println("工具输入或配置无效；未执行安全判定。");
            return 2;
        }
    }
}
