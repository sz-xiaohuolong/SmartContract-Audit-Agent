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
import java.nio.file.Path;
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

    // 定义单次实验记录
    record ExperimentRecord(
            String filename,
            String mode,
            boolean hasVuln,
            String type,
            long timeMs,
            String rawError // 记录可能的解析错误
    ) {}

    @Test
    void runPilotAblationStudy() throws IOException {
        // 1. 定位数据集 (确保这里的路径与你实际存放 .sol 文件的位置一致)
        // 假设之前我们放在了 src/main/resources/testset/pilot_set
        File datasetDir = new File("src/main/resources/testset/pilot_set");

        // 如果上面找不到，尝试 test resources
        if (!datasetDir.exists()) {
            datasetDir = new File("src/test/resources/contracts/pilot_set");
        }

        if (!datasetDir.exists() || datasetDir.listFiles() == null) {
            log.error("❌ 未找到数据集目录: {}", datasetDir.getAbsolutePath());
            return;
        }

        File[] contractFiles = datasetDir.listFiles((dir, name) -> name.endsWith(".sol"));
        if (contractFiles == null || contractFiles.length == 0) {
            log.error("❌ 目录下没有 .sol 文件");
            return;
        }

        log.info("🚀 开始 Pilot 消融实验，共发现 {} 个样本", contractFiles.length);
        List<ExperimentRecord> report = new ArrayList<>();

        // 2. 遍历每个合约
        for (File file : contractFiles) {
            String filename = file.getName();
            // 读取文件内容
            String code = Files.readString(file.toPath());

            log.info("\n========== 处理样本: {} ==========", filename);

            // === Mode 1: Vanilla (基准线 - 手动解析 JSON) ===
            report.add(runVanillaTest(filename, code));

            // === Mode 2: RAG Only (消融) ===
            report.add(runStandardTest(filename, "RAG-Only", () -> detector.auditRAGOnly(code)));

            // === Mode 3: Full Agent (完整) ===
            report.add(runStandardTest(filename, "VeriRAG-Full", () -> detector.auditFullAgent(code)));
        }

        // 3. 生成 Markdown 报告
        saveReportToMarkdown(report);
    }

    /**
     * 专门处理 auditVanilla (返回 String) 的测试逻辑
     */
    private ExperimentRecord runVanillaTest(String filename, String code) {
        long start = System.currentTimeMillis();
        try {
            // 1. 获取原始字符串
            String rawJson = detector.auditVanilla(code);
            long duration = System.currentTimeMillis() - start;

            // 2. 清洗并解析 JSON
            SmartContractAnalysisResult result = parseRawJson(rawJson);

            log.info("✅ [Vanilla] 完成, 耗时: {}ms, 结果: {}", duration, result.isHasVulnerability());
            return new ExperimentRecord(filename, "Vanilla", result.isHasVulnerability(), result.getVulnerabilityType(), duration, null);

        } catch (Exception e) {
            log.error("❌ [Vanilla] 失败: {}", e.getMessage());
            return new ExperimentRecord(filename, "Vanilla", false, "ParseError", 0, e.getMessage());
        }
    }

    /**
     * 处理 auditRAGOnly 和 auditFullAgent (直接返回 Object) 的测试逻辑
     */
    private ExperimentRecord runStandardTest(String filename, String mode, java.util.function.Supplier<SmartContractAnalysisResult> func) {
        long start = System.currentTimeMillis();
        try {
            SmartContractAnalysisResult res = func.get();
            long duration = System.currentTimeMillis() - start;

            log.info("✅ [{}] 完成, 耗时: {}ms, 结果: {}", mode, duration, res.isHasVulnerability());
            return new ExperimentRecord(filename, mode, res.isHasVulnerability(), res.getVulnerabilityType(), duration, null);

        } catch (Exception e) {
            log.error("❌ [{}] 失败: {}", mode, e.getMessage());
            return new ExperimentRecord(filename, mode, false, "SystemError", 0, e.getMessage());
        }
    }

    /**
     * 辅助方法：清洗 LLM 返回的脏 JSON 字符串
     */
    private SmartContractAnalysisResult parseRawJson(String rawOutput) {
        try {
            // 1. 尝试提取 ```json ... ``` 块
            String cleanJson = rawOutput;
            if (rawOutput.contains("```")) {
                Pattern pattern = Pattern.compile("```(?:json)?(.*?)```", Pattern.DOTALL);
                Matcher matcher = pattern.matcher(rawOutput);
                if (matcher.find()) {
                    cleanJson = matcher.group(1).trim();
                }
            }

            // 2. 确保只包含 { ... }
            int startIndex = cleanJson.indexOf("{");
            int endIndex = cleanJson.lastIndexOf("}");
            if (startIndex != -1 && endIndex != -1) {
                cleanJson = cleanJson.substring(startIndex, endIndex + 1);
            }

            // 3. 反序列化
            return objectMapper.readValue(cleanJson, SmartContractAnalysisResult.class);

        } catch (Exception e) {
            log.warn("JSON 解析失败，原始输出: {}", rawOutput);
            // 返回一个默认的错误结果，而不是抛出异常中断实验
            return new SmartContractAnalysisResult(false, "JSON Parsing Failed", "Raw output was not valid JSON");
        }
    }

    /**
     * 生成报告
     */
    private void saveReportToMarkdown(List<ExperimentRecord> records) throws IOException {
        records.sort(Comparator.comparing(ExperimentRecord::filename));
        StringBuilder sb = new StringBuilder();
        String timestamp = LocalDateTime.now().format(DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss"));

        sb.append("# 智能合约审计实验报告\n\n");
        sb.append("**测试时间**: ").append(timestamp).append("\n\n");

        sb.append("## 1. 统计摘要\n");
        sb.append("| 模式 (Mode) | 平均耗时 (Avg Time) | 检出率 (Success Rate) | 样本数 |\n");
        sb.append("|---|---|---|---|\n");

        Map<String, List<ExperimentRecord>> grouped = records.stream().collect(Collectors.groupingBy(ExperimentRecord::mode));
        List<String> modes = List.of("Vanilla", "RAG-Only", "VeriRAG-Full");

        for (String mode : modes) {
            List<ExperimentRecord> rs = grouped.getOrDefault(mode, Collections.emptyList());
            if (rs.isEmpty()) continue;

            double avgTime = rs.stream().mapToLong(ExperimentRecord::timeMs).average().orElse(0);
            long detected = rs.stream().filter(ExperimentRecord::hasVuln).count();
            double rate = (double) detected / rs.size() * 100;

            sb.append(String.format("| **%s** | %.0f ms | **%.1f%%** (%d/%d) | %d |\n",
                    mode, avgTime, rate, detected, rs.size(), rs.size()));
        }

        sb.append("\n## 2. 详细数据\n");
        sb.append("| Filename | Mode | Detected | Type/Reason | Time |\n");
        sb.append("|---|---|---|---|---|\n");

        String currentFile = "";
        for (ExperimentRecord r : records) {
            String fileNameDisplay = r.filename.equals(currentFile) ? "" : "**" + r.filename + "**";
            currentFile = r.filename;

            String status = r.hasVuln ? "✅" : "❌";
            String note = r.type;
            if ("ParseError".equals(r.type)) note = "⚠️ JSON Error";
            if (note != null) note = note.replace("\n", " ").replace("|", "");
            if (note != null && note.length() > 40) note = note.substring(0, 40) + "...";

            sb.append(String.format("| %s | %s | %s | %s | %d |\n",
                    fileNameDisplay, r.mode, status, note, r.timeMs));
        }

        String fileName = "Ablation_Study_" + System.currentTimeMillis() + ".md";
        Files.writeString(Paths.get(fileName), sb.toString(), StandardCharsets.UTF_8);
        System.out.println("🎉 报告已生成: " + Paths.get(fileName).toAbsolutePath());
    }
}