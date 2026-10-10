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
import java.util.List;
import java.util.TreeMap;
import java.util.regex.Pattern;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;

/** 仅运行本机固定配置的静态工具；空告警不表示合约安全。 */
public final class ToolCli {
    private static final int DIAGNOSTIC_LIMIT = 8192;
    private static final Set<String> SUMMARY_KEYS = Set.of("tools.slither.executable", "tools.slither.solc", "tools.mythril.executable", "tools.slither.solc-remaps", "tools.slither.solc-args");
    private static final Pattern VERSION = Pattern.compile("(?m)^\\s*Version:\\s*(\\d+\\.\\d+\\.\\d+)(?:\\+|\\s|$)");
    private static final Pattern SECRET_KEY = Pattern.compile("api[-_]?key|token|secret|password|authorization", Pattern.CASE_INSENSITIVE);
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
            List<String> dependencyArguments = engine == ToolAnalyzer.Engine.SLITHER ? dependencyArguments(properties) : List.of();
            String command = executable.contains("/") ? Path.of(executable).toAbsolutePath().toString() : executable;
            var runner = new ProcessRunner();
            var versionRun = runner.run(java.util.List.of(command, "--version"), Path.of(System.getProperty("java.io.tmpdir")),
                Duration.ofSeconds(3), 1024);
            String version = versionRun.status() == ProcessRunner.Status.OK ? redact(versionRun.stdout().strip(), properties) : null;
            String compilerPath = engine == ToolAnalyzer.Engine.SLITHER ? properties.getProperty("tools.slither.solc") : null;
            Map<String,Object> compiler = null;
            ProcessRunner.Result compilerRun = null;
            String compilerError = null;
            if (compilerPath != null) {
                Path path = Path.of(compilerPath).toAbsolutePath();
                compiler = new LinkedHashMap<>();
                compiler.put("path", path.toString());
                compiler.put("version", null);
                compiler.put("sha256", null);
                if (!Files.isRegularFile(path) || !Files.isExecutable(path)) {
                    compilerError = "COMPILER_UNAVAILABLE";
                    compilerRun = new ProcessRunner.Result(ProcessRunner.Status.START_ERROR, null, "", "固定编译器不存在或不可执行。", false, true, 0);
                } else {
                    path = path.toRealPath();
                    compilerPath = path.toString();
                    compiler.put("path", compilerPath);
                    compiler.put("sha256", digest(Files.readAllBytes(path)));
                    compilerRun = runner.run(List.of(compilerPath, "--version"), path.getParent(), Duration.ofSeconds(3), DIAGNOSTIC_LIMIT);
                    var match = VERSION.matcher(compilerRun.stdout());
                    if (compilerRun.status() != ProcessRunner.Status.OK || compilerRun.truncated() || !compilerRun.cleanedUp() || !match.find()) {
                        compilerError = "COMPILER_PROBE_FAILED";
                    } else {
                        compiler.put("version", match.group(1));
                    }
                    String afterHash = digest(Files.readAllBytes(path));
                    if (!afterHash.equals(compiler.get("sha256"))) {
                        compiler.put("sha256After", afterHash);
                        compilerError = "ENVIRONMENT_CHANGED";
                    }
                }
            }
            var analyzer = new ToolAnalyzer(runner);
            var result = compilerError == null
                ? analyzer.analyze(engine, command, source, Duration.ofSeconds(engine == ToolAnalyzer.Engine.SLITHER ? 30 : 60), compilerPath, dependencyArguments)
                : new ToolAnalyzer.Result(engine, ToolAnalyzer.Status.PROCESS_ERROR, new ObjectMapper().createArrayNode(), compilerRun);
            if (compiler != null && compilerError == null && !compiler.get("sha256").equals(executableHash(compilerPath))) {
                compiler.put("sha256After", executableHash(compilerPath));
                compilerError = "ENVIRONMENT_CHANGED";
                result = new ToolAnalyzer.Result(engine, ToolAnalyzer.Status.PROCESS_ERROR, new ObjectMapper().createArrayNode(), result.process());
            }
            Map<String,Object> output = new LinkedHashMap<>();
            output.put("engine", result.engine().name());
            output.put("sourceHash", digest(source.getBytes(StandardCharsets.UTF_8)));
            output.put("sourceFile", "Contract.sol");
            output.put("status", result.status().name());
            output.put("issues", redactNode(result.issues(), properties));
            output.put("durationMs", result.process().durationMs());
            output.put("version", version);
            output.put("compiler", compiler);
            output.put("compilerProcess", compilerRun == null ? null : diagnostic(compilerRun, properties));
            output.put("process", diagnostic(result.process(), properties));
            output.put("errorCategory", compilerError == null ? errorCategory(result) : compilerError);
            var compilationArguments = new java.util.ArrayList<String>();
            if (compilerPath != null) compilationArguments.addAll(List.of("--solc", compilerPath));
            compilationArguments.addAll(dependencyArguments);
            output.put("compilationArguments", compilationArguments);
            Map<String,Object> summary = new TreeMap<>();
            Map<String,Object> full = new TreeMap<>();
            for (String key : properties.stringPropertyNames()) {
                full.put(key, properties.getProperty(key));
                if (SUMMARY_KEYS.contains(key)) summary.put(key, redact(properties.getProperty(key), properties));
            }
            output.put("configSummary", summary);
            Map<String,Object> binding = new TreeMap<>();
            binding.put("configuration", full);
            binding.put("compiler", compiler);
            binding.put("executable", command);
            binding.put("executableHash", executableHash(command));
            binding.put("version", version);
            binding.put("compilationArguments", compilationArguments);
            output.put("configHash", digest(new ObjectMapper().writeValueAsBytes(binding)));
            out.println(new ObjectMapper().writeValueAsString(output));
            return result.status() == ToolAnalyzer.Status.OK ? 0 : 1;
        } catch (Exception e) {
            err.println("工具输入或配置无效；未执行安全判定。");
            return 2;
        }
    }

    private static String digest(byte[] bytes) throws Exception {
        return java.util.HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));
    }

    private static String executableHash(String executable) throws Exception {
        if (!executable.contains("/")) return null;
        Path path = Path.of(executable);
        return Files.isRegularFile(path) ? digest(Files.readAllBytes(path)) : null;
    }

    private static Map<String,Object> diagnostic(ProcessRunner.Result process, Properties properties) {
        Map<String,Object> result = new LinkedHashMap<>();
        result.put("status", process.status().name());
        result.put("exitCode", process.exitCode());
        result.put("durationMs", process.durationMs());
        result.put("stdout", bounded(redact(process.stdout(), properties)));
        result.put("stderr", bounded(redact(process.stderr(), properties)));
        result.put("truncated", process.truncated());
        result.put("diagnosticsTruncated", process.truncated() || process.stdout().length() > DIAGNOSTIC_LIMIT || process.stderr().length() > DIAGNOSTIC_LIMIT);
        result.put("cleanedUp", process.cleanedUp());
        return result;
    }

    private static String bounded(String text) {
        return text.substring(0, Math.min(text.length(), DIAGNOSTIC_LIMIT));
    }

    private static String redact(String text, Properties properties) {
        for (String key : properties.stringPropertyNames()) {
            String secret = properties.getProperty(key);
            if (SECRET_KEY.matcher(key).find() && !secret.isEmpty()) text = text.replace(secret, "<redacted>");
        }
        return text.replaceAll("(?i)(https?://)[^\\s/@]+(?::[^\\s/@]*)?@", "$1<redacted>@")
            .replaceAll("(?i)\\b(authorization\\s*[:=]\\s*(?:bearer\\s+)?|bearer\\s+)[^\\s,;\"']+", "$1<redacted>")
            .replaceAll("(?i)((?:api[-_]?key|token|secret|password)[\"']?\\s*[=:]\\s*[\"']?)[^\\s&,;\"']+", "$1<redacted>");
    }

    private static com.fasterxml.jackson.databind.JsonNode redactNode(com.fasterxml.jackson.databind.JsonNode node, Properties properties) {
        if (node.isTextual()) return com.fasterxml.jackson.databind.node.TextNode.valueOf(redact(node.textValue(), properties));
        if (node.isArray()) {
            var array = new ObjectMapper().createArrayNode();
            for (var value : node) array.add(redactNode(value, properties));
            return array;
        }
        if (node.isObject()) {
            var object = new ObjectMapper().createObjectNode();
            node.properties().forEach(field -> object.set(field.getKey(),
                SECRET_KEY.matcher(field.getKey()).find() ? com.fasterxml.jackson.databind.node.TextNode.valueOf("<redacted>")
                : redactNode(field.getValue(), properties)));
            return object;
        }
        return node;
    }

    private static List<String> dependencyArguments(Properties properties) {
        var result = new java.util.ArrayList<String>();
        String arguments = properties.getProperty("tools.slither.solc-args", "").strip();
        String remaps = properties.getProperty("tools.slither.solc-remaps", "").strip();
        if (!arguments.isEmpty()) {
            String[] tokens = arguments.split("\\s+");
            for (int index = 0; index < tokens.length; index++) {
                String token = tokens[index];
                if ("--optimize".equals(token)) continue;
                if (!Set.of("--base-path", "--include-path", "--allow-paths", "--optimize-runs", "--evm-version").contains(token)
                    || ++index >= tokens.length) throw new IllegalArgumentException();
                String value = tokens[index];
                if (!value.matches("[A-Za-z0-9_./@,:+-]+")) throw new IllegalArgumentException();
                if (Set.of("--base-path", "--include-path", "--allow-paths").contains(token)) validateDirectories(value);
                if ("--optimize-runs".equals(token) && (!value.matches("[0-9]+") || Long.parseLong(value) < 1 || Long.parseLong(value) > 1_000_000))
                    throw new IllegalArgumentException();
                if ("--evm-version".equals(token) && !Set.of("homestead", "tangerineWhistle", "spuriousDragon", "byzantium",
                    "constantinople", "petersburg", "istanbul", "berlin", "london", "paris", "shanghai", "cancun", "prague", "osaka").contains(value))
                    throw new IllegalArgumentException();
            }
            result.addAll(List.of("--solc-args", arguments));
        }
        if (!remaps.isEmpty()) {
            for (String remap : remaps.split("\\s+")) {
                String[] pair = remap.split("=", -1);
                if (pair.length != 2 || !pair[0].matches("[A-Za-z0-9_./@:-]+") || !pair[1].matches("[A-Za-z0-9_./@:+-]+"))
                    throw new IllegalArgumentException();
                validateDirectories(pair[1]);
            }
            result.addAll(List.of("--solc-remaps", remaps));
        }
        return List.copyOf(result);
    }

    private static void validateDirectories(String value) {
        for (String item : value.split(",", -1)) {
            Path path = Path.of(item);
            if (!path.isAbsolute() || !Files.isDirectory(path)) throw new IllegalArgumentException();
        }
    }

    private static String errorCategory(ToolAnalyzer.Result result) {
        if (result.status() == ToolAnalyzer.Status.OK) return null;
        String diagnostic = (result.process().stdout() + "\n" + result.process().stderr()).toLowerCase(java.util.Locale.ROOT);
        if (diagnostic.contains("requires different compiler version") || diagnostic.contains("compiler version mismatch")) return "COMPILER_MISMATCH";
        if (diagnostic.contains("file not found") || diagnostic.matches("(?s).*source .+ not found.*") || diagnostic.contains("unresolved import")) return "MISSING_IMPORT";
        if (diagnostic.contains("invalid solc compilation") || diagnostic.contains("solidity compilation failed")
            || diagnostic.contains("compilation failed")) return "COMPILATION_FAILED";
        if (result.process().status() == ProcessRunner.Status.START_ERROR) return "TOOL_UNAVAILABLE";
        return result.status().name();
    }
}
