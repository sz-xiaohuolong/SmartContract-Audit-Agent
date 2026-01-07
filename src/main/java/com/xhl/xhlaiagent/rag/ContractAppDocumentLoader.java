package com.xhl.xhlaiagent.rag;

import lombok.extern.slf4j.Slf4j;
import org.springframework.ai.document.Document;
import org.springframework.core.io.Resource;
import org.springframework.core.io.support.ResourcePatternResolver;
import org.springframework.stereotype.Component;
import org.springframework.util.StreamUtils;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * 文档加载器：
 * - 兼容 SmartBugs Curated（YAML Front Matter）
 * - 保留 Solidity code blocks（用于向量化）
 */
@Component
@Slf4j
public class ContractAppDocumentLoader {

    private final ResourcePatternResolver resourcePatternResolver;

    // YAML Front Matter: 必须出现在文件开头
    private static final Pattern FRONT_MATTER = Pattern.compile(
            "^---\\s*\\R(.*?)\\R---\\s*\\R",
            Pattern.DOTALL
    );

    public ContractAppDocumentLoader(ResourcePatternResolver resourcePatternResolver) {
        this.resourcePatternResolver = resourcePatternResolver;
    }

    /**
     * @return 加载 markdown 文档，每个 md 文件生成一个 Document
     */
    public List<Document> loadMarkdowns() {
        List<Document> allDocuments = new ArrayList<>();
        try {
            // 扫描所有文档
            Resource[] resources = resourcePatternResolver.getResources("classpath:document/**/*.md");
            log.info("Found {} markdown resources under classpath:document/**/*.md", resources.length);

            for (Resource resource : resources) {
                String fileName = resource.getFilename();
                if (fileName == null) fileName = "unknown.md";

                String raw = StreamUtils.copyToString(resource.getInputStream(), StandardCharsets.UTF_8);

                // 1) 解析 Front Matter（如果存在）
                Map<String, Object> meta = new HashMap<>();
                meta.put("source_file", fileName);

                FrontMatterParseResult fm = parseFrontMatter(raw);
                meta.putAll(fm.metadata);

                // 2) 作为向量化文本：建议用 “去掉 front matter 的 body”
                //    这样 metadata 不会污染 embedding，但代码块会保留
                String contentForEmbedding = fm.body.isBlank() ? raw : fm.body;

                // 3) 兼容旧文档：如果没有 Category，就用你原来的 “关键字” 提取兜底
                if (!meta.containsKey("category")) {
                    String legacyCategory = extractField(contentForEmbedding, "关键字");
                    if (legacyCategory != null && !legacyCategory.isBlank()) {
                        meta.put("category", legacyCategory);
                    }
                }

                allDocuments.add(new Document(contentForEmbedding, meta));
            }

        } catch (IOException e) {
            log.error("Markdown 文档加载失败", e);
        }

        log.info("Loaded {} Documents", allDocuments.size());
        return allDocuments;
    }

    /**
     * 解析 YAML Front Matter，并返回：
     * - metadata：key/value map
     * - body：去掉 front matter 的正文
     */
    private FrontMatterParseResult parseFrontMatter(String raw) {
        Matcher matcher = FRONT_MATTER.matcher(raw);
        if (!matcher.find()) {
            // 没有 front matter
            return new FrontMatterParseResult(Collections.emptyMap(), raw);
        }

        String fmBlock = matcher.group(1);
        String body = raw.substring(matcher.end());

        Map<String, Object> meta = new HashMap<>();
        // 每行格式: Key: Value
        for (String line : fmBlock.split("\\R")) {
            String trimmed = line.trim();
            if (trimmed.isBlank()) continue;

            int idx = trimmed.indexOf(':');
            if (idx <= 0) continue;

            String key = trimmed.substring(0, idx).trim();
            String value = trimmed.substring(idx + 1).trim();

            // 统一 key（你后续 Milvus / filter 建议全小写）
            String normKey = normalizeKey(key);

            // 对 SmartBugs 的 Category / SWC-ID / Vulnerable-Lines 做一点结构化
            if ("category".equals(normKey)) {
                meta.put("category", value);
                meta.put("categories", splitCsv(value)); // 可选：方便 filter / 统计
            } else if ("swc-id".equals(normKey) || "swc_id".equals(normKey) || "swc".equals(normKey)) {
                meta.put("swc_id", value);
                meta.put("swc_ids", splitCsv(value));
            } else if ("vulnerable-lines".equals(normKey) || "vulnerable_lines".equals(normKey)) {
                meta.put("vulnerable_lines", value);
                meta.put("vulnerable_line_list", splitNumberCsv(value));
            } else {
                meta.put(normKey, value);
            }
        }

        return new FrontMatterParseResult(meta, body);
    }

    private static String normalizeKey(String key) {
        // 例：Origin-Path -> origin_path
        return key.trim()
                .toLowerCase(Locale.ROOT)
                .replace(' ', '_')
                .replace('-', '_');
    }

    private static List<String> splitCsv(String value) {
        if (value == null) return Collections.emptyList();
        String v = value.trim();
        if (v.isBlank() || "N/A".equalsIgnoreCase(v)) return Collections.emptyList();
        String[] parts = v.split("\\s*,\\s*");
        List<String> out = new ArrayList<>();
        for (String p : parts) {
            if (!p.isBlank()) out.add(p.trim());
        }
        return out;
    }

    private static List<Integer> splitNumberCsv(String value) {
        List<Integer> out = new ArrayList<>();
        for (String s : splitCsv(value)) {
            try {
                out.add(Integer.parseInt(s));
            } catch (NumberFormatException ignored) {
            }
        }
        return out;
    }

    /**
     * 兼容旧文档的字段提取：匹配
     * 关键字：value
     * **关键字**：value
     */
    private static String extractField(String text, String key) {
        String pattern = "(?m)(?:\\*{0,2})" + Pattern.quote(key) + "(?:\\*{0,2})\\s*[:：]\\s*(.+)";
        Matcher matcher = Pattern.compile(pattern).matcher(text);
        if (matcher.find()) {
            return matcher.group(1).trim();
        }
        return "";
    }

    private static class FrontMatterParseResult {
        final Map<String, Object> metadata;
        final String body;

        FrontMatterParseResult(Map<String, Object> metadata, String body) {
            this.metadata = metadata;
            this.body = body;
        }
    }
}
