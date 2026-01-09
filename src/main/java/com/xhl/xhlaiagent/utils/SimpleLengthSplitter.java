package com.xhl.xhlaiagent.utils;

import org.springframework.ai.document.Document;

import java.util.*;

public class SimpleLengthSplitter {

    /**
     * @param docs 原始文档（可能很长）
     * @param maxLen 每段最大长度（建议 <= 1800 留安全边际）
     * @param overlap 重叠长度（建议 100~200）
     */
    public static List<Document> split(List<Document> docs, int maxLen, int overlap) {
        List<Document> out = new ArrayList<>();
        if (docs == null) return out;

        for (Document d : docs) {
            String text = d.getText();
            if (text == null) continue;

            text = text.trim();
            if (text.isEmpty()) continue;

            Map<String, Object> meta = d.getMetadata() == null ? new HashMap<>() : new HashMap<>(d.getMetadata());

            // 短文本不切
            if (text.length() <= maxLen) {
                meta.put("chunk_index", 0);
                meta.put("chunk_total", 1);
                out.add(new Document(text, meta));
                continue;
            }

            int start = 0;
            int chunkIndex = 0;

            // 先占位统计 chunk_total（第二遍填也行，这里简单起见用 list 收集后再补 total）
            List<Document> temp = new ArrayList<>();

            while (start < text.length()) {
                int end = Math.min(start + maxLen, text.length());
                String chunk = text.substring(start, end).trim();
                if (!chunk.isEmpty()) {
                    Map<String, Object> chunkMeta = new HashMap<>(meta);
                    chunkMeta.put("chunk_index", chunkIndex);
                    temp.add(new Document(chunk, chunkMeta));
                    chunkIndex++;
                }
                if (end >= text.length()) break;
                start = Math.max(0, end - overlap);
            }

            int total = temp.size();
            for (Document cd : temp) {
                cd.getMetadata().put("chunk_total", total);
                out.add(cd);
            }
        }

        return out;
    }
}
