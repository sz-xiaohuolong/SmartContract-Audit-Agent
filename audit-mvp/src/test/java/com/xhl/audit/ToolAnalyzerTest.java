package com.xhl.audit;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class ToolAnalyzerTest {
    private ProcessRunner.Result output(String text) {
        return new ProcessRunner.Result(ProcessRunner.Status.OK,0,text,"",false,true,1);
    }
    @Test void missingResultAndExplicitFailureAreNotSuccessfulEmptyFindings() {
        var analyzer=new ToolAnalyzer(new ProcessRunner());
        assertEquals(ToolAnalyzer.Status.PARSE_ERROR,analyzer.parse(ToolAnalyzer.Engine.SLITHER,output("{}" )).status());
        assertEquals(ToolAnalyzer.Status.TOOL_ERROR,analyzer.parse(ToolAnalyzer.Engine.SLITHER,output("{\"success\":false,\"error\":\"compile failed\"}" )).status());
        assertEquals(ToolAnalyzer.Status.PARSE_ERROR,analyzer.parse(ToolAnalyzer.Engine.MYTHRIL,output("{}" )).status());
        assertEquals(ToolAnalyzer.Status.TOOL_ERROR,analyzer.parse(ToolAnalyzer.Engine.MYTHRIL,output("{\"success\":false,\"issues\":[]}" )).status());
    }
    @Test void validEmptyFindingIsOnlyToolSuccess() {
        var analyzer=new ToolAnalyzer(new ProcessRunner());
        var r=analyzer.parse(ToolAnalyzer.Engine.SLITHER,output("{\"success\":true,\"results\":{\"detectors\":[]}}"));
        assertEquals(ToolAnalyzer.Status.OK,r.status());assertEquals(0,r.issues().size());
    }
    @Test void slitherOmittedDetectorsWithValidResultsMeansNoFindings() {
        var analyzer = new ToolAnalyzer(new ProcessRunner());
        assertEquals(ToolAnalyzer.Status.OK, analyzer.parse(ToolAnalyzer.Engine.SLITHER,
            output("{\"success\":true,\"results\":{}}")).status());
        assertEquals(ToolAnalyzer.Status.PARSE_ERROR, analyzer.parse(ToolAnalyzer.Engine.SLITHER,
            output("{\"success\":true}")).status());
    }
    @Test void slitherInvocationDisablesFindingExitCode() {
        assertTrue(ToolAnalyzer.command(ToolAnalyzer.Engine.SLITHER, "slither", java.nio.file.Path.of("C.sol")).contains("--fail-none"));
    }
    @Test void timeoutKeepsItsOwnStatus() {
        var process=new ProcessRunner.Result(ProcessRunner.Status.TIMEOUT,null,"","",false,true,300);
        assertEquals(ToolAnalyzer.Status.TIMEOUT,new ToolAnalyzer(new ProcessRunner()).parse(ToolAnalyzer.Engine.MYTHRIL,process).status());
    }
}
