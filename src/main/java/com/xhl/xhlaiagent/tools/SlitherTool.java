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
import java.util.List;
import java.util.concurrent.TimeUnit;
import java.util.stream.Collectors;

/**
 * Slither 静态分析引擎
 */
@Slf4j
public class SlitherTool {
    private final ObjectMapper objectMapper = new ObjectMapper();

    @Tool(description = "静态代码分析工具。输入Solidity合约代码，调用本地Slither引擎进行漏洞扫描，返回结构化的漏洞报告。")
    public String slitherAnalyze(@ToolParam(description = "完整的智能合约源代码") String contractCode) {
        Path tempDir = null;
        try {
            // ================= 修改点 1: 清洗 Markdown 标记 =================
            // 防止 LLM 传入 ```solidity 开头的代码块导致编译失败
            if (contractCode.contains("```")) {
                contractCode = contractCode.replaceAll("```[a-zA-Z]*", "").replace("```", "");
            }
            // ============================================================

            // 1. 创建临时文件
            tempDir = Files.createTempDirectory("slither_audit_local_");
            Path contractPath = tempDir.resolve("contract.sol");
            Files.writeString(contractPath, contractCode, StandardCharsets.UTF_8);

            log.info("执行本地 Slither 分析，工作目录: {}", tempDir);

            // 2. 构建命令
            // 注意：这里文件名只写 contract.sol，因为下面设置了 directory
            ProcessBuilder builder = new ProcessBuilder(
                    "slither",
                    "contract.sol",
                    "--json", "-"
            );

            // ================= 修改点 2: 设置工作目录 =================
            // 让 Slither 在临时目录下运行，产生的 crytic-export 垃圾文件也会在那，随临时目录一起删除
            builder.directory(tempDir.toFile());
            // =======================================================

            builder.redirectErrorStream(true);

            Process process = builder.start();

            // 3. 读取输出
            String output;
            try (BufferedReader reader = new BufferedReader(new InputStreamReader(process.getInputStream(), StandardCharsets.UTF_8))) {
                output = reader.lines().collect(Collectors.joining("\n"));
            }

            boolean finished = process.waitFor(30, TimeUnit.SECONDS);
            if (!finished) {
                process.destroyForcibly();
                return "错误：分析超时 (Time Limit Exceeded)";
            }

            // 4. 解析结果
            return parseSlitherOutput(output);

        } catch (Exception e) {
            log.error("Slither 本地调用失败", e);
            return "系统内部错误：无法执行静态分析 - " + e.getMessage();
        } finally {
            // 清理临时文件
            deleteDirectory(tempDir.toFile());
        }
    }

    /**
     * 数据清洗层：将庞大的 JSON 转换为 LLM 易读的摘要
     */
    private String parseSlitherOutput(String rawOutput) {
        try {
            // 预判编译错误 (如果输出里包含了 Error 且没有 JSON 结构)
            if (rawOutput.contains("Error:") && !rawOutput.contains("{")) {
                return "Slither 运行失败 (编译错误): \n" + rawOutput.substring(0, Math.min(rawOutput.length(), 300));
            }

            int jsonStart = rawOutput.indexOf("{");
            int jsonEnd = rawOutput.lastIndexOf("}");

            if (jsonStart == -1 || jsonEnd == -1) {
                return "分析失败（无法提取 JSON 报告）：\n" + rawOutput.substring(0, Math.min(rawOutput.length(), 500));
            }

            String jsonString = rawOutput.substring(jsonStart, jsonEnd + 1);
            JsonNode root = objectMapper.readTree(jsonString);

            JsonNode detectors = root.path("results").path("detectors");

            if (detectors.isMissingNode() || detectors.isEmpty()) {
                return "✅ Slither 安全扫描完成：未发现已知的高危漏洞。";
            }

            StringBuilder report = new StringBuilder("🚨 Slither 发现以下潜在漏洞：\n");
            boolean foundIssues = false;

            for (JsonNode issue : detectors) {
                String impact = issue.path("impact").asText();
                String check = issue.path("check").asText();
                String description = issue.path("description").asText();

                // 过滤策略
                if (List.of("High", "Medium").contains(impact)) {
                    foundIssues = true;
                    report.append(String.format("- [%s] 类型: %s\n  描述: %s\n", impact, check, simplifyDescription(description)));
                }
            }

            if (!foundIssues) {
                return "⚠️ 扫描完成：仅发现少量低级别风险或优化建议，无高危漏洞。";
            }

            return report.toString();

        } catch (Exception e) {
            log.warn("JSON 解析失败", e);
            return "分析完成，但解析报告失败。可能是 Slither 输出格式异常。";
        }
    }

    private String simplifyDescription(String desc) {
        String simplified = desc.replaceAll("\\r\\n|\\r|\\n", " ");
        if (simplified.length() > 150) {
            return simplified.substring(0, 150) + "...";
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