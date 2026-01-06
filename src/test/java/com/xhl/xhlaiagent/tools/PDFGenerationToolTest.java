package com.xhl.xhlaiagent.tools;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertNotNull;

//@SpringBootTest
public class PDFGenerationToolTest {

    @Test
    public void testGeneratePDF() {
        PDFGenerationTool tool = new PDFGenerationTool();
        String fileName = "编程导航.pdf";
        String content = "哈哈哈哈哈哈";
        String result = tool.generatePDF(fileName, content);
        assertNotNull(result);
    }
}
