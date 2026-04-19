package com.xhl.xhlaiagent.app;

import com.xhl.xhlaiagent.utils.ContractReaderUtils;
import com.xhl.xhlaiagent.rag.model.SmartContractAnalysisResult;
import jakarta.annotation.Resource;
import lombok.extern.slf4j.Slf4j;
import org.junit.jupiter.api.Assertions;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

@Slf4j
@SpringBootTest
class SmartContractDetectTest {

    @Resource
    private SmartContractDetect smartContractDetect;

    @Test
    void doChat() {
        String message = ContractReaderUtils.createPromptFromContract("OverFlow.sol");
        String result = String.valueOf(smartContractDetect.auditVanilla(message));
        Assertions.assertNotNull(result);
    }

    @Test
    void doChatWithRag() {
        String message = ContractReaderUtils.createPromptFromContract("Unchecked37.sol");
        SmartContractAnalysisResult result = smartContractDetect.auditFullAgent(message);
        Assertions.assertNotNull(result);
    }
}