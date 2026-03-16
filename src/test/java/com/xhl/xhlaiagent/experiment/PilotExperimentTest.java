package com.xhl.xhlaiagent.experiment;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.xhl.xhlaiagent.app.SmartContractDetect;
import com.xhl.xhlaiagent.rag.model.SmartContractAnalysisResult;
import jakarta.annotation.Resource;
import lombok.extern.slf4j.Slf4j;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

import java.io.File;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.*;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

@SpringBootTest
@Slf4j
public class PilotExperimentTest {

    @Resource
    private SmartContractDetect detector;

    // 用于手动解析 Vanilla 模式返回的 JSON 字符串
    private final ObjectMapper objectMapper = new ObjectMapper();

    /**
     * 运行模式（一次只跑一个）
     * 用法：mvn test -Dtest=PilotExperimentTest -Dmode=Vanilla
     * 可选：Vanilla / RAG-Only / VeriRAG-Full
     */
    private static final List<String> MODES = List.of("Vanilla", "RAG-Only", "VeriRAG-Full");

    // 定义单次实验记录（新增 vulnerabilityReason）
    record ExperimentRecord(
            String filename,
            String mode,
            boolean hasVuln,
            String vulnerabilityType,
            String vulnerabilityReason,
            long timeMs,
            String rawError, // 记录可能的解析/系统错误
            String peopleAudit // 人工审核
    ) {
    }

    @Test
    void runPilotSingleMode() throws IOException {

        // 0) 读取本次要跑的 mode（默认 Vanilla）
        String mode = System.getProperty("mode", "Vanilla");
        if (!MODES.contains(mode)) {
            log.error("❌ mode 参数非法: {}，可选: {}", mode, MODES);
            return;
        }
        log.info("🧪 Pilot Experiment - Selected Mode = {}", mode);

        // 1) 定位数据集目录
        File datasetDir = new File("src/main/resources/testset/pilot_set");
        if (!datasetDir.exists()) {
            datasetDir = new File("src/test/resources/contracts/pilot_set");
        }
        if (!datasetDir.exists() || datasetDir.listFiles() == null) {
            log.error("❌ 未找到数据集目录: {}", datasetDir.getAbsolutePath());
            return;
        }

        File[] contractFiles = datasetDir.listFiles((dir, name) -> name.endsWith(".sol"));
        if (contractFiles == null || contractFiles.length == 0) {
            log.error("❌ 目录下没有 .sol 文件: {}", datasetDir.getAbsolutePath());
            return;
        }

        log.info("🚀 开始 Pilot 单模式实验，共发现 {} 个样本，模式={}", contractFiles.length, mode);
        List<ExperimentRecord> report = new ArrayList<>();

        // 2) 遍历每个合约（只跑一个 mode）
        for (File file : contractFiles) {
            String filename = file.getName();
            String code = Files.readString(file.toPath());

            log.info("\n========== 处理样本: {} (mode={}) ==========", filename, mode);

            ExperimentRecord r;
            switch (mode) {
                case "Vanilla" -> r = runVanillaTest(filename, code);
                case "RAG-Only" -> r = runStandardTest(filename, "RAG-Only", () -> detector.auditRAGOnly(code));
                case "VeriRAG-Full" ->
                        r = runStandardTest(filename, "VeriRAG-Full", () -> detector.auditFullAgent(code));
                default -> {
                    // 不会到这里
                    r = new ExperimentRecord(filename, mode, false, "InvalidMode", "InvalidMode", 0, "Invalid mode", null);
                }
            }
            report.add(r);
        }

        // 3) 生成 Markdown 报告（只针对本次 mode）
        saveReportToMarkdown(report, mode);
    }

    /**
     * 专门处理 Vanilla：detector.auditVanilla(code) 返回 String JSON 的解析逻辑
     */
    private ExperimentRecord runVanillaTest(String filename, String code) {
        long start = System.currentTimeMillis();
        try {
            String rawJson = detector.auditVanilla(code); // 这里你已改成返回 String
            long duration = System.currentTimeMillis() - start;

            SmartContractAnalysisResult result = parseRawJson(rawJson);

            log.info("✅ [Vanilla] 完成, 耗时: {}ms, hasVuln={}, type={}, reason={}",
                    duration,
                    result.isHasVulnerability(),
                    safeOneLine(result.getVulnerabilityType(), 80),
                    safeOneLine(result.getVulnerabilityReason(), 120)
            );

            return new ExperimentRecord(
                    filename,
                    "Vanilla",
                    result.isHasVulnerability(),
                    nullToNA(result.getVulnerabilityType()),
                    nullToNA(result.getVulnerabilityReason()),
                    duration,
                    null,
                    null
            );

        } catch (Exception e) {
            log.error("❌ [Vanilla] 失败: {}", e.getMessage());
            return new ExperimentRecord(filename, "Vanilla", false,
                    "ParseError", "ParseError", 0, e.getMessage(), null);
        }
    }

    /**
     * 处理 RAG-Only / Full：直接返回 Object（SmartContractAnalysisResult）
     */
    private ExperimentRecord runStandardTest(String filename, String mode, java.util.function.Supplier<SmartContractAnalysisResult> func) {
        long start = System.currentTimeMillis();
        try {
            SmartContractAnalysisResult res = func.get();
            long duration = System.currentTimeMillis() - start;

            log.info("✅ [{}] 完成, 耗时: {}ms, hasVuln={}, type={}, reason={}",
                    mode,
                    duration,
                    res.isHasVulnerability(),
                    safeOneLine(res.getVulnerabilityType(), 80),
                    safeOneLine(res.getVulnerabilityReason(), 120)
            );

            return new ExperimentRecord(
                    filename,
                    mode,
                    res.isHasVulnerability(),
                    nullToNA(res.getVulnerabilityType()),
                    nullToNA(res.getVulnerabilityReason()),
                    duration,
                    null,
                    null
            );

        } catch (Exception e) {
            log.error("❌ [{}] 失败: {}", mode, e.getMessage());
            return new ExperimentRecord(filename, mode, false,
                    "SystemError", "SystemError", 0, e.getMessage(), null);
        }
    }

    /**
     * 清洗 LLM 返回的脏 JSON 字符串（Vanilla 模式）
     */
    private SmartContractAnalysisResult parseRawJson(String rawOutput) {
        try {
            String cleanJson = rawOutput;

            // 1) 提取 ```json ... ``` 块
            if (rawOutput != null && rawOutput.contains("```")) {
                Pattern pattern = Pattern.compile("```(?:json)?(.*?)```", Pattern.DOTALL);
                Matcher matcher = pattern.matcher(rawOutput);
                if (matcher.find()) {
                    cleanJson = matcher.group(1).trim();
                }
            }

            // 2) 只保留 { ... }
            int startIndex = cleanJson.indexOf("{");
            int endIndex = cleanJson.lastIndexOf("}");
            if (startIndex != -1 && endIndex != -1) {
                cleanJson = cleanJson.substring(startIndex, endIndex + 1);
            }

            // 3) 反序列化
            SmartContractAnalysisResult r = objectMapper.readValue(cleanJson, SmartContractAnalysisResult.class);

            // 兜底：字段为空时给 N/A，避免 Markdown 空白难看
            if (r.getVulnerabilityType() == null || r.getVulnerabilityType().isBlank()) {
                r.setVulnerabilityType("N/A");
            }
            if (r.getVulnerabilityReason() == null || r.getVulnerabilityReason().isBlank()) {
                r.setVulnerabilityReason("N/A");
            }
            return r;

        } catch (Exception e) {
            log.warn("⚠️ JSON 解析失败，原始输出片段: {}", safeOneLine(rawOutput, 300));
            // 返回默认错误结果，不中断实验
            return new SmartContractAnalysisResult(false, "JSON Parsing Failed", "Raw output was not valid JSON");
        }
    }


    /**
     * 生成 Markdown 报告（只包含本次 mode）
     */
    private void saveReportToMarkdown(List<ExperimentRecord> records, String mode) throws IOException {
        records.sort(Comparator.comparing(ExperimentRecord::filename));

        String timestamp = LocalDateTime.now().format(DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss"));
        StringBuilder sb = new StringBuilder();

        sb.append("# 智能合约审计实验报告（Pilot Single-Mode）\n\n");
        sb.append("**测试时间**: ").append(timestamp).append("\n\n");
        sb.append("**本次模式**: ").append(mode).append("\n\n");

        // 1) 摘要
        sb.append("## 1. 统计摘要\n");
        sb.append("| Mode | Avg Time (ms) | Detected Rate | Samples |\n");
        sb.append("|---|---:|---:|---:|\n");

        double avgTime = records.stream().mapToLong(ExperimentRecord::timeMs).average().orElse(0);
        long detected = records.stream().filter(ExperimentRecord::hasVuln).count();
        double rate = records.isEmpty() ? 0 : (double) detected / records.size() * 100;

        sb.append(String.format("| **%s** | %.0f | **%.1f%%** (%d/%d) | %d |\n",
                mode, avgTime, rate, detected, records.size(), records.size()));

        // 2) 详细数据（新增“人工审核”列）
        sb.append("\n## 2. 详细数据\n");
        sb.append("| Filename | Detected | vulnerabilityType | vulnerabilityReason | Time(ms) | Error | 人工审核 |\n");
        // ✅ 分隔行必须和表头列数一致：7 列
        sb.append("|---|---|---|---|---:|---|---|\n");

        for (ExperimentRecord r : records) {
            String status = r.hasVuln ? "✅" : "❌";
            String type = safeOneLine(r.vulnerabilityType, 60);
            String reason = safeOneLine(r.vulnerabilityReason, 360);
            String err = safeOneLine(r.rawError, 120); // 适当放长点

            // 人工审核：默认空（方便你手动填：TP/FP/TN/FN 或 ✅/❌ 或 备注）
            String people = safeOneLine(r.peopleAudit, 80);
            if (people == null) people = "";

            // ✅ 每行也必须是 7 列；最后一列不要写 null
            sb.append(String.format("| **%s** | %s | %s | %s | %d | %s | %s |\n",
                    r.filename,
                    status,
                    (type == null ? "" : type),
                    (reason == null ? "" : reason),
                    r.timeMs,
                    (err == null ? "" : err),
                    people
            ));
        }

        // 输出文件
        String fileName = "Pilot_" + mode.replaceAll("[^a-zA-Z0-9_-]", "_")
                + "_Report_" + System.currentTimeMillis() + ".md";

        Files.writeString(Paths.get(fileName), sb.toString(), StandardCharsets.UTF_8);
        System.out.println("🎉 报告已生成: " + Paths.get(fileName).toAbsolutePath());
    }


    private static String nullToNA(String s) {
        return (s == null || s.isBlank()) ? "N/A" : s;
    }

    private static String safeOneLine(String s, int maxLen) {
        if (s == null) return null;
        String t = s.replace("\n", " ").replace("\r", " ").replace("|", " ");
        if (t.length() > maxLen) t = t.substring(0, maxLen) + "...";
        return t;
    }
}
