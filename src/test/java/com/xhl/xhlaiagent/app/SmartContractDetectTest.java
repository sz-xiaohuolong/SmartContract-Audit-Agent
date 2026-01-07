package com.xhl.xhlaiagent.app;

import com.xhl.utils.ContractReaderUtils;
import com.xhl.xhlaiagent.rag.model.SmartContractAnalysisResult;
import jakarta.annotation.Resource;
import lombok.extern.slf4j.Slf4j;
import org.junit.jupiter.api.Assertions;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.*;

@Slf4j
@SpringBootTest
class SmartContractDetectTest {

    @Resource
    private SmartContractDetect smartContractDetect;

    @Test
    void doChat() {
        String message = ContractReaderUtils.createPromptFromContract("VulnerableDonation.sol");
        String content = smartContractDetect.doChat(message);
        Assertions.assertNotNull(content);
    }

    @Test
    void doChatWithRag() {
        String message = ContractReaderUtils.createPromptFromContract("OverFlow.sol");
        SmartContractAnalysisResult result = smartContractDetect.doChatWithRag(message);
        Assertions.assertNotNull(result);
    }
}