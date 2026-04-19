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
                return buildToolResponse("timeout", List.of(), "Time limit exceeded", output);
            }

            // 4. 解析结果
            return parseSlitherOutput(output);

        } catch (Exception e) {
            log.error("Slither 本地调用失败", e);
            return buildToolResponse("execution_error", List.of(), e.getMessage(), null);
        } finally {
            // 清理临时文件
            deleteDirectory(tempDir == null ? null : tempDir.toFile());
        }
    }

    /**
     * 数据清洗层：将庞大的 JSON 转换为 LLM 易读的摘要
     */
    private String parseSlitherOutput(String rawOutput) {
        try {
            // 预判编译错误 (如果输出里包含了 Error 且没有 JSON 结构)
            if (rawOutput.contains("Error:") && !rawOutput.contains("{")) {
                return buildToolResponse("compile_error", List.of(), "Compile error", rawOutput);
            }

            int jsonStart = rawOutput.indexOf("{");
            int jsonEnd = rawOutput.lastIndexOf("}");

            if (jsonStart == -1 || jsonEnd == -1) {
                return buildToolResponse("parse_error", List.of(), "Unable to extract Slither JSON report", rawOutput);
            }

            String jsonString = rawOutput.substring(jsonStart, jsonEnd + 1);
            JsonNode root = objectMapper.readTree(jsonString);

            JsonNode detectors = root.path("results").path("detectors");

            if (detectors.isMissingNode() || detectors.isEmpty()) {
                return buildToolResponse("ok", List.of(), null, null);
            }

            List<Map<String, Object>> issues = new ArrayList<>();
            for (JsonNode issue : detectors) {
                Map<String, Object> item = new LinkedHashMap<>();
                item.put("check", issue.path("check").asText(""));
                item.put("impact", issue.path("impact").asText(""));
                item.put("confidence", issue.path("confidence").asText(""));
                item.put("description", simplifyDescription(issue.path("description").asText("")));
                item.put("line", extractPrimaryLine(issue));
                item.put("contract", extractContractName(issue));
                issues.add(item);
            }

            return buildToolResponse("ok", issues, null, null);

        } catch (Exception e) {
            log.warn("JSON 解析失败", e);
            return buildToolResponse("parse_error", List.of(), e.getMessage(), rawOutput);
        }
    }

    private Integer extractPrimaryLine(JsonNode issue) {
        JsonNode elements = issue.path("elements");
        if (!elements.isArray() || elements.isEmpty()) {
            return null;
        }

        JsonNode sourceMapping = elements.get(0).path("source_mapping").path("lines");
        if (sourceMapping.isArray() && !sourceMapping.isEmpty()) {
            return sourceMapping.get(0).asInt();
        }
        return null;
    }

    private String extractContractName(JsonNode issue) {
        JsonNode elements = issue.path("elements");
        if (!elements.isArray() || elements.isEmpty()) {
            return "";
        }
        return elements.get(0).path("name").asText("");
    }

    private String buildToolResponse(String status, List<Map<String, Object>> issues, String parseError, String stdoutExcerpt) {
        try {
            Map<String, Object> payload = new LinkedHashMap<>();
            payload.put("engine", "slither");
            payload.put("status", status);
            payload.put("issues", issues);
            payload.put("parseError", parseError);
            payload.put("stdoutExcerpt", stdoutExcerpt == null ? null : simplifyDescription(stdoutExcerpt));
            return objectMapper.writeValueAsString(payload);
        } catch (Exception e) {
            log.warn("构建 Slither 结构化输出失败", e);
            return "{\"engine\":\"slither\",\"status\":\"serialization_error\",\"issues\":[],\"parseError\":\""
                    + simplifyDescription(e.getMessage()) + "\",\"stdoutExcerpt\":null}";
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
