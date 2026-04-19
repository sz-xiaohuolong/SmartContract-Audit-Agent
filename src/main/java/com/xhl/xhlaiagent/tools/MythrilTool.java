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
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
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
                return buildToolResponse("timeout", List.of(), "Time limit exceeded", output);
            }

            return parseMythrilOutput(output);

        } catch (Exception e) {
            log.error("Mythril 本地调用失败", e);
            return buildToolResponse("execution_error", List.of(), e.getMessage(), null);
        } finally {
            deleteDirectory(tempDir == null ? null : tempDir.toFile());
        }
    }

    private String parseMythrilOutput(String rawOutput) {
        try {
            // 预判错误
            if ((rawOutput.contains("Error") || rawOutput.contains("Traceback")) && !rawOutput.contains("\"issues\"")) {
                return buildToolResponse("compile_error", List.of(), "Compile or environment error", rawOutput);
            }

            // Mythril 的 JSON 输出通常在最后，但也可能混杂日志，寻找 JSON 起止点
            int jsonStart = rawOutput.indexOf("{");
            int jsonEnd = rawOutput.lastIndexOf("}");

            if (jsonStart == -1 || jsonEnd == -1) {
                // Mythril 如果没发现漏洞，有时只输出文本，不输出 JSON，需特殊处理
                if (rawOutput.contains("The analysis was completed successfully") && !rawOutput.contains("issues")) {
                    return buildToolResponse("ok", List.of(), null, null);
                }
                return buildToolResponse("parse_error", List.of(), "Unable to extract Mythril JSON report", rawOutput);
            }

            String jsonString = rawOutput.substring(jsonStart, jsonEnd + 1);
            JsonNode root = objectMapper.readTree(jsonString);
            JsonNode issues = root.path("issues");
            if (issues.isMissingNode() || issues.isEmpty()) {
                return buildToolResponse("ok", List.of(), null, null);
            }

            List<Map<String, Object>> structuredIssues = new ArrayList<>();
            for (JsonNode issue : issues) {
                Map<String, Object> structured = new LinkedHashMap<>();
                structured.put("title", issue.path("title").asText(""));
                structured.put("severity", issue.path("severity").asText(""));
                structured.put("swcId", issue.path("swc-id").asText(""));
                structured.put("contract", issue.path("contract").asText(""));
                structured.put("function", issue.path("function").asText(""));
                structured.put("line", issue.path("lineno").isMissingNode() ? null : issue.path("lineno").asInt(-1));
                structured.put("description", simplifyDescription(issue.path("description").asText("")));
                structuredIssues.add(structured);
            }

            return buildToolResponse("ok", structuredIssues, null, null);

        } catch (Exception e) {
            log.warn("Mythril JSON 解析失败", e);
            return buildToolResponse("parse_error", List.of(), e.getMessage(), rawOutput);
        }
    }

    private String buildToolResponse(String status, List<Map<String, Object>> issues, String parseError, String stdoutExcerpt) {
        try {
            Map<String, Object> payload = new LinkedHashMap<>();
            payload.put("engine", "mythril");
            payload.put("status", status);
            payload.put("issues", issues);
            payload.put("parseError", parseError);
            payload.put("stdoutExcerpt", stdoutExcerpt == null ? null : simplifyDescription(stdoutExcerpt));
            return objectMapper.writeValueAsString(payload);
        } catch (Exception e) {
            log.warn("构建 Mythril 结构化输出失败", e);
            return "{\"engine\":\"mythril\",\"status\":\"serialization_error\",\"issues\":[],\"parseError\":\""
                    + simplifyDescription(e.getMessage()) + "\",\"stdoutExcerpt\":null}";
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
