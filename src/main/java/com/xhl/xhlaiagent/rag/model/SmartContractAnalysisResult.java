package com.xhl.xhlaiagent.rag.model;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

// 智能合约安全分析结果包装类
@Data
@AllArgsConstructor
@NoArgsConstructor
@JsonIgnoreProperties(ignoreUnknown = true)  // 忽略未知字段，防止 LLM 返回额外字段导致解析失败
public class SmartContractAnalysisResult {

    /**
     * 是否存在漏洞
     * true 表示存在漏洞，false 表示不存在漏洞
     */
    private boolean hasVulnerability;

    /**
     * 漏洞类型（如果存在漏洞）
     * 例如：重入攻击、整数溢出、权限控制错误 等
     */
    private String vulnerabilityType;

    /**
     * 漏洞原因（简要描述）
     */
    private String vulnerabilityReason;
}
