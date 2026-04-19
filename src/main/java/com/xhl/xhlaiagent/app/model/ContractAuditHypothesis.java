package com.xhl.xhlaiagent.app.model;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.ArrayList;
import java.util.List;

/**
 * Full Agent 第一阶段的漏洞假设输出。
 */
@Data
@NoArgsConstructor
@AllArgsConstructor
@JsonIgnoreProperties(ignoreUnknown = true)
public class ContractAuditHypothesis {

    /**
     * 是否怀疑当前合约存在安全风险。
     */
    private boolean suspected;

    /**
     * 规范化后的候选漏洞类型列表。
     */
    private List<String> candidateTypes = new ArrayList<>();

    /**
     * 核心判断依据。
     */
    private String rationale;

    /**
     * 从源码中提取出的关键信号。
     */
    private List<String> keySignals = new ArrayList<>();
}
