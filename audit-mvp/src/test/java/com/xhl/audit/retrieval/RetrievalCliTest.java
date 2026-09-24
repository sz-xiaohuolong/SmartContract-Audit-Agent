package com.xhl.audit.retrieval;

import com.xhl.audit.AuditCli;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import java.nio.file.*;
import java.util.*;
import java.io.*;
import java.time.Duration;
import static org.junit.jupiter.api.Assertions.*;
import static com.xhl.audit.retrieval.RetrievalData.*;

class RetrievalCliTest {
    @TempDir Path directory;
    @Test void comparesFourStrategiesWithoutModelOrTargetLabels() throws Exception {
        Path source = directory.resolve("target.sol");
        Files.writeString(source, "contract C { address owner; uint balance; function f() public { require(msg.sender == owner); balance = 0; } }");
        var facts = new PythonFactsExtractor("python3", Path.of("../tools/experiment/program_facts.py"), Duration.ofSeconds(5)).extract(Files.readString(source));
        String risk = facts.facts().stream().filter(f -> f.kind().equals("WRITE")).findFirst().orElseThrow().id();
        var mapper = new ObjectMapper();
        var cases = new ArrayList<Candidate>();
        for (String role : List.of("VULNERABLE", "DEFENSE")) cases.add(new Candidate(role, role, "pair", role, "ACCESS_CONTROL", "WRITE", "案例" + role,
            List.of(new Condition("CHECK_BEFORE", "$actor", "$authority", role.equals("DEFENSE"))), true, "离线手工夹具", .8, .5));
        Path request = directory.resolve("request.json");
        mapper.writeValue(request.toFile(), Map.of("target", new Target("ACCESS_CONTROL", risk, Map.of("actor", "msg.sender", "resource", "balance", "authority", "owner")),
            "pool", new CandidatePool("1", "a".repeat(64), facts.sourceHash(), cases), "budget", new Budget(1000, 2)));
        var output = new ByteArrayOutputStream();
        int exit = AuditCli.run(new String[]{"--retrieval", "--source", source.toString(), "--request", request.toString(),
            "--worker", "../tools/experiment/program_facts.py", "--strategy", "compare"}, Map.of(), new PrintStream(output), System.err);
        assertEquals(0, exit);
        var report = mapper.readTree(output.toByteArray());
        assertEquals(4, report.get("results").size());
        assertEquals("D1", report.get("results").get(3).get("strategy").asText());
        assertEquals("DEFENSE", report.get("results").get(3).get("selected").get(0).get("candidate").get("role").asText());
    }
}
