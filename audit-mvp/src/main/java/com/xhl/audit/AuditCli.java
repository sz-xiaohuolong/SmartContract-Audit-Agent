package com.xhl.audit;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HashMap;
import java.util.Map;
import java.util.Properties;
import java.util.Set;

/** 显式传入源码和配置才调用模型；无参数时只显示帮助。 */
public final class AuditCli {
    private AuditCli() {}
    public static void main(String[] args) { System.exit(run(args, System.getenv(), System.out, System.err)); }

    public static int run(String[] args, Map<String, String> environment, PrintStream out, PrintStream err) {
        if (args.length > 0 && "--retrieval".equals(args[0]))
            return com.xhl.audit.retrieval.RetrievalCli.run(java.util.Arrays.copyOfRange(args, 1, args.length), out, err);
        if (args.length == 0 || (args.length == 1 && "--help".equals(args[0]))) {
            out.println("用法：java -jar audit-mvp.jar --source 合约.sol --config providers.properties [--provider ark]");
            out.println("仅显式执行时调用一次模型；退出码：0 完成，1 审计失败，2 输入或配置无效。");
            return 0;
        }
        try {
            Map<String, String> options = new HashMap<>();
            Set<String> allowed = Set.of("--source", "--config", "--provider");
            for (int i = 0; i < args.length; i += 2) {
                if (!allowed.contains(args[i]) || i + 1 >= args.length || options.putIfAbsent(args[i], args[i + 1]) != null)
                    throw new IllegalArgumentException();
            }
            if (!options.containsKey("--source") || !options.containsKey("--config")) throw new IllegalArgumentException();
            Path sourcePath = Path.of(options.get("--source"));
            // 有限读取，避免尺寸检查和读取之间的文件变化绕过上限。
            byte[] bytes;
            try (var input = Files.newInputStream(sourcePath)) { bytes = input.readNBytes(1_048_577); }
            if (bytes.length > 1_048_576) throw new IllegalArgumentException();
            String source = StandardCharsets.UTF_8.newDecoder().decode(java.nio.ByteBuffer.wrap(bytes)).toString();
            if (source.isBlank()) throw new IllegalArgumentException();
            Properties properties = new Properties();
            try (var reader = Files.newBufferedReader(Path.of(options.get("--config")), StandardCharsets.UTF_8)) { properties.load(reader); }
            var registry = new ProviderRegistry(properties, environment);
            var provider = registry.resolve(options.get("--provider"));
            var result = new AuditService(new SpringAiGateway(registry)).audit(source, provider.name());
            out.println(new ObjectMapper().writeValueAsString(result));
            return result.status() == AuditResult.Status.COMPLETED ? 0 : 1;
        } catch (Exception e) {
            err.println("输入或配置无效：请检查参数、UTF-8 源码（不超过 1 MiB）、供应商配置和 API Key。");
            return 2;
        }
    }
}
