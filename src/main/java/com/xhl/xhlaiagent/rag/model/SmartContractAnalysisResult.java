package com.xhl.xhlaiagent.rag.model;

import lombok.Data;

// 智能合约安全分析结果包装类
@Data
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
