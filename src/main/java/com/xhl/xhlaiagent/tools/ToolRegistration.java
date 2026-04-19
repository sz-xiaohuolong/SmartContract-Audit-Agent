package com.xhl.xhlaiagent.tools;

import org.springframework.ai.tool.ToolCallback;
import org.springframework.ai.tool.ToolCallbacks;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

// 工具注册
@Configuration
public class ToolRegistration {

    @Bean
    public SlitherTool slitherTool() {
        return new SlitherTool();
    }

    @Bean
    public MythrilTool mythrilTool() {
        return new MythrilTool();
    }

    @Bean
    public ToolCallback[] allTools(SlitherTool slitherTool, MythrilTool mythrilTool) {
//        FileOperationTool fileOperationTool = new FileOperationTool();
//        ResourceDownloadTool resourceDownloadTool = new ResourceDownloadTool();
//        PDFGenerationTool pdfGenerationTool = new PDFGenerationTool();
        // 把普通对象转换为工具
        return ToolCallbacks.from(
                mythrilTool,
                slitherTool
//                fileOperationTool,
//                resourceDownloadTool,
//                pdfGenerationTool
        );
    }
}
