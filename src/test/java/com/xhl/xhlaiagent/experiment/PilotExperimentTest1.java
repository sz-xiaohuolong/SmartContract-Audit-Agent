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
import java.util.function.Supplier;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

/**
 * VeriRAG-Agent 完整对比实验框架
 *
 * ═══════════════════════════════════════════════════════════════════
 * 【测试集目录结构约定】
 *
 *   src/main/resources/testset/
 *   ├── buggy_contracts/                  ← SolidiFI-benchmark (全部有漏洞, GT=true)
 *   │   ├── Re-entrancy/                  ← 目录名 = 漏洞类型标签
 *   │   │   ├── 1.sol, 2.sol, ...
 *   │   ├── Overflow-Underflow/
 *   │   ├── Timestamp/
 *   │   ├── Unchecked-Send/
 *   │   ├── TOD/
 *   │   ├── tx.origin/
 *   │   └── Unhandled-Exceptions/
 *   └── safe_contracts/                   ← 干净合约 (GT=false), 需手动准备
 *       ├── safe_erc20.sol
 *       ├── safe_simple_storage.sol
 *       └── ...
 *
 * 【运行方式】
 *   mvn test -Dtest=PilotExperimentTest#runFullExperiment -Dmode=Vanilla
 *   mvn test -Dtest=PilotExperimentTest#runFullExperiment -Dmode=RAG-Only
 *   mvn test -Dtest=PilotExperimentTest#runFullExperiment -Dmode=VeriRAG-Full
 *
 * 【采样策略】
 *   每个漏洞类别最多取 MAX_SAMPLES_PER_CATEGORY 份合约（避免跑几千个）
 *   干净合约全部纳入（建议准备 10-15 份）
 *
 * 【输出】
 *   三个阶段各生成一份 Markdown 报告，包含：
 *   - 完整混淆矩阵 (TP/TN/FP/FN)
 *   - Precision / Recall / F1 / Accuracy（整体 + 分漏洞类别）
 *   - 每条样本的详细记录（文件名、GT标签、预测结果、耗时）
 * ═══════════════════════════════════════════════════════════════════
 */
@SpringBootTest
@Slf4j
public class PilotExperimentTest1 {

    @Resource
    private SmartContractDetect detector;

    private final ObjectMapper objectMapper = new ObjectMapper();

    // ─────────────────── 可调参数 ───────────────────

    /** 每个漏洞类别最多抽取的样本数（控制实验成本） */
    private static final int MAX_SAMPLES_PER_CATEGORY = 8;

    /** 合法的运行模式 */
    private static final List<String> MODES = List.of("Vanilla", "RAG-Only", "VeriRAG-Full");

    /**
     * SolidiFI-benchmark 目录名 → 标准漏洞类型名映射
     * key: 磁盘目录名（大小写敏感，与仓库保持一致）
     * value: 论文中使用的标准名称（用于分类别统计）
     */
    private static final Map<String, String> CATEGORY_MAPPING = Map.of(
            "Re-entrancy",           "Reentrancy",
            "Overflow-Underflow",    "Integer Overflow/Underflow",
            "Timestamp",             "Timestamp Dependency",
            "Unchecked-Send",        "Unchecked Send",
            "TOD",                   "TOD",
            "tx.origin",             "tx.origin",
            "Unhandled-Exceptions",  "Unhandled Exceptions"
    );

    // ─────────────────── 数据结构 ───────────────────

    /**
     * Ground Truth 标签（从目录结构自动推断）
     *
     * @param isVulnerable    是否有漏洞
     * @param vulnerabilityType 漏洞类型（Safe 合约填 "Safe"）
     */
    record GroundTruth(boolean isVulnerable, String vulnerabilityType) {}

    /**
     * 单条实验记录
     *
     * @param filename          合约文件名
     * @param groundTruth       人工标注的真实标签
     * @param predicted         系统预测结果
     * @param mode              当前运行模式
     * @param timeMs            检测耗时（毫秒）
     * @param rawError          系统错误信息（正常为null）
     * @param outcome           TP / TN / FP / FN
     */
    record ExperimentRecord(
            String filename,
            GroundTruth groundTruth,
            SmartContractAnalysisResult predicted,
            String mode,
            long timeMs,
            String rawError,
            String outcome    // "TP" / "TN" / "FP" / "FN"
    ) {}

    // ─────────────────── 主入口 ───────────────────

    @Test
    void runFullExperiment() throws IOException {

        // 0) 读取模式
        String mode = System.getProperty("mode", "Vanilla");
        if (!MODES.contains(mode)) {
            log.error("❌ mode 参数非法: {}，可选值: {}", mode, MODES);
            return;
        }
        log.info("═══════════════════════════════════════");
        log.info("🧪 VeriRAG-Agent Experiment | Mode = {}", mode);
        log.info("═══════════════════════════════════════");

        // 1) 构建带 Ground Truth 标签的样本列表
        List<LabeledSample> samples = loadLabeledSamples();
        if (samples.isEmpty()) {
            log.error("❌ 没有找到任何样本，请检查测试集目录结构");
            return;
        }
        log.info("✅ 共加载 {} 个带标签样本（含正负样本）", samples.size());
        logSampleDistribution(samples);

        // 2) 逐样本检测
        List<ExperimentRecord> records = new ArrayList<>();
        int total = samples.size();

        for (int i = 0; i < total; i++) {
            LabeledSample sample = samples.get(i);
            log.info("\n[{}/{}] 正在处理: {} (GT={}, type={})",
                    i + 1, total,
                    sample.filename(),
                    sample.groundTruth().isVulnerable() ? "Vulnerable" : "Safe",
                    sample.groundTruth().vulnerabilityType());

            ExperimentRecord record = runSingleSample(sample, mode);
            records.add(record);

            // 实时日志
            log.info("  → 预测: {} | 类型: {} | 耗时: {}ms | 结果: {}",
                    record.predicted().isHasVulnerability() ? "Vulnerable" : "Safe",
                    record.predicted().getVulnerabilityType(),
                    record.timeMs(),
                    record.outcome());
        }

        // 3) 生成完整报告
        String reportPath = saveFullReport(records, mode);
        log.info("\n🎉 实验完成！报告路径: {}", reportPath);
        printQuickSummary(records, mode);
    }

    // ─────────────────── 数据加载 ───────────────────

    /**
     * 从目录结构自动推断 Ground Truth，构建带标签样本列表
     *
     * 逻辑：
     *  - buggy_contracts/<TYPE>/*.sol  → GT(isVulnerable=true, type=<TYPE>)
     *  - safe_contracts/*.sol          → GT(isVulnerable=false, type="Safe")
     */
    private List<LabeledSample> loadLabeledSamples() {
        List<LabeledSample> samples = new ArrayList<>();

        // ── 正样本：buggy_contracts 下各子目录 ──
        File buggyRoot = resolveDir("buggy_contracts");
        if (buggyRoot != null && buggyRoot.isDirectory()) {
            File[] categoryDirs = buggyRoot.listFiles(File::isDirectory);
            if (categoryDirs != null) {
                // 按目录名排序，确保实验可复现
                Arrays.sort(categoryDirs, Comparator.comparing(File::getName));

                for (File categoryDir : categoryDirs) {
                    String dirName = categoryDir.getName();
                    String mappedType = CATEGORY_MAPPING.getOrDefault(dirName, dirName);

                    File[] solFiles = categoryDir.listFiles((d, name) -> name.endsWith(".sol"));
                    if (solFiles == null || solFiles.length == 0) {
                        log.warn("⚠️ 目录 {} 下没有 .sol 文件，已跳过", dirName);
                        continue;
                    }

                    // 按文件名排序后截取，保证结果可复现
                    Arrays.sort(solFiles, Comparator.comparing(File::getName));
                    int take = Math.min(solFiles.length, MAX_SAMPLES_PER_CATEGORY);

                    for (int i = 0; i < take; i++) {
                        File f = solFiles[i];
                        try {
                            String code = Files.readString(f.toPath());
                            GroundTruth gt = new GroundTruth(true, mappedType);
                            samples.add(new LabeledSample(f.getName(), code, gt));
                        } catch (IOException e) {
                            log.warn("⚠️ 读取文件失败: {} - {}", f.getName(), e.getMessage());
                        }
                    }
                    log.info("  📂 加载 {} 类别: {} 份（共 {} 份可用）", mappedType, take, solFiles.length);
                }
            }
        } else {
            log.warn("⚠️ 未找到 buggy_contracts 目录，请检查路径配置");
        }

        // ── 负样本：safe_contracts 目录 ──
        File safeRoot = resolveDir("safe_contracts");
        if (safeRoot != null && safeRoot.isDirectory()) {
            File[] safeFiles = safeRoot.listFiles((d, name) -> name.endsWith(".sol"));
            if (safeFiles != null) {
                Arrays.sort(safeFiles, Comparator.comparing(File::getName));
                for (File f : safeFiles) {
                    try {
                        String code = Files.readString(f.toPath());
                        GroundTruth gt = new GroundTruth(false, "Safe");
                        samples.add(new LabeledSample(f.getName(), code, gt));
                    } catch (IOException e) {
                        log.warn("⚠️ 读取安全合约失败: {}", f.getName());
                    }
                }
                log.info("  📂 加载安全合约（负样本）: {} 份", safeFiles.length);
            }
        } else {
            log.warn("⚠️ 未找到 safe_contracts 目录！\n" +
                    "   → 实验将缺少负样本，无法计算 FP/Precision。\n" +
                    "   → 请在 src/main/resources/testset/safe_contracts/ 下放置干净合约。\n" +
                    "   → 建议数量：10-15 份，可从 OpenZeppelin 标准合约中选取。");
        }

        // 打乱顺序（固定随机种子，保证可复现）
        Collections.shuffle(samples, new Random(42L));
        return samples;
    }

    /** 按优先级查找测试集目录 */
    private File resolveDir(String subPath) {
        String[] candidates = {
                "src/main/resources/testset/" + subPath,
                "src/test/resources/testset/" + subPath,
                "testset/" + subPath
        };
        for (String path : candidates) {
            File f = new File(path);
            if (f.exists() && f.isDirectory()) {
                log.debug("找到目录: {}", f.getAbsolutePath());
                return f;
            }
        }
        return null;
    }

    private void logSampleDistribution(List<LabeledSample> samples) {
        Map<String, Long> dist = samples.stream()
                .collect(Collectors.groupingBy(
                        s -> s.groundTruth().isVulnerable()
                                ? s.groundTruth().vulnerabilityType()
                                : "Safe",
                        Collectors.counting()
                ));
        log.info("样本分布：");
        dist.entrySet().stream()
                .sorted(Map.Entry.<String, Long>comparingByValue().reversed())
                .forEach(e -> log.info("  {:30s} → {} 份", e.getKey(), e.getValue()));
    }

    // ─────────────────── 单样本检测 ───────────────────

    private ExperimentRecord runSingleSample(LabeledSample sample, String mode) {
        long start = System.currentTimeMillis();
        SmartContractAnalysisResult predicted;
        String rawError = null;

        try {
            predicted = switch (mode) {
                case "Vanilla"      -> parseVanilla(detector.auditVanilla(sample.code()));
                case "RAG-Only"     -> detector.auditRAGOnly(sample.code());
                case "VeriRAG-Full" -> detector.auditFullAgent(sample.code());
                default             -> throw new IllegalArgumentException("Unknown mode: " + mode);
            };
        } catch (Exception e) {
            log.error("❌ 检测异常: {}", e.getMessage());
            rawError = e.getMessage();
            predicted = new SmartContractAnalysisResult(false, "SystemError", e.getMessage());
        }

        long duration = System.currentTimeMillis() - start;

        // 计算 TP/TN/FP/FN
        boolean gtVuln = sample.groundTruth().isVulnerable();
        boolean predVuln = predicted.isHasVulnerability();
        String outcome = computeOutcome(gtVuln, predVuln);

        return new ExperimentRecord(
                sample.filename(),
                sample.groundTruth(),
                predicted,
                mode,
                duration,
                rawError,
                outcome
        );
    }

    private String computeOutcome(boolean gtVuln, boolean predVuln) {
        if (gtVuln && predVuln)   return "TP";
        if (!gtVuln && !predVuln) return "TN";
        if (!gtVuln && predVuln)  return "FP";
        return "FN"; // gtVuln && !predVuln
    }

    /** 处理 Vanilla 模式返回的原始 JSON 字符串 */
    private SmartContractAnalysisResult parseVanilla(String rawOutput) {
        try {
            String clean = rawOutput;
            if (rawOutput != null && rawOutput.contains("```")) {
                Matcher m = Pattern.compile("```(?:json)?(.*?)```", Pattern.DOTALL).matcher(rawOutput);
                if (m.find()) clean = m.group(1).trim();
            }
            int s = clean.indexOf("{"), e = clean.lastIndexOf("}");
            if (s != -1 && e != -1) clean = clean.substring(s, e + 1);

            SmartContractAnalysisResult r = objectMapper.readValue(clean, SmartContractAnalysisResult.class);
            if (r.getVulnerabilityType() == null || r.getVulnerabilityType().isBlank())
                r.setVulnerabilityType("N/A");
            if (r.getVulnerabilityReason() == null || r.getVulnerabilityReason().isBlank())
                r.setVulnerabilityReason("N/A");
            return r;
        } catch (Exception e) {
            log.warn("⚠️ Vanilla JSON 解析失败，原始片段: {}", safeStr(rawOutput, 200));
            return new SmartContractAnalysisResult(false, "ParseError", "Raw output was not valid JSON");
        }
    }

    // ─────────────────── 指标计算 ───────────────────

    record Metrics(int tp, int tn, int fp, int fn) {
        double precision() {
            return (tp + fp) == 0 ? 0.0 : (double) tp / (tp + fp);
        }
        double recall() {
            return (tp + fn) == 0 ? 0.0 : (double) tp / (tp + fn);
        }
        double f1() {
            double p = precision(), r = recall();
            return (p + r) == 0 ? 0.0 : 2 * p * r / (p + r);
        }
        double accuracy() {
            int total = tp + tn + fp + fn;
            return total == 0 ? 0.0 : (double) (tp + tn) / total;
        }
        int total() { return tp + tn + fp + fn; }
    }

    private Metrics calcMetrics(List<ExperimentRecord> records) {
        int tp = 0, tn = 0, fp = 0, fn = 0;
        for (ExperimentRecord r : records) {
            switch (r.outcome()) {
                case "TP" -> tp++;
                case "TN" -> tn++;
                case "FP" -> fp++;
                case "FN" -> fn++;
            }
        }
        return new Metrics(tp, tn, fp, fn);
    }

    /** 按漏洞类别分组计算指标 */
    private Map<String, Metrics> calcPerCategoryMetrics(List<ExperimentRecord> records) {
        // 只对正样本类别计算 per-category 指标（GT=true 的子集）
        Map<String, List<ExperimentRecord>> grouped = records.stream()
                .filter(r -> r.groundTruth().isVulnerable())
                .collect(Collectors.groupingBy(r -> r.groundTruth().vulnerabilityType()));

        Map<String, Metrics> result = new TreeMap<>();
        for (Map.Entry<String, List<ExperimentRecord>> entry : grouped.entrySet()) {
            // 对于正样本子集，只有 TP 和 FN 两种情况（无 FP/TN）
            // 这里的 Recall = 分类别检出率
            List<ExperimentRecord> cat = entry.getValue();
            int tp = (int) cat.stream().filter(r -> r.outcome().equals("TP")).count();
            int fn = (int) cat.stream().filter(r -> r.outcome().equals("FN")).count();
            result.put(entry.getKey(), new Metrics(tp, 0, 0, fn));
        }
        return result;
    }

    // ─────────────────── 报告生成 ───────────────────

    private String saveFullReport(List<ExperimentRecord> records, String mode) throws IOException {
        String timestamp = LocalDateTime.now().format(DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss"));
        Metrics overall = calcMetrics(records);
        Map<String, Metrics> perCategory = calcPerCategoryMetrics(records);

        StringBuilder sb = new StringBuilder();

        // ── 标题 ──
        sb.append("# VeriRAG-Agent 实验报告\n\n");
        sb.append("| 项目 | 值 |\n|---|---|\n");
        sb.append(String.format("| 运行模式 | **%s** |\n", mode));
        sb.append(String.format("| 测试时间 | %s |\n", timestamp));
        sb.append(String.format("| 样本总量 | %d（正: %d，负: %d）|\n",
                overall.total(),
                records.stream().filter(r -> r.groundTruth().isVulnerable()).count(),
                records.stream().filter(r -> !r.groundTruth().isVulnerable()).count()));
        sb.append(String.format("| 平均耗时 | %.0f ms |\n\n",
                records.stream().mapToLong(ExperimentRecord::timeMs).average().orElse(0)));

        // ── 整体性能指标 ──
        sb.append("## 1. 整体性能指标\n\n");
        sb.append("### 1.1 混淆矩阵\n\n");
        sb.append("| | 预测 Vulnerable | 预测 Safe |\n");
        sb.append("|---|---|---|\n");
        sb.append(String.format("| **实际 Vulnerable** | TP = %d | FN = %d |\n", overall.tp(), overall.fn()));
        sb.append(String.format("| **实际 Safe** | FP = %d | TN = %d |\n\n", overall.fp(), overall.tn()));

        sb.append("### 1.2 评估指标汇总\n\n");
        sb.append("| 指标 | 值 | 说明 |\n");
        sb.append("|---|---|---|\n");
        sb.append(String.format("| **Precision** | **%.4f** (%.1f%%) | TP / (TP + FP) |\n",
                overall.precision(), overall.precision() * 100));
        sb.append(String.format("| **Recall** | **%.4f** (%.1f%%) | TP / (TP + FN) |\n",
                overall.recall(), overall.recall() * 100));
        sb.append(String.format("| **F1 Score** | **%.4f** | 2×P×R / (P+R) |\n", overall.f1()));
        sb.append(String.format("| **Accuracy** | **%.4f** (%.1f%%) | (TP+TN) / Total |\n\n",
                overall.accuracy(), overall.accuracy() * 100));

        // ── 分类别指标 ──
        sb.append("## 2. 分漏洞类别检出率（Recall）\n\n");
        sb.append("> 注：分类别指标仅统计正样本（GT=Vulnerable），故此处展示 Recall（检出率）。\n\n");
        sb.append("| 漏洞类别 | TP | FN | Recall | 样本数 |\n");
        sb.append("|---|---:|---:|---:|---:|\n");

        for (Map.Entry<String, Metrics> entry : perCategory.entrySet()) {
            Metrics m = entry.getValue();
            sb.append(String.format("| %s | %d | %d | %.4f (%.1f%%) | %d |\n",
                    entry.getKey(), m.tp(), m.fn(), m.recall(), m.recall() * 100,
                    m.tp() + m.fn()));
        }

        // ── 误报分析 ──
        List<ExperimentRecord> fps = records.stream()
                .filter(r -> r.outcome().equals("FP")).toList();
        List<ExperimentRecord> fns = records.stream()
                .filter(r -> r.outcome().equals("FN")).toList();

        sb.append("\n## 3. 错误样本分析\n\n");

        sb.append("### 3.1 误报（FP）列表 — 系统误报漏洞，实为安全合约\n\n");
        if (fps.isEmpty()) {
            sb.append("> 无误报。\n\n");
        } else {
            sb.append("| 文件名 | 系统预测类型 | 预测原因（摘要） |\n");
            sb.append("|---|---|---|\n");
            for (ExperimentRecord r : fps) {
                sb.append(String.format("| %s | %s | %s |\n",
                        r.filename(),
                        r.predicted().getVulnerabilityType(),
                        safeStr(r.predicted().getVulnerabilityReason(), 80)));
            }
            sb.append("\n");
        }

        sb.append("### 3.2 漏报（FN）列表 — 系统漏报，实为有漏洞合约\n\n");
        if (fns.isEmpty()) {
            sb.append("> 无漏报。\n\n");
        } else {
            sb.append("| 文件名 | GT漏洞类型 | 系统给出原因（摘要） |\n");
            sb.append("|---|---|---|\n");
            for (ExperimentRecord r : fns) {
                sb.append(String.format("| %s | %s | %s |\n",
                        r.filename(),
                        r.groundTruth().vulnerabilityType(),
                        safeStr(r.predicted().getVulnerabilityReason(), 80)));
            }
            sb.append("\n");
        }

        // ── 完整样本明细 ──
        sb.append("## 4. 完整样本检测明细\n\n");
        sb.append("| # | 文件名 | GT类型 | GT标签 | 预测标签 | 预测类型 | 结果 | 耗时(ms) |\n");
        sb.append("|---|---|---|---|---|---|---|---:|\n");

        List<ExperimentRecord> sorted = records.stream()
                .sorted(Comparator.comparing(ExperimentRecord::outcome)
                        .thenComparing(r -> r.groundTruth().vulnerabilityType()))
                .toList();

        for (int i = 0; i < sorted.size(); i++) {
            ExperimentRecord r = sorted.get(i);
            String outcomeEmoji = switch (r.outcome()) {
                case "TP" -> "✅ TP";
                case "TN" -> "✅ TN";
                case "FP" -> "❌ FP";
                case "FN" -> "❌ FN";
                default   -> r.outcome();
            };
            sb.append(String.format("| %d | %s | %s | %s | %s | %s | %s | %d |\n",
                    i + 1,
                    r.filename(),
                    r.groundTruth().vulnerabilityType(),
                    r.groundTruth().isVulnerable() ? "Vulnerable" : "Safe",
                    r.predicted().isHasVulnerability() ? "Vulnerable" : "Safe",
                    safeStr(r.predicted().getVulnerabilityType(), 40),
                    outcomeEmoji,
                    r.timeMs()));
        }

        // ── 写入文件 ──
        String fileName = String.format("Experiment_%s_%s.md",
                mode.replaceAll("[^a-zA-Z0-9_-]", "_"),
                LocalDateTime.now().format(DateTimeFormatter.ofPattern("yyyyMMdd_HHmmss")));

        Files.writeString(Paths.get(fileName), sb.toString(), StandardCharsets.UTF_8);
        return Paths.get(fileName).toAbsolutePath().toString();
    }

    // ─────────────────── 控制台摘要 ───────────────────

    private void printQuickSummary(List<ExperimentRecord> records, String mode) {
        Metrics m = calcMetrics(records);
        log.info("\n╔══════════════════════════════════════════════╗");
        log.info("║  Mode: {:10s}  |  Samples: {:4d}          ║", mode, m.total());
        log.info("╠══════════════════════════════════════════════╣");
        log.info("║  TP: {:4d}  TN: {:4d}  FP: {:4d}  FN: {:4d}  ║",
                m.tp(), m.tn(), m.fp(), m.fn());
        log.info("╠══════════════════════════════════════════════╣");
        log.info("║  Precision : {:.4f} ({:.1f}%)               ║", m.precision(), m.precision() * 100);
        log.info("║  Recall    : {:.4f} ({:.1f}%)               ║", m.recall(), m.recall() * 100);
        log.info("║  F1 Score  : {:.4f}                         ║", m.f1());
        log.info("║  Accuracy  : {:.4f} ({:.1f}%)               ║", m.accuracy(), m.accuracy() * 100);
        log.info("╚══════════════════════════════════════════════╝");
    }

    // ─────────────────── 内部辅助类型 ───────────────────

    /** 带 Ground Truth 标签的样本（仅在内存中使用，不序列化） */
    record LabeledSample(String filename, String code, GroundTruth groundTruth) {}

    // ─────────────────── 工具函数 ───────────────────

    private static String safeStr(String s, int maxLen) {
        if (s == null) return "";
        String t = s.replace("\n", " ").replace("\r", " ").replace("|", "│");
        return t.length() > maxLen ? t.substring(0, maxLen) + "…" : t;
    }
}