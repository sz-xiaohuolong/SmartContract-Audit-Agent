package com.xhl.xhlaiagent.rag;

import lombok.extern.slf4j.Slf4j;
import org.springframework.ai.document.Document;
import org.springframework.ai.reader.markdown.MarkdownDocumentReader;
import org.springframework.ai.reader.markdown.config.MarkdownDocumentReaderConfig;
import org.springframework.core.io.Resource;
import org.springframework.core.io.support.ResourcePatternResolver;
import org.springframework.stereotype.Component;

import java.io.IOException;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * 文档加载器
 */
@Component
@Slf4j
public class ContractAppDocumentLoader {
    private final ResourcePatternResolver resourcePatternResolver;

    // 构造器注入，Spring 会自动传入它有的组件
    public ContractAppDocumentLoader(ResourcePatternResolver resourcePatternResolver) {
        this.resourcePatternResolver = resourcePatternResolver;
    }


    /**
     * @return 加载markdown 文档
     */
    public List<Document> loadMarkdowns() {
        List<Document> allDocuments = new ArrayList<>();
        try {
            // 扫描所有文档
            Resource[] resources = resourcePatternResolver.getResources("classpath:document/*.md");

            for (Resource resource : resources) {
                String fileName = resource.getFilename();

                MarkdownDocumentReaderConfig config = MarkdownDocumentReaderConfig.builder()
                        .withHorizontalRuleCreateDocument(true) // 添加水平线作为文档分隔符
                        .withIncludeCodeBlock(false) // 不包含代码块
                        .withIncludeBlockquote(false) // 不包含引用
                        .withAdditionalMetadata("source_file", fileName)
                        .build();

                MarkdownDocumentReader reader = new MarkdownDocumentReader(resource, config);
                List<Document> docs = reader.get();
                // 为每个小节自动解析结构化信息
                for (Document doc : docs) {
                    Map<String, Object> metadata = new HashMap<>(doc.getMetadata());
                    String content = doc.getText();
                    // 提取关键字段（可按关键词识别）
                    metadata.put("category", extractField(content, "关键字"));
                    allDocuments.add(new Document(content, metadata));
                }
            }
        } catch (IOException e) {
            log.error("Markdown 文档加载失败", e);
        }
        return allDocuments;
    }

    /**
     * 辅助方法：提取以“关键字：”“描述：”等开头的行
     */
    private static String extractField(String text, String key) {
        // 允许匹配：
        // 关键字：value
        // **关键字**：value
        // **关键字**: value
        // 支持中英文冒号
        String pattern = "(?m)(?:\\*{0,2})" + key + "(?:\\*{0,2})\\s*[:：]\\s*(.+)";
        Matcher matcher = Pattern.compile(pattern).matcher(text);
        if (matcher.find()) {
            return matcher.group(1).trim();
        }
        return "";
    }

    // 测试
    public static void main(String[] args) {
        String text = "关键字：reentrancy, call(), send(), transfer(), external call before state update";
        System.out.println(extractField(text, "关键字"));

    }
}

