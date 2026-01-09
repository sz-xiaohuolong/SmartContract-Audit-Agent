package com.xhl.xhlaiagent.utils;

import lombok.extern.slf4j.Slf4j;
import org.springframework.core.io.ClassPathResource;
import org.springframework.util.StreamUtils;

import java.io.IOException;
import java.nio.charset.StandardCharsets;

/**
 * 智能合约文件读取工具
 * 默认读取路径: src/main/resources/contracts/
 */
@Slf4j
public class ContractReaderUtils {

    // 基础路径常量，对应 src/main/resources/contracts/
    private static final String BASE_PATH = "contracts/";

    /**
     * 读取 resources/contracts 目录下的合约文件
     * @param fileName 文件名，例如 "VulnerableDonation.sol"
     * @return 文件内容的字符串
     */
    public static String readContract(String fileName) {
        // 拼接完整路径: contracts/VulnerableDonation.sol
        String fullPath = BASE_PATH + fileName;
        try {
            ClassPathResource resource = new ClassPathResource(fullPath);
            if (!resource.exists()) {
                throw new RuntimeException("❌ 未找到合约文件: " + fullPath + "。请检查 src/main/resources/contracts/ 目录下是否存在该文件。");
            }
            return StreamUtils.copyToString(resource.getInputStream(), StandardCharsets.UTF_8);
        } catch (IOException e) {
            log.error("读取合约文件失败: {}", fullPath, e);
            throw new RuntimeException("读取合约文件失败: " + fileName, e);
        }
    }

    /**
     * 构造用于测试的完整 Prompt (包含系统提示 + 代码块)
     *
     * @param fileName 文件名
     * @return 完整的 Prompt 字符串
     */
    public static String createPromptFromContract(String fileName) {
        String code = readContract(fileName);
        return """
                ```solidity
                %s
                ```
                """.formatted(code);
    }
}