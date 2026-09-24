package com.xhl.audit.retrieval;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import static org.junit.jupiter.api.Assertions.*;

class FactsAdapterTest {
    @TempDir Path directory;
    @Test void realOfflineWorkerPreservesSourceAndOrder() throws Exception {
        var extractor = new PythonFactsExtractor("python3", Path.of("../tools/experiment/program_facts.py"), Duration.ofSeconds(5));
        var result = extractor.extract("contract C { uint balance; function f() public { balance = 0; msg.sender.call(\"\"); } }");
        assertEquals("COMPLETE", result.status());
        assertEquals("WRITE", result.facts().getFirst().kind());
        assertEquals("CALL", result.facts().getLast().kind());
    }
    @Test void missingOrderInValidHashResponseIsRejected() throws Exception {
        Path worker = directory.resolve("worker.py");
        Files.writeString(worker, """
            import json, hashlib, sys
            from pathlib import Path
            source = Path(sys.argv[-1]).read_bytes()
            print(json.dumps({'schemaVersion':'1','sourceHash':hashlib.sha256(source).hexdigest(),'status':'COMPLETE',
                'stateVariables':[], 'scopes':[{'id':'scope','contract':'C','name':'f','modifiers':[],'complete':True}],
                'facts':[{'id':'x','scope':'scope','kind':'CHECK','subject':'msg.sender','resource':'owner','line':1}], 'limitations':[]}))
            """);
        assertEquals("FAILED", new PythonFactsExtractor("python3", worker, Duration.ofSeconds(3)).extract("contract C {}").status());
    }
    @Test void hashMismatchMalformedAndTimeoutCannotInjectFacts() throws Exception {
        for (String body : new String[]{"print('{}')", "print('not-json')", "import time; time.sleep(10)"}) {
            Path worker = directory.resolve("worker.py"); Files.writeString(worker, body);
            var result = new PythonFactsExtractor("python3", worker, Duration.ofMillis(100)).extract("contract C {}");
            assertEquals("FAILED", result.status());
            assertTrue(result.facts().isEmpty());
        }
    }
}
