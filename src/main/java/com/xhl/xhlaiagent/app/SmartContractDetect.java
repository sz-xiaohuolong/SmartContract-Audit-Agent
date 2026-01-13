package com.xhl.xhlaiagent.app;

import com.xhl.xhlaiagent.advisor.MyLoggerAdvisor;
import com.xhl.xhlaiagent.chatmemory.FileBasedChatMemory;
import com.xhl.xhlaiagent.constant.FileConstant;
import com.xhl.xhlaiagent.rag.SafeQuestionAnswerAdvisor;
import com.xhl.xhlaiagent.rag.model.SmartContractAnalysisResult;
import jakarta.annotation.Resource;
import lombok.extern.slf4j.Slf4j;
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.memory.ChatMemory;
import org.springframework.ai.chat.model.ChatModel;
import org.springframework.ai.chat.model.ChatResponse;
import org.springframework.ai.tool.ToolCallback;
import org.springframework.ai.vectorstore.VectorStore;
import org.springframework.stereotype.Component;

@Component
@Slf4j
public class SmartContractDetect {

    private final ChatClient chatClient;

    // 系统提示词
    // 简单的 System Prompt (用于 Baseline / RAG-Only 模式)
    private static final String BASIC_SYSTEM_PROMPT = """
            你是一名智能合约安全专家。请分析用户提供的 Solidity 代码，判断是否存在安全漏洞。
            请直接输出分析结果，不需要调用任何外部工具。如果没有检测出漏洞，不要编造，直接返回false。
            最终结果请严格按照 JSON 格式输出。
            待分析的智能合约代码如下：
            ${contract_code}
            """;

    public static final String SYSTEM_PROMPT1 = """
            你是一名 VeriRAG-Agent，即资深的智能合约安全审计智能体。你配备了双引擎检测系统：
            1. **Slither (静态分析)**: 速度快，用于全面扫描。
            2. **Mythril (符号执行)**: 精度高但速度慢，用于验证复杂逻辑或算术漏洞。
            
            你的核心工作流（Workflow）必须严格遵守以下循环：
            
            1. **Phase I & II (检索与理解)**: 结合 RAG 检索到的知识，阅读并理解用户的合约代码。
            
            2. **Phase III (认知推理与假设)**: 
               - 基于代码逻辑，进行 Step-by-Step 的思维链推理。
               - 提出“漏洞假设”。
            
            3. **Phase IV (双引擎动态验证 - 核心)**: 
               - **Step A**: 优先调用 `SlitherTool` 进行全量扫描。
               - **Step B (按需启动)**: 
                   - 如果 Slither 报告了高危漏洞，且你需要确认其可利用性（Exploitability）；
                   - 或者你怀疑存在整数溢出、复杂权限绕过等 Slither 容易漏报的问题；
                   - **务必追加调用 `MythrilTool` 进行深度验证！**
               - 对比两者的结果作为“基准真值（Ground Truth）”。
            
            4. **Final Output (最终结论)**: 
               - 综合推理、Slither 和 Mythril 的结果输出审计报告。
               - 务必明确指出是哪个工具发现了漏洞。
               - 更新 vulnerabilityType、vulnerabilityReason 的内容
            
            注意：
            - 你拥有工具调用权限，**务必积极使用**。
            - 最终输出必须严格遵守 JSON 格式要求。
            - 输出语言为中文
            
            待分析的智能合约代码如下：
            ${contract_code}
            """;

    public static final String SYSTEM_PROMPT_RAG_ONLY = """
            你是一名 RAG-based 智能合约安全审计助手，专注于结合“外部安全知识库（RAG）”与自身的推理能力，对 Solidity 智能合约进行漏洞分析。
            
            你的核心工作流必须遵循以下阶段：
            
            1. **Phase I (检索与理解)**  
               - 基于用户提供的合约代码，从安全知识库中检索相关的漏洞模式、历史案例或最佳实践。
               - 阅读并理解检索到的上下文信息与合约源码。
            
            2. **Phase II (知识对齐与分析)**  
               - 将检索到的漏洞知识与当前合约的代码结构、逻辑流程进行对齐。
               - 判断是否存在相似的漏洞模式或安全隐患。
            
            3. **Phase III (推理与判断)**  
               - 基于代码逻辑与检索到的知识，进行逐步（Step-by-Step）的推理分析。
               - 若检索结果不足或未命中，请依赖你自身的智能合约安全知识进行独立推理。
               - 明确判断合约是否存在漏洞，并形成合理的分析依据。
            
            4. **Final Output (最终结论)**  
               - 输出结构化的审计结果。
               - 若存在漏洞，请给出漏洞类型（vulnerabilityType）及简要原因说明（vulnerabilityReason）。
               - 若未发现明显漏洞，也需说明判断依据。
            
            注意事项：
            - 若知识库未检索到相关信息，不应直接下没有漏洞的定论，而应基于自身知识进行判断。
            - 最终输出必须严格遵守 JSON 格式。
            - 输出语言为中文。
            
            待分析的智能合约代码如下：
            ${contract_code}
            """;


    // 构造器注入
    public SmartContractDetect(ChatModel dashscopeChatModel) {
        // 初始化基于文件的对话记忆
        String fileDir = FileConstant.FILE_SAVE_DIR + "/chat-memory";
        ChatMemory chatMemory = new FileBasedChatMemory(fileDir);
        chatClient = ChatClient.builder(dashscopeChatModel)
                .defaultSystem(SYSTEM_PROMPT1)
                .defaultAdvisors(
                        // 自定义日志 Advisor
                        new MyLoggerAdvisor()
                        // 自定义推理增强 Advisor，可按需开启
                        // new ReReadingAdvisor()
                )
                .build();
    }

    // 最简单的方法，用于对比实验
    public String auditVanilla(String message) {
        log.info("🧪 [Experiment] Running Mode: Vanilla LLM");
        String userMessage = message + "\n\n" + formatPrompt;
        ChatResponse response = chatClient
                .prompt()
                .system(BASIC_SYSTEM_PROMPT)
                .user(userMessage)
                .call()
                .chatResponse();
        return response.getResult().getOutput().getText();
    }


    String formatPrompt = """
            请使用以下 JSON 格式输出结果（不要添加额外文字）：
            {
              "hasVulnerability": true 或 false,
              "vulnerabilityType": "漏洞类型（如重入攻击）",
              "vulnerabilityReason": "漏洞原因简述"
            }
            """;

    @Resource
    private VectorStore milvusVectorVectorStore;

    @Resource
    private ToolCallback[] allTools; //工具调用


    public SmartContractAnalysisResult auditRAGOnly(String message) {
        log.info("🧪 [Experiment] Running Mode: RAG Only");
        String userMessage = message + "\n\n" + formatPrompt;
        SmartContractAnalysisResult result = chatClient
                .prompt()
                .system(SYSTEM_PROMPT_RAG_ONLY)
                .user(userMessage)
                // 开启日志，便于观察效果
                .advisors(new MyLoggerAdvisor())
                // 应用知识库问答
                .advisors(new SafeQuestionAnswerAdvisor(milvusVectorVectorStore))
                .call()
                .entity(SmartContractAnalysisResult.class);
        return result;
    }

    public SmartContractAnalysisResult auditFullAgent(String message) {
        log.info("🧪 [Experiment] Running Mode: VeriRAG-Agent (Full)");
        String userMessage = message + "\n\n" + formatPrompt;
        SmartContractAnalysisResult result = chatClient
                .prompt()
                .user(userMessage)
                // 开启日志，便于观察效果
                .advisors(new MyLoggerAdvisor())
                // 应用知识库问答
                .advisors(new SafeQuestionAnswerAdvisor(milvusVectorVectorStore))
                .tools(allTools)
                .call()
                .entity(SmartContractAnalysisResult.class);
        return result;
    }

}
