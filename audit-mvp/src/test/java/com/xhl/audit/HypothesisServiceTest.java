package com.xhl.audit;

import org.junit.jupiter.api.Test;
import java.util.List;
import static org.junit.jupiter.api.Assertions.*;

class HypothesisServiceTest {
    @Test void 完整中文提示超出字节预算时不得请求模型() {
        String source = "contract C { uint x; function f() public { x = 1; } }";
        var request = new HypothesisService.Request(source, source, null, "FULL", 1, 1,
            "ACCESS_CONTROL", "f", "机制卡片：需要核验权限", List.of());
        var calls = new java.util.concurrent.atomic.AtomicInteger();
        ModelGateway gateway = (name, system, user) -> {
            calls.incrementAndGet();
            return new GatewayReply("{\"schemaVersion\":\"2\",\"hypotheses\":[]}", "fixture", "fixture", null, null, 0);
        };
        var baseline = new HypothesisService(gateway).analyze(request, "fixture");
        int bytes = baseline.requestConsumptionReceipt().path("systemPromptBytes").asInt()
            + baseline.requestConsumptionReceipt().path("userPromptBytes").asInt();
        calls.set(0);
        var blocked = new HypothesisService(gateway, bytes - 1).analyze(request, "fixture");
        assertEquals(0, calls.get());
        assertEquals("FAILED", blocked.status());
        assertEquals("INPUT_BUDGET_EXCEEDED", blocked.errorCategory());
        assertEquals(0, blocked.requestAttempts());
        assertNull(blocked.inputTokens());
        assertEquals("BLOCKED", blocked.requestConsumptionReceipt().path("promptBudgetStatus").asText());
        assertEquals("COMPLETED", new HypothesisService(gateway, bytes).analyze(request, "fixture").status());
        assertEquals(1, calls.get());
    }
    @Test void caseSensitiveNamesBindTheExactDeclaredFunction() {
        String source = "contract Vault { address owner; uint balance; uint credit; function withdraw() public { require(msg.sender == owner); balance = 1; } function Withdraw() public { credit = 1; } }";
        var request = new HypothesisService.Request(source, source, null, "FULL", 1, 1,
            "ACCESS_CONTROL", "Withdraw", "", List.of());
        var service = new HypothesisService((name, system, user) -> new GatewayReply("""
            {"schemaVersion":"2","hypotheses":[{"vulnerabilityType":"ACCESS_CONTROL",
            "contract":"Vault","function":"Withdraw","riskLine":1,"riskOperation":"WRITE",
            "reason":"待核查","evidenceIds":[]}]}
            """, "fixture", "fixture", null, null, 0, "stop", 1));
        assertEquals("Withdraw", service.analyze(request, "fixture").hypotheses().getFirst().function());
    }
    @Test void ambiguousCaseFoldedFunctionNamesAreRejected() {
        String source = "contract Vault { uint balance; function withdraw() public { balance = 1; } function Withdraw() public { balance = 2; } }";
        var request = new HypothesisService.Request(source, source, null, "FULL", 1, 1,
            "ACCESS_CONTROL", "withdraw", "", List.of());
        String body = """
            {"schemaVersion":"2","hypotheses":[{"vulnerabilityType":"ACCESS_CONTROL",
            "contract":"Vault","function":"WITHDRAW","riskLine":1,"riskOperation":"WRITE",
            "reason":"待核查","evidenceIds":[]}]}
            """;
        var result = service(body, null, null, "stop").analyze(request, "fixture");
        assertEquals("FAILED", result.status());
        assertEquals("FUNCTION_MISMATCH", result.validationIssue());
        assertTrue(result.hypotheses().isEmpty());
    }

    @Test void functionExcerptRejectsOtherExactFunctionAndAmbiguousTarget() {
        String source = "contract Vault { uint balance; function withdraw() public { balance = 1; } function Withdraw() public { balance = 2; } }";
        String body = """
            {"schemaVersion":"2","hypotheses":[{"vulnerabilityType":"ACCESS_CONTROL",
            "contract":"Vault","function":"Withdraw","riskLine":1,"riskOperation":"WRITE",
            "reason":"待核查","evidenceIds":[]}]}
            """;
        for (String target : List.of("withdraw", "WITHDRAW")) {
            var request = new HypothesisService.Request(source, source, null, "FUNCTION", 1, 1,
                "ACCESS_CONTROL", target, "", List.of());
            var result = service(body, null, null, "stop").analyze(request, "fixture");
            assertEquals("FAILED", result.status(), target);
            assertEquals("FUNCTION_MISMATCH", result.validationIssue(), target);
            assertTrue(result.hypotheses().isEmpty(), target);
        }
    }

    @Test void functionExcerptAllowsUniqueCaseFoldedName() {
        var request = new HypothesisService.Request(SOURCE, SOURCE, null, "FUNCTION", 1, 1,
            "REENTRANCY", "WITHDRAW", "", List.of());
        String body = """
            {"schemaVersion":"2","hypotheses":[{"vulnerabilityType":"REENTRANCY",
            "contract":"Vault","function":"Withdraw()","riskLine":1,"riskOperation":"CALL",
            "reason":"待核查","evidenceIds":[]}]}
            """;
        var result = service(body, null, null, "stop").analyze(request, "fixture");
        assertEquals("COMPLETED", result.status());
        assertEquals("withdraw", result.hypotheses().getFirst().function());
    }

    @Test void exactFunctionNameWithWrongRiskLineIsNotCaseFoldedToAnotherFunction() {
        String source = """
            contract Vault {
                function withdraw() public {}
                function Withdraw() public {}
            }
            """;
        var request = new HypothesisService.Request(source, source, null, "FULL", 1, 4,
            "ACCESS_CONTROL", "Withdraw", "", List.of());
        String body = """
            {"schemaVersion":"2","hypotheses":[{"vulnerabilityType":"ACCESS_CONTROL",
            "contract":"Vault","function":"Withdraw","riskLine":2,"riskOperation":"WRITE",
            "reason":"待核查","evidenceIds":[]}]}
            """;
        var result = service(body, null, null, "stop").analyze(request, "fixture");
        assertEquals("FAILED", result.status());
        assertEquals("FUNCTION_MISMATCH", result.validationIssue());
        assertTrue(result.hypotheses().isEmpty());
    }

    @Test void caseSensitiveContractNamesBindBothExactDeclarations() {
        String source = "contract Vault { function withdraw() public {} } contract vault { function withdraw() public {} }";
        var request = new HypothesisService.Request(source, source, null, "FULL", 1, 1,
            "ACCESS_CONTROL", "withdraw", "", List.of());
        String body = """
            {"schemaVersion":"2","hypotheses":[
            {"vulnerabilityType":"ACCESS_CONTROL","contract":"Vault","function":"withdraw",
            "riskLine":1,"riskOperation":"WRITE","reason":"待核查","evidenceIds":[]},
            {"vulnerabilityType":"ACCESS_CONTROL","contract":"vault","function":"withdraw",
            "riskLine":1,"riskOperation":"WRITE","reason":"待核查","evidenceIds":[]}]}
            """;
        var result = service(body, null, null, "stop").analyze(request, "fixture");
        assertEquals("COMPLETED", result.status());
        assertEquals(List.of("Vault", "vault"), result.hypotheses().stream()
            .map(HypothesisService.Hypothesis::contract).toList());
        assertTrue(result.rejectedHypotheses().isEmpty());
    }

    @Test void contractNamesIgnoreDeclarationsInsideCommentsAndStrings() {
        String body = """
            {"schemaVersion":"2","hypotheses":[{"vulnerabilityType":"REENTRANCY",
            "contract":"vAuLt","function":"withdraw","riskLine":1,"riskOperation":"CALL",
            "reason":"待核查","evidenceIds":[]}]}
            """;
        for (String source : List.of(SOURCE + " // contract vault {}",
                "/* contract vault {} */ " + SOURCE,
                SOURCE.replace("contract Vault {", "contract Vault { string constant note = \"contract vault {}\";"))) {
            var request = new HypothesisService.Request(source, source, null, "FULL", 1, 1,
                "REENTRANCY", "withdraw", "", List.of());
            var result = service(body, null, null, "stop").analyze(request, "fixture");
            assertEquals("COMPLETED", result.status(), source);
            assertEquals("Vault", result.hypotheses().getFirst().contract(), source);
        }
    }

    @Test void commentOnlyContractNameIsRejected() {
        String source = SOURCE + " /* contract Other {} */";
        var request = new HypothesisService.Request(source, source, null, "FULL", 1, 1,
            "REENTRANCY", "withdraw", "", List.of());
        String body = """
            {"schemaVersion":"2","hypotheses":[{"vulnerabilityType":"REENTRANCY",
            "contract":"Other","function":"withdraw","riskLine":1,"riskOperation":"CALL",
            "reason":"待核查","evidenceIds":[]}]}
            """;
        var result = service(body, null, null, "stop").analyze(request, "fixture");
        assertEquals("FAILED", result.status());
        assertEquals("CONTRACT_MISMATCH", result.validationIssue());
        assertTrue(result.hypotheses().isEmpty());
    }

    @Test void ambiguousCaseFoldedContractNamesRemainRejected() {
        String source = "contract Vault { function withdraw() public {} } contract vault { function withdraw() public {} }";
        var request = new HypothesisService.Request(source, source, null, "FULL", 1, 1,
            "ACCESS_CONTROL", "withdraw", "", List.of());
        String body = """
            {"schemaVersion":"2","hypotheses":[{"vulnerabilityType":"ACCESS_CONTROL",
            "contract":"VAULT","function":"withdraw","riskLine":1,"riskOperation":"WRITE",
            "reason":"待核查","evidenceIds":[]}]}
            """;
        var result = service(body, null, null, "stop").analyze(request, "fixture");
        assertEquals("FAILED", result.status());
        assertEquals("CONTRACT_MISMATCH", result.validationIssue());
        assertTrue(result.hypotheses().isEmpty());
    }

    private static final String SOURCE = "contract Vault { function withdraw() public { msg.sender.call(\"\"); } }";
    private HypothesisService.Request request() {
        return new HypothesisService.Request(SOURCE, SOURCE, null, "FULL", 1, 1,
            "REENTRANCY", "withdraw", "[案例]", List.of("evidence-1"));
    }
    private HypothesisService service(String body, Integer input, Integer output, String finish) {
        return new HypothesisService((provider, system, user) ->
            new GatewayReply(body, "fixture", "fixture", input, output, 1, finish));
    }

    @Test void validEmptyAndReportedHypothesesRemainPreliminary() {
        var empty = service("{\"schemaVersion\":\"2\",\"hypotheses\":[]}", null, null, "stop")
            .analyze(request(), "fixture");
        assertEquals("COMPLETED", empty.status());
        assertEquals("NO_CONFIRMED_FINDINGS", empty.conclusion());
        assertNull(empty.inputTokens());
        var body = """
            {"schemaVersion":"2","hypotheses":[{"vulnerabilityType":"REENTRANCY",
            "contract":"Vault","function":"withdraw","riskLine":1,"riskOperation":"CALL",
            "reason":"调用前状态未更新","evidenceIds":["evidence-1"]}]}
            """;
        var reported = service(body, 15, 20, "stop").analyze(request(), "fixture");
        assertEquals("COMPLETED", reported.status());
        assertEquals("VULNERABILITY_REPORTED", reported.conclusion());
        assertEquals(1, reported.hypotheses().size());
        assertEquals(20, reported.outputTokens());
        assertNull(reported.validationIssue());
    }
    @Test void invalidContractHasSpecificDiagnosticWithoutBecomingSafe() {
        var body = """
            {"schemaVersion":"2","hypotheses":[{"vulnerabilityType":"REENTRANCY",
            "contract":"Unknown","function":"withdraw","riskLine":1,"riskOperation":"CALL",
            "reason":"x","evidenceIds":[]}]}
            """;
        var result = service(body, 10, 20, "stop").analyze(request(), "fixture");
        assertEquals("FAILED", result.status());
        assertEquals("UNRESOLVED", result.conclusion());
        assertEquals("CONTRACT_MISMATCH", result.validationIssue());
        assertEquals(20, result.outputTokens());
    }

    @Test void badStructureLineAndEvidenceNeverBecomeSafe() {
        var valid = "{\"schemaVersion\":\"2\",\"hypotheses\":[{\"vulnerabilityType\":\"REENTRANCY\",\"contract\":\"Vault\",\"function\":\"withdraw\",\"riskLine\":1,\"riskOperation\":\"CALL\",\"reason\":\"x\",\"evidenceIds\":[\"evidence-1\"]}]}";
        for (String body : List.of("", "{}", valid.replace("\"riskLine\":1", "\"riskLine\":2"),
                                   valid.replace("evidence-1", "unknown"),
                                   valid.replace("\"reason\":\"x\"", "\"reason\":\"x\",\"reason\":\"y\""),
                                   valid + "{}",
                                   valid.replace("REENTRANCY", "ACCESS_CONTROL"))) {
            var result = service(body, null, null, "stop").analyze(request(), "fixture");
            assertEquals("FAILED", result.status(), body);
            assertEquals("UNRESOLVED", result.conclusion());
            assertEquals("MODEL_OUTPUT_INVALID", result.errorCategory());
        }
    }

    @Test void normalizesPresentationWithoutChangingEvidenceOrScope() {
        var body = """
            下面是审计结论：
            ```json
            {"schemaVersion":"2","title":"审计结果","hypotheses":[{
            "vulnerabilityType":"REENTRANCY","contract":" vault ","function":"Withdraw()",
            "riskLine":"1","riskOperation":"CALL","reason":"状态更新滞后",
            "evidenceIds":null,"severity":"high"}]}
            ```
            以上仅为初步假设。
            """;
        var result = service(body, 10, 20, "stop").analyze(request(), "fixture");
        assertEquals("COMPLETED", result.status());
        assertEquals("Vault", result.hypotheses().getFirst().contract());
        assertEquals("withdraw", result.hypotheses().getFirst().function());
        assertEquals(List.of(), result.hypotheses().getFirst().evidenceIds());
    }

    @Test void constructorAliasesResolveToDeclaredTarget() {
        String source = "contract Vault { constructor() { owner = msg.sender; } }";
        var req = new HypothesisService.Request(source, source, null, "FULL", 1, 1,
            "ACCESS_CONTROL", "constructor", "", List.of());
        var body = """
            {"schemaVersion":"2","hypotheses":[{"vulnerabilityType":"ACCESS_CONTROL",
            "contract":"vault","function":"Vault()","riskLine":"1",
            "riskOperation":"WRITE","reason":"构造函数假设","evidenceIds":[]}]}
            """;
        var result = service(body, null, null, "stop").analyze(req, "fixture");
        assertEquals("COMPLETED", result.status());
        assertEquals("constructor", result.hypotheses().getFirst().function());
    }

    @Test void normalizationStillRejectsWrongLineMissingFieldsAndUnknownFunction() {
        var body = """
            {"schemaVersion":"2","hypotheses":[{"vulnerabilityType":"REENTRANCY",
            "contract":"Vault","function":"withdraw()","riskLine":"1",
            "riskOperation":"CALL","reason":"x","evidenceIds":null}]}
            """;
        for (String invalid : List.of(body.replace("\"1\"", "\"2147483648\""),
                body.replace("withdraw()", "constructor()"),
                body.replace("\"reason\":\"x\",", ""))) {
            assertEquals("UNRESOLVED", service(invalid, null, null, "stop").analyze(request(), "fixture").conclusion());
        }
    }

    @Test void fullContractAllowsDeclaredFunctionsAndUnnamedFallbackButExcerptDoesNot() {
        String source = """
            contract Vault {
                function withdraw() public { msg.sender.call(""); }
                function() public { msg.sender.call(""); }
            }
            """;
        String body = """
            {"schemaVersion":"2","hypotheses":[{"vulnerabilityType":"REENTRANCY",
            "contract":"Vault","function":"withdraw()","riskLine":2,"riskOperation":"CALL",
            "reason":"调用风险","evidenceIds":[]},{"vulnerabilityType":"REENTRANCY",
            "contract":"Vault","function":"","riskLine":3,"riskOperation":"CALL",
            "reason":"回退调用风险","evidenceIds":[]}]}
            """;
        var full = new HypothesisService.Request(source, source, null, "FULL", 1, 4,
            "REENTRANCY", "fallback", "", List.of());
        var result = service(body, null, null, "stop").analyze(full, "fixture");
        assertEquals("COMPLETED", result.status());
        assertEquals("fallback", result.hypotheses().get(1).function());
        var excerpt = new HypothesisService.Request(source, source.split("\n")[2], null, "FUNCTION", 3, 3,
            "REENTRANCY", "fallback", "", List.of());
        var clipped = service(body, null, null, "stop").analyze(excerpt, "fixture");
        assertEquals(1, clipped.hypotheses().size());
        assertEquals("fallback", clipped.hypotheses().getFirst().function());
        assertEquals("RISK_LINE_INVALID", clipped.rejectedHypotheses().getFirst().issue());
        var wrongLine = service(body.replace("\"riskLine\":2", "\"riskLine\":3"),
            null, null, "stop").analyze(full, "fixture");
        assertEquals(1, wrongLine.hypotheses().size());
        assertEquals("FUNCTION_MISMATCH", wrongLine.rejectedHypotheses().getFirst().issue());
    }

    @Test void similarContractNameDoesNotTurnOrdinaryFunctionIntoConstructor() {
        String source = "contract Missing { function missing() public { owner = msg.sender; } }";
        var request = new HypothesisService.Request(source, source, null, "FULL", 1, 1,
            "ACCESS_CONTROL", "missing", "", List.of());
        String body = """
            {"schemaVersion":"2","hypotheses":[{"vulnerabilityType":"ACCESS_CONTROL",
            "contract":"Missing","function":"missing","riskLine":1,"riskOperation":"WRITE",
            "reason":"函数并非真正的构造函数","evidenceIds":[]}]}
            """;
        var result = service(body, null, null, "stop").analyze(request, "fixture");
        assertEquals("COMPLETED", result.status());
        assertEquals("missing", result.hypotheses().getFirst().function());
    }

    @Test void omittedEvidenceListMeansNoCitationRatherThanFabricatedCitation() {
        var body = """
            {"schemaVersion":"2","hypotheses":[{"vulnerabilityType":"REENTRANCY",
            "contract":"Vault","function":"withdraw","riskLine":1,"riskOperation":"CALL","reason":"调用风险"}]}
            """;
        var result = service(body, null, null, "stop").analyze(request(), "fixture");
        assertEquals("COMPLETED", result.status());
        assertEquals(List.of(), result.hypotheses().getFirst().evidenceIds());
    }

    @Test void validFindingSurvivesRejectedExtraHypothesisButAllRejectedRemainsUnknown() {
        String valid = """
            {"vulnerabilityType":"REENTRANCY","contract":"Vault","function":"withdraw",
            "riskLine":1,"riskOperation":"CALL","reason":"状态更新滞后","evidenceIds":[]}
            """;
        String invalid = valid.replace("withdraw", "fallback");
        String body = "{\"schemaVersion\":\"2\",\"hypotheses\":[" + valid + "," + invalid + "]}";
        var result = service(body, 10, 20, "stop").analyze(request(), "fixture");
        assertEquals("COMPLETED", result.status());
        assertEquals("VULNERABILITY_REPORTED", result.conclusion());
        assertEquals(1, result.hypotheses().size());
        assertEquals("PARTIAL_HYPOTHESES_REJECTED", result.validationIssue());
        body = "{\"schemaVersion\":\"2\",\"hypotheses\":[" + invalid + "]}";
        assertEquals("UNRESOLVED", service(body, 10, 20, "stop").analyze(request(), "fixture").conclusion());
    }

    @Test void truncationAndCallErrorPreserveUnknown() {
        var truncated = service("{\"schemaVersion\":\"2\",\"hypotheses\":[]}", 10, 2048, "length")
            .analyze(request(), "fixture");
        assertEquals("FAILED", truncated.status());
        assertEquals("MODEL_OUTPUT_TRUNCATED", truncated.errorCategory());
        assertEquals(2048, truncated.outputTokens());
        var failed = new HypothesisService((p, s, u) -> {throw new RuntimeException("secret");})
            .analyze(request(), "fixture");
        assertEquals("FAILED", failed.status());
        assertEquals("MODEL_CALL_ERROR", failed.errorCategory());
        assertFalse(failed.toString().contains("secret"));
    }
    @Test void sourceDigestAndScopeMustMatchBeforeCallingModel() {
        var calls = new java.util.concurrent.atomic.AtomicInteger();
        var service = new HypothesisService((p, s, u) -> {
            calls.incrementAndGet();
            return new GatewayReply("{\"schemaVersion\":\"2\",\"hypotheses\":[]}", "fixture", "fixture", null, null, 1);
        });
        var badHash = new HypothesisService.Request(SOURCE, SOURCE, "0".repeat(64), "FULL", 1, 1,
            "REENTRANCY", "withdraw", "", List.of());
        assertEquals("FAILED", service.analyze(badHash, "fixture").status());
        var badExcerpt = new HypothesisService.Request(SOURCE, "contract Other {}", null, "FULL", 1, 1,
            "REENTRANCY", "withdraw", "", List.of());
        assertEquals("FAILED", service.analyze(badExcerpt, "fixture").status());
        assertEquals(0, calls.get());
    }
    @Test void promptSpecifiesExactObjectAndAbsoluteSourceLines() {
        var captured = new java.util.ArrayList<String>();
        var service = new HypothesisService((p, system, user) -> {
            captured.add(system);
            captured.add(user);
            return new GatewayReply("{\"schemaVersion\":\"2\",\"hypotheses\":[]}", "fixture", "fixture", null, null, 1);
        });
        String source = "contract Vault {\nfunction withdraw() public {\nmsg.sender.call(\"\");\n}\n}";
        var scoped = new HypothesisService.Request(source,
            "function withdraw() public {\nmsg.sender.call(\"\");\n}", null,
            "FUNCTION", 2, 4, "REENTRANCY", "withdraw", "", List.of());
        assertEquals("COMPLETED", service.analyze(scoped, "fixture").status());
        assertTrue(captured.get(0).contains("只输出一个 JSON 对象"));
        assertTrue(captured.get(1).contains("3 | msg.sender.call"));
        assertTrue(captured.get(1).contains("vulnerabilityType 必须等于上述机制"));
    }
    @Test void 全文发现提示覆盖其他合约并将检索作为比较材料() {
        var captured = new java.util.ArrayList<String>();
        var service = new HypothesisService((p, system, user) -> {
            captured.add(system);
            captured.add(user);
            return new GatewayReply("{\"schemaVersion\":\"2\",\"hypotheses\":[]}", "fixture", "fixture", null, null, 1);
        });
        String source = "contract Target {\nfunction f() public {}\n}\ncontract Other {}";
        var full = new HypothesisService.Request(source, source, null, "FULL", 1, 4,
            "ACCESS_CONTROL", "f", "", List.of());
        assertEquals("COMPLETED", service.analyze(full, "fixture").status());
        assertTrue(captured.get(1).contains("全文所有真实合约及运行期入口"));
        assertFalse(captured.get(1).contains("目标所属合约：Target"));
        assertTrue(captured.get(1).contains("contract Other"));
        assertTrue(captured.get(0).contains("先独立检查待审源码"));
    }
    @Test void 全文范围必须覆盖实际源码且兼容末尾换行() {
        var calls = new java.util.concurrent.atomic.AtomicInteger();
        var service = new HypothesisService((p, system, user) -> {
            calls.incrementAndGet();
            return new GatewayReply("{\"schemaVersion\":\"2\",\"hypotheses\":[]}", "fixture", "fixture", null, null, 1);
        });
        String source = "contract Target {\nfunction f() public {}\n}\ncontract Other {}";
        for (int[] range : List.of(new int[]{1, 2}, new int[]{2, 4})) {
            var invalid = new HypothesisService.Request(source, source, null, "FULL", range[0], range[1],
                "ACCESS_CONTROL", "f", "", List.of());
            assertEquals("INPUT_INVALID", service.analyze(invalid, "fixture").errorCategory());
        }
        assertEquals(0, calls.get());
        for (String ending : List.of("", "\n", "\n\n")) {
            String fullSource = source + ending;
            int end = ending.equals("\n\n") ? 5 : 4;
            var valid = new HypothesisService.Request(fullSource, fullSource, null, "FULL", 1, end,
                "ACCESS_CONTROL", "f", "", List.of());
            assertEquals("COMPLETED", service.analyze(valid, "fixture").status());
        }
        assertEquals(3, calls.get());
    }

    @Test void 未来重入写入候选必须明确拒绝并保留原件() throws Exception {
        String body = """
            {"schemaVersion":"2","hypotheses":[{"vulnerabilityType":"REENTRANCY",
            "contract":"Vault","function":"withdraw","riskLine":1,"riskOperation":"WRITE",
            "reason":"后置写入只可作为顺序证据","evidenceIds":[]}]}
            """;
        var result = service(body, null, null, "stop").analyze(request(), "fixture");
        assertEquals("FAILED", result.status());
        assertEquals("UNRESOLVED", result.conclusion());
        assertEquals("REQUIRES_CALL", result.validationIssue());
        var rejected = new com.fasterxml.jackson.databind.ObjectMapper().valueToTree(result).path("rejectedHypotheses").get(0);
        assertEquals("WRITE", rejected.path("candidate").path("riskOperation").asText());
        assertEquals(1, rejected.path("candidate").path("riskLine").asInt());
    }

    @Test void 非枚举风险操作全部拒绝时不能返回未确认发现() {
        for (String operation : List.of("TRANSFER", "DELETE", "call")) {
            String body = "{\"schemaVersion\":\"2\",\"hypotheses\":[{\"vulnerabilityType\":\"REENTRANCY\","
                + "\"contract\":\"Vault\",\"function\":\"withdraw\",\"riskLine\":1,\"riskOperation\":\"" + operation
                + "\",\"reason\":\"待核查\",\"evidenceIds\":[]}]}";
            var result = service(body, 12, 9, "stop").analyze(request(), "fixture");
            assertEquals("UNRESOLVED", result.conclusion(), operation);
            assertEquals("RISK_OPERATION_INVALID", result.validationIssue());
            assertEquals(12, result.inputTokens());
        }
    }

    @Test void 合法重入调用不因额外写入候选被丢弃() throws Exception {
        String call = "{\"vulnerabilityType\":\"REENTRANCY\",\"contract\":\"Vault\",\"function\":\"withdraw\","
            + "\"riskLine\":1,\"riskOperation\":\"CALL\",\"reason\":\"顺序证据\",\"evidenceIds\":[]}";
        String body = "{\"schemaVersion\":\"2\",\"hypotheses\":[" + call + "," + call.replace("CALL", "WRITE") + "]}";
        var result = service(body, null, null, "stop").analyze(request(), "fixture");
        assertEquals(1, result.hypotheses().size());
        assertEquals("VULNERABILITY_REPORTED", result.conclusion());
        assertEquals("PARTIAL_HYPOTHESES_REJECTED", result.validationIssue());
        assertEquals(1, result.rejectedHypotheses().getFirst().index());
        assertEquals("REQUIRES_CALL", result.rejectedHypotheses().getFirst().issue());
    }

    private static final String CATALOG_SOURCE = """
        contract First { function f() public {} }
        contract Vault {
          function withdraw() public {
            msg.sender.call("");
          }
          function helper() internal { msg.sender.call("内部"); }
        }
        """;
    private static final String CATALOG_BODY = """
        {"schemaVersion":"2","hypotheses":[{"vulnerabilityType":"REENTRANCY",
        "contract":"Vault","function":"withdraw","riskLine":4,"riskOperation":"CALL",
        "reason":"需验证外部调用的保护条件","evidenceIds":[]}]}
        """;
    private HypothesisService.Request catalogRequest(com.fasterxml.jackson.databind.JsonNode catalog) {
        return new HypothesisService.Request(CATALOG_SOURCE, CATALOG_SOURCE, null, "FULL", 1, 7,
            "REENTRANCY", "f", "", List.of(), catalog);
    }
    private com.fasterxml.jackson.databind.node.ObjectNode catalog() {
        var catalog = RiskCatalogFixture.catalog(CATALOG_SOURCE);
        RiskCatalogFixture.operation(catalog, CATALOG_SOURCE, "Vault", "withdraw", "msg.sender.call(\"\")", "CALL", "a".repeat(64));
        return catalog;
    }
    @Test void 全文第二合约的唯一风险绑定补跨度并保留未覆盖机制() {
        var catalog = catalog();
        var captured = new java.util.ArrayList<String>();
        var service = new HypothesisService((p, system, user) -> {
            captured.add(user);
            return new GatewayReply(CATALOG_BODY, "fixture", "fixture", null, null, 1);
        });
        var result = service.analyze(catalogRequest(catalog), "fixture");
        assertEquals("COMPLETED", result.status());
        assertEquals("a".repeat(64), result.hypotheses().getFirst().riskFactId());
        assertEquals(catalog.path("operations").get(0).path("span"), result.hypotheses().getFirst().riskSpan());
        assertTrue(captured.getFirst().contains("MECHANISM_UNSUPPORTED"));
        assertTrue(captured.getFirst().contains("withdraw()"));
    }
    @Test void 目录错摘要错跨度或错行必须在模型请求前阻断() {
        var calls = new java.util.concurrent.atomic.AtomicInteger();
        var service = new HypothesisService((p, s, u) -> {
            calls.incrementAndGet();
            return new GatewayReply(CATALOG_BODY, "fixture", "fixture", null, null, 1);
        });
        for (String field : List.of("sourceHash", "contentSha256", "line", "start")) {
            var catalog = catalog();
            var span = (com.fasterxml.jackson.databind.node.ObjectNode) catalog.path("operations").get(0).path("span");
            if (field.equals("sourceHash")) catalog.put(field, "0".repeat(64));
            else if (field.equals("contentSha256")) span.put(field, "0".repeat(64));
            else span.put(field, 99999);
            var result = service.analyze(catalogRequest(catalog), "fixture");
            assertEquals("INPUT_INVALID", result.errorCategory(), field);
            assertEquals("UNRESOLVED", result.conclusion());
        }
        assertEquals(0, calls.get());
    }
    @Test void 声明行和内部调用行不能移到目录操作() {
        for (int line : List.of(3, 6)) {
            String body = CATALOG_BODY.replace("\"riskLine\":4", "\"riskLine\":" + line);
            var result = service(body, null, null, "stop").analyze(catalogRequest(catalog()), "fixture");
            assertEquals("RISK_CATALOG_POSITION_MISMATCH", result.validationIssue());
            assertEquals(line, result.rejectedHypotheses().getFirst().candidate().path("riskLine").asInt());
            assertEquals("UNRESOLVED", result.conclusion());
        }
    }
    @Test void 同行两个真实风险操作必须拒绝歧义() {
        var catalog = catalog();
        var second = catalog.withArray("operations").get(0).deepCopy();
        ((com.fasterxml.jackson.databind.node.ObjectNode) second).put("factId", "b".repeat(64));
        catalog.withArray("operations").add(second);
        var result = service(CATALOG_BODY, null, null, "stop").analyze(catalogRequest(catalog), "fixture");
        assertEquals("RISK_CATALOG_AMBIGUOUS", result.validationIssue());
        assertEquals("UNRESOLVED", result.conclusion());
    }
    @Test void 模型伪造后端字段不得覆盖目录绑定() {
        String body = CATALOG_BODY.replace("\"reason\":", "\"riskFactId\":\"伪造\",\"riskSpan\":{\"line\":99},\"reason\":");
        var result = service(body, null, null, "stop").analyze(catalogRequest(catalog()), "fixture");
        assertEquals("a".repeat(64), result.hypotheses().getFirst().riskFactId());
        assertEquals(4, result.hypotheses().getFirst().riskSpan().path("line").asInt());
    }
    @Test void 相同行号的依赖源码操作不能误绑定主源码() {
        var catalog = catalog();
        var row = (com.fasterxml.jackson.databind.node.ObjectNode) catalog.path("operations").get(0);
        row.put("sourceUnit", "Dependency.sol").put("sourceUnitHash", "e".repeat(64));
        ((com.fasterxml.jackson.databind.node.ObjectNode) row.path("span")).put("sourceUnit", "Dependency.sol").put("sourceUnitId", 1);
        catalog.withArray("sourceUnits").addObject().put("sourceUnit", "Dependency.sol").put("sourceUnitId", 1).put("sha256", "e".repeat(64));
        var result = service(CATALOG_BODY, null, null, "stop").analyze(catalogRequest(catalog), "fixture");
        assertEquals("RISK_CATALOG_POSITION_MISMATCH", result.validationIssue());
        assertEquals("UNRESOLVED", result.conclusion());
    }
    @Test void 无目录的旧调用不产生虚构后端绑定字段() {
        var result = service(CATALOG_BODY.replace("\"riskLine\":4", "\"riskLine\":1"), null, null, "stop")
            .analyze(request(), "fixture");
        assertEquals("COMPLETED", result.status());
        assertNull(result.hypotheses().getFirst().riskFactId());
        assertNull(result.hypotheses().getFirst().riskSpan());
    }
}
