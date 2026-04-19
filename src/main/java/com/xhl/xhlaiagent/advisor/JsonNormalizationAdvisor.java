package com.xhl.xhlaiagent.advisor;

import org.springframework.ai.chat.client.advisor.api.AdvisedRequest;
import org.springframework.ai.chat.client.advisor.api.AdvisedResponse;
import org.springframework.ai.chat.client.advisor.api.CallAroundAdvisor;
import org.springframework.ai.chat.client.advisor.api.CallAroundAdvisorChain;
import org.springframework.ai.chat.messages.AssistantMessage;
import org.springframework.ai.chat.model.ChatResponse;
import org.springframework.ai.chat.model.Generation;

import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * JSON 规范化 Advisor
 * 用于 Vanilla 模式，不依赖 RAG
 *
 * 功能：
 * 1. 在请求前添加强制 JSON 输出的提示
 * 2. 在响应后清理和规范化 LLM 输出，确保 JSON 格式正确
 * 3. 直接修改响应内容，使 .entity() 方法能正确解析
 */
public class JsonNormalizationAdvisor implements CallAroundAdvisor {

    // 默认输出 schema：SmartContractAnalysisResult
    private static final String DEFAULT_JSON_FORMAT_INSTRUCTION = """

            【重要】你的回复必须严格遵循 JSON 格式，不要添加任何额外文字或解释。
            JSON 必须包含以下三个字段：
            - hasVulnerability: 布尔值 true 或 false，表示是否存在漏洞
            - vulnerabilityType: 字符串，漏洞类型（如"重入攻击"）
            - vulnerabilityReason: 字符串，漏洞原因简述

            如果检测不到漏洞，hasVulnerability 必须为 false，vulnerabilityType 和 vulnerabilityReason 可填 "无"。
            直接输出 JSON，不要用代码块包裹。
            """;

    private static final String DEFAULT_EMPTY_FALLBACK_JSON =
            "{\"hasVulnerability\":false,\"vulnerabilityType\":\"EmptyOutput\",\"vulnerabilityReason\":\"LLM returned empty or invalid JSON response\"}";

    // 匹配 ```json 或 ``` 代码块
    private static final Pattern CODE_BLOCK_PATTERN = Pattern.compile(
            "```(?:json)?\\s*([\\s\\S]*?)```", Pattern.DOTALL
    );

    private final String jsonFormatInstruction;
    private final String emptyFallbackJson;

    public JsonNormalizationAdvisor() {
        this(DEFAULT_JSON_FORMAT_INSTRUCTION, DEFAULT_EMPTY_FALLBACK_JSON);
    }

    public JsonNormalizationAdvisor(String jsonFormatInstruction, String emptyFallbackJson) {
        this.jsonFormatInstruction = jsonFormatInstruction;
        this.emptyFallbackJson = emptyFallbackJson;
    }

    @Override
    public String getName() {
        return "JsonNormalizationAdvisor";
    }

    @Override
    public int getOrder() {
        return 0;  // 与 SafeQuestionAnswerAdvisor 同优先级
    }

    @Override
    public AdvisedResponse aroundCall(AdvisedRequest request, CallAroundAdvisorChain chain) {
        // 1. 请求前：追加 JSON 格式约束，并转义用户输入中的大括号
        // ST4 (StringTemplate) 会解析大括号作为模板语法，需要转义
        String escapedUserText = request.userText()
                .replace("{", "\\{")
                .replace("}", "\\}");
        String enhancedUserText = escapedUserText + jsonFormatInstruction;

        AdvisedRequest advisedRequest = AdvisedRequest.from(request)
                .userText(enhancedUserText)
                .build();

        // 2. 调用下一个 advisor（实际调用 LLM）
        AdvisedResponse response = chain.nextAroundCall(advisedRequest);

        // 3. 响应后：清理和规范化输出
        ChatResponse originalResponse = response.response();
        String rawOutput = originalResponse.getResult().getOutput().getText();

        // 清理 JSON
        String cleanedJson = cleanJsonOutput(rawOutput);

        // 构建新的响应 - 直接修改 AssistantMessage 的 content
        AssistantMessage cleanedMessage = new AssistantMessage(cleanedJson);
        Generation cleanedGeneration = new Generation(cleanedMessage);
        ChatResponse cleanedResponse = new ChatResponse(List.of(cleanedGeneration));

        return new AdvisedResponse(cleanedResponse, advisedRequest.adviseContext());
    }

    /**
     * 清理 LLM 输出，提取标准 JSON
     */
    private String cleanJsonOutput(String rawOutput) {
        if (rawOutput == null || rawOutput.isBlank()) {
            return emptyFallbackJson;
        }

        String cleaned = rawOutput.trim();

        // 1. 尝试从 ```json 或 ``` 代码块提取
        Matcher codeBlockMatcher = CODE_BLOCK_PATTERN.matcher(cleaned);
        if (codeBlockMatcher.find()) {
            cleaned = codeBlockMatcher.group(1).trim();
        }

        // 2. 如果还有代码块标记残留，手动去除
        cleaned = cleaned.replace("```json", "").replace("```", "").trim();

        // 3. 提取首个平衡的 JSON 对象
        String extracted = extractFirstJsonObject(cleaned);
        if (extracted != null && !extracted.isBlank()) {
            cleaned = extracted;
        } else {
            return emptyFallbackJson;
        }

        // 4. 基本语法修复
        cleaned = fixJsonSyntax(cleaned);

        return cleaned;
    }

    private String extractFirstJsonObject(String text) {
        int start = text.indexOf('{');
        if (start < 0) {
            return null;
        }

        int depth = 0;
        boolean inString = false;
        boolean escaped = false;

        for (int i = start; i < text.length(); i++) {
            char ch = text.charAt(i);

            if (escaped) {
                escaped = false;
                continue;
            }

            if (ch == '\\') {
                escaped = true;
                continue;
            }

            if (ch == '"') {
                inString = !inString;
                continue;
            }

            if (inString) {
                continue;
            }

            if (ch == '{') {
                depth++;
            } else if (ch == '}') {
                depth--;
                if (depth == 0) {
                    return text.substring(start, i + 1);
                }
            }
        }

        return null;
    }

    /**
     * 修复常见的 JSON 语法错误
     */
    private String fixJsonSyntax(String json) {
        // 移除可能的控制字符
        json = json.replaceAll("[\\x00-\\x1F]", "");

        // 修复常见的全角/智能引号
        json = json.replace('\u201c', '"')
                .replace('\u201d', '"')
                .replace('\u2018', '\'')
                .replace('\u2019', '\'');

        // 修复全角标点
        json = json.replace('\uff1a', ':')
                .replace('\uff0c', ',');

        // 移除末尾多余的逗号（JSON 数组/对象常见错误）
        json = json.replaceAll(",\\s*}", "}");
        json = json.replaceAll(",\\s*]", "]");

        return json;
    }
}
