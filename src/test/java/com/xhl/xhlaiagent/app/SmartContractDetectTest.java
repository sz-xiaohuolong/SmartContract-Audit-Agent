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
        String message = """
                请分析以下智能合约代码，并给出相应的审计建议：
                          pragma solidity ^0.8.0;
                          contract VulnerableDonation {
                              mapping (address => uint) public balances;
                              address payable public owner;
                
                              constructor() {
                                  owner = payable(msg.sender);
                              }
                
                              function donate() public payable {
                                  balances[msg.sender] += msg.value;
                              }
                
                              function withdraw(uint _amount) public {
                                  require(balances[msg.sender] >= _amount, "Insufficient balance");
                                  msg.sender.transfer(_amount);
                                  balances[msg.sender] -= _amount;
                              }
                          }
                """;

        String content = smartContractDetect.doChat(message);
        Assertions.assertNotNull(content);
    }

    @Test
    void doChatWithRag() {
        String message = ContractReaderUtils.createPromptFromContract("VulnerableDonation.sol");
        SmartContractAnalysisResult result = smartContractDetect.doChatWithRag(message);
        Assertions.assertNotNull(result);
    }
}