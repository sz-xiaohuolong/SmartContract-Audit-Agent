package com.xhl.audit;

import com.sun.net.httpserver.HttpServer;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import java.nio.file.Path;
import java.nio.file.Files;
import java.nio.charset.StandardCharsets;
import java.net.InetSocketAddress;
import java.io.ByteArrayOutputStream;
import java.io.PrintStream;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;
import static org.junit.jupiter.api.Assertions.*;

class CliIntegrationTest {
    @TempDir Path directory;
    @Test void completesThroughRealGatewayAndPreservesZeroUsage() throws Exception { check(200, 0); }
    @Test void unauthorizedResponseFailsWithoutRetryOrSecretOutput() throws Exception { check(401, 1); }
    @Test void transientServerFailureDoesNotRetry() throws Exception { check(500, 1); }
    @Test void localFileKeyWorksWithoutEnvironmentAndIsNotPrinted() throws Exception { check(200, 0, true); }
    private void check(int httpStatus, int expectedExit) throws Exception {
        check(httpStatus, expectedExit, false);
    }
    private void check(int httpStatus, int expectedExit, boolean fileKey) throws Exception {
        var calls = new AtomicInteger();
        var authorization = new AtomicReference<String>();
        var server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/api/plan/v3/chat/completions", exchange -> {
            calls.incrementAndGet(); exchange.getRequestBody().readAllBytes();
            authorization.set(exchange.getRequestHeaders().getFirst("Authorization"));
            String content = "{\"hasVulnerability\":false,\"vulnerabilityType\":\"\",\"vulnerabilityReason\":\"未发现可确认漏洞\"}";
            String body = httpStatus == 200 ? new ObjectMapper().writeValueAsString(Map.of(
                "id","local","object","chat.completion","created",1,"model","fixture",
                "choices", java.util.List.of(Map.of("index",0,"message",Map.of("role","assistant","content",content),"finish_reason","stop")),
                "usage",Map.of("prompt_tokens",0,"completion_tokens",0,"total_tokens",0)))
                : "{\"error\":{\"message\":\"secret-fixture\",\"type\":\"api_error\"}}";
            byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set("Content-Type","application/json");
            exchange.sendResponseHeaders(httpStatus, bytes.length);exchange.getResponseBody().write(bytes);exchange.close();
        });
        server.start();
        try {
            Path source = directory.resolve("Contract.sol"), config = directory.resolve("providers.properties");
            Files.writeString(source,"pragma solidity ^0.8.0; contract C {}");
            Files.writeString(config,"default-provider=ark\nproviders.ark.base-url=http://127.0.0.1:"+server.getAddress().getPort()+"/api/plan/v3\nproviders.ark.model=fixture\n"+
                (fileKey ? "providers.ark.api-key=secret-fixture\n" : "providers.ark.api-key-env=TEST_KEY\n"));
            var out=new ByteArrayOutputStream();var err=new ByteArrayOutputStream();
            assertEquals(expectedExit,AuditCli.run(new String[]{"--source",source.toString(),"--config",config.toString()},
                fileKey ? Map.of() : Map.of("TEST_KEY","secret-fixture"),new PrintStream(out),new PrintStream(err)));
            assertEquals(1,calls.get());
            assertEquals("Bearer secret-fixture", authorization.get());
            var result=new ObjectMapper().readTree(out.toString(StandardCharsets.UTF_8));
            assertEquals(expectedExit==0?"COMPLETED":"FAILED",result.get("status").asText());
            assertFalse(out.toString().contains("secret-fixture"));assertFalse(err.toString().contains("secret-fixture"));
            if(expectedExit==0) {assertTrue(result.get("inputTokens").isInt());assertEquals(0,result.get("inputTokens").intValue());}
            else assertEquals("UNRESOLVED",result.get("conclusion").asText());
        } finally {server.stop(0);}
    }
}
