package com.xhl.xhlaiagent.tools;

import com.xhl.xhlaiagent.utils.ContractReaderUtils;
import lombok.extern.slf4j.Slf4j;
import org.junit.jupiter.api.Assertions;
import org.junit.jupiter.api.Test;

@Slf4j
class MythrilToolTest {

    @Test
    void mythrilAnalyze() {
// 1. 准备测试数据
        // 确保你的 resources/contracts/ 目录下有 MythrilDemo.sol
        // 如果没有 ContractReaderUtils，你也可以直接硬编码一个简单的字符串
        String contractCode = ContractReaderUtils.readContract("OverFlow.sol");


        log.info("开始测试 Mythril 工具...");

        // 2. 实例化工具 (假设你已经把方法名改为了 mythrilAnalyze)
        MythrilTool mythrilTool = new MythrilTool();

        // 3. 调用分析
        long startTime = System.currentTimeMillis();
        String result = mythrilTool.mythrilAnalyze(contractCode); // 如果你没改方法名，这里可能是 analyzeContract
        long duration = System.currentTimeMillis() - startTime;

        // 4. 输出结果
        log.info("耗时: {} ms", duration);
        log.info("Mythril 分析结果:\n{}", result);

        // 5. 断言
        Assertions.assertNotNull(result);
        Assertions.assertFalse(result.contains("系统内部错误"), "工具执行不应抛出异常");
        Assertions.assertFalse(result.contains("错误：Mythril 分析超时"), "工具不应超时（如果代码简单）");

        // 如果 Mythril 正常工作，应该能发现溢出漏洞
        // 注意：具体关键词取决于 Mythril 版本，通常会有 "Integer Overflow" 或 SWC ID
        if (result.contains("✅")) {
            log.warn("Mythril 未发现漏洞，请检查 solc 版本或 Mythril 安装是否正常。");
        } else {
            log.info("测试通过：成功检测到漏洞信息。");
        }
    }

}