package com.xhl.xhlaiagent.rag;

import com.xhl.utils.SimpleLengthSplitter;
import jakarta.annotation.Resource;
import lombok.extern.slf4j.Slf4j;
import org.springframework.ai.document.Document;
import org.springframework.ai.document.DocumentTransformer;
import org.springframework.ai.transformer.splitter.TextSplitter;
import org.springframework.ai.vectorstore.SearchRequest;
import org.springframework.ai.vectorstore.VectorStore;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.util.List;

@Configuration
@Slf4j
public class MilvusVectorStoreConfig {

    @Resource
    private ContractAppDocumentLoader contractAppDocumentLoader;

    @Resource
    private VectorStore vectorStore;

    // 你现在导入的 SmartBugs 数据集名字（来自 Front Matter 的 Dataset: smartbugs-curated）
    private static final String DATASET_NAME = "smartbugs-curated";

    @Bean
    public VectorStore milvusVectorVectorStore() {

        // 1) 更可靠的“是否已导入”判断：用 metadata filter 查 dataset
        //    这里用一个稳定 query + filter，而不是用中文“合约”碰运气
        boolean alreadyLoaded = alreadyLoadedDataset(DATASET_NAME);
        if (alreadyLoaded) {
            log.info("Milvus already contains dataset='{}', skip loading.", DATASET_NAME);
            return vectorStore;
        }

        log.info("Milvus does not contain dataset='{}', start loading documents...", DATASET_NAME);

        // 2) 加载文档（每个 md = 1 Document；包含 Solidity code blocks）
        List<Document> documents = contractAppDocumentLoader.loadMarkdowns();
        if (documents == null || documents.isEmpty()) {
            log.warn("No documents loaded from ContractAppDocumentLoader. Nothing to add.");
            return vectorStore;
        }

        // 3) 只导入属于 smartbugs-curated 的文档（避免把其它 KB 混进论文实验）
        List<Document> smartbugsDocs = documents.stream()
                .filter(d -> {
                    Object ds = d.getMetadata() == null ? null : d.getMetadata().get("dataset");
                    return ds != null && DATASET_NAME.equalsIgnoreCase(String.valueOf(ds));
                })
                .toList();

        if (smartbugsDocs.isEmpty()) {
            log.warn("Loaded {} documents, but none has metadata.dataset='{}'. " +
                            "Check your Front Matter parse in ContractAppDocumentLoader.",
                    documents.size(), DATASET_NAME);
            return vectorStore;
        }

        // 4) 先切分：避免 embedding 输入超过 2048
        List<Document> smartbugsChunks = SimpleLengthSplitter.split(smartbugsDocs, 1800, 150);
        log.info("Split {} docs into {} chunks (maxLen={}, overlap={})",
                smartbugsDocs.size(), smartbugsChunks.size(), 1800, 150);


        // 4) 分批写入（防止一次 add 太大；同时打印进度）
        int batchSize = 20;
        int total = smartbugsChunks.size();
        log.info("Ready to add {} documents for dataset='{}' into Milvus (batchSize={})",
                total, DATASET_NAME, batchSize);

        long start = System.currentTimeMillis();

        for (int i = 0; i < total; i += batchSize) {
            int end = Math.min(i + batchSize, total);
            List<Document> batch = smartbugsChunks.subList(i, end);

            vectorStore.add(batch);

            log.info("Inserted batch [{}/{}], docs={} ({}%)",
                    (i / batchSize) + 1,
                    (int) Math.ceil(total * 1.0 / batchSize),
                    batch.size(),
                    (end * 100) / total);
        }

        long cost = System.currentTimeMillis() - start;
        log.info("Finished inserting dataset='{}': docs={}, cost={} ms",
                DATASET_NAME, total, cost);

//        // 5) 插入后做一次 quick sanity check（带 filter）
//        List<Document> check = vectorStore.similaritySearch(
//                SearchRequest.builder()
//                        .query("access control delegatecall") // 英文关键词更贴合源码
//                        .topK(3)
//                        // 关键：限定只在 smartbugs-curated 内检索
//                        .filterExpression("dataset == '" + DATASET_NAME + "'")
//                        .build()
//        );

//        log.info("Sanity check returned {} docs for dataset='{}'.", check == null ? 0 : check.size(), DATASET_NAME);
        return vectorStore;
    }

    /**
     * 判断 Milvus 是否已存在某个 dataset 的数据。
     * 用 filterExpression 查一条即可，避免 query 文本导致误判。
     */
    private boolean alreadyLoadedDataset(String datasetName) {
        try {
            List<Document> result = vectorStore.similaritySearch(
                    SearchRequest.builder()
                            .query("probe") // query 只用于触发检索，真正限定靠 filter
                            .topK(1)
                            .filterExpression("dataset == '" + datasetName + "'")
                            .build()
            );
            return result != null && !result.isEmpty();
        } catch (Exception e) {
            // 如果 filterExpression 在你的 VectorStore 实现里不支持，会抛异常
            // 这种情况下我们降级：直接返回 false，让它导入（保证可复现）
            log.warn("FilterExpression not supported or search failed, fallback to load. Reason: {}", e.getMessage());
            return false;
        }
    }
}
