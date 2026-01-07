package com.xhl.xhlaiagent.tools;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.extern.slf4j.Slf4j;
import org.springframework.ai.tool.annotation.Tool;
import org.springframework.ai.tool.annotation.ToolParam;

import java.io.BufferedReader;
import java.io.File;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.TimeUnit;
import java.util.stream.Collectors;

/**
 * Mythril 符号执行分析引擎 (动态/符号执行)
 */
@Slf4j
public class MythrilTool {
    private final ObjectMapper objectMapper = new ObjectMapper();

    @Tool(description = "Mythril符号执行工具。当静态分析(Slither)结果不确定，或需要检测复杂逻辑漏洞(如整数溢出、未检查的返回值)时使用。耗时较长，精准度高。")
    public String mythrilAnalyze(@ToolParam(description = "完整的智能合约源代码") String contractCode) {
        Path tempDir = null;
        try {
            // 1. 清洗 Markdown
            if (contractCode.contains("```")) {
                contractCode = contractCode.replaceAll("```[a-zA-Z]*", "").replace("```", "");
            }

            // 2. 创建临时文件
            tempDir = Files.createTempDirectory("mythril_audit_local_");
            Path contractPath = tempDir.resolve("contract.sol");
            Files.writeString(contractPath, contractCode, StandardCharsets.UTF_8);

            log.info("执行 Mythril 符号执行分析，目录: {}", tempDir);
            //激活虚拟环境
            // 定义 myth 在 venv 中的绝对路径，todo后面可以替换到配置文件中
            String mythExecutable = "/Users/daiyifei/Documents/code/SmartContract-agent/venv/bin/myth";

            // 3. 构建命令
            // myth analyze contract.sol --execution-timeout 60 -o json
            ProcessBuilder builder = new ProcessBuilder(
                    mythExecutable,
                    "analyze",
                    "contract.sol",
                    "--execution-timeout", "60", // 强制限制符号执行时间为 60 秒
                    "-o", "json"
            );

            builder.directory(tempDir.toFile());
            builder.redirectErrorStream(true);

            Process process = builder.start();

            // 4. 读取输出
            String output;
            try (BufferedReader reader = new BufferedReader(new InputStreamReader(process.getInputStream(), StandardCharsets.UTF_8))) {
                output = reader.lines().collect(Collectors.joining("\n"));
            }

            // Java 进程等待超时设置稍长一点，给 Mythril 缓冲
            boolean finished = process.waitFor(90, TimeUnit.SECONDS);
            if (!finished) {
                process.destroyForcibly();
                return "错误：Mythril 分析超时 (已强制终止)。符号执行极其耗时，请尝试简化代码片段。";
            }

            return parseMythrilOutput(output);

        } catch (Exception e) {
            log.error("Mythril 本地调用失败", e);
            return "系统内部错误：无法执行 Mythril 分析 - " + e.getMessage();
        } finally {
            deleteDirectory(tempDir.toFile());
        }
    }

    private String parseMythrilOutput(String rawOutput) {
        try {
            // 预判错误
            if ((rawOutput.contains("Error") || rawOutput.contains("Traceback")) && !rawOutput.contains("\"issues\"")) {
                return "Mythril 运行失败 (编译或环境错误): \n" + rawOutput.substring(0, Math.min(rawOutput.length(), 300));
            }

            // Mythril 的 JSON 输出通常在最后，但也可能混杂日志，寻找 JSON 起止点
            int jsonStart = rawOutput.indexOf("{");
            int jsonEnd = rawOutput.lastIndexOf("}");

            if (jsonStart == -1 || jsonEnd == -1) {
                // Mythril 如果没发现漏洞，有时只输出文本，不输出 JSON，需特殊处理
                if (rawOutput.contains("The analysis was completed successfully") && !rawOutput.contains("issues")) {
                    return "✅ Mythril 深度验证完成：在指定时间内未发现可利用的漏洞路径。";
                }
                return "分析失败（无法提取 JSON 报告）：\n" + rawOutput.substring(0, Math.min(rawOutput.length(), 500));
            }

            String jsonString = rawOutput.substring(jsonStart, jsonEnd + 1);
            JsonNode root = objectMapper.readTree(jsonString);
            JsonNode issues = root.path("issues");

            if (issues.isMissingNode() || issues.isEmpty()) {
                return "✅ Mythril 深度验证完成：未发现已知的高危漏洞。";
            }

            StringBuilder report = new StringBuilder("🧪 Mythril 符号执行报告 (高精准度):\n");
            for (JsonNode issue : issues) {
                String title = issue.path("swc-title").asText();
                String severity = issue.path("severity").asText();
                String description = issue.path("description").asText();

                // Mythril 的 description 通常很长，包含汇编信息，需要精简
                report.append(String.format("""
                        ---
                        🔴 漏洞: %s
                        ⚠️ 级别: %s
                        📝 描述: %s
                        """, title, severity, simplifyDescription(description)));
            }

            return report.toString();

        } catch (Exception e) {
            log.warn("Mythril JSON 解析失败", e);
            return "分析完成，但解析 Mythril 报告失败。";
        }
    }

    private String simplifyDescription(String desc) {
        // 移除 Markdown 格式和过长的换行
        String simplified = desc.replaceAll("\\r\\n|\\r|\\n", " ").replaceAll("\\s+", " ");
        if (simplified.length() > 300) {
            return simplified.substring(0, 300) + "...";
        }
        return simplified;
    }

    private void deleteDirectory(File file) {
        if (file != null && file.exists()) {
            File[] files = file.listFiles();
            if (files != null) {
                for (File f : files) deleteDirectory(f);
            }
            file.delete();
        }
    }
}