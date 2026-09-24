package com.xhl.audit;

import org.junit.jupiter.api.Test;
import java.io.ByteArrayOutputStream;
import java.io.PrintStream;
import java.util.Map;
import static org.junit.jupiter.api.Assertions.*;

class AuditCliTest {
    @Test void emptyArgumentsShowHelpWithoutCredentials() {
        var out=new ByteArrayOutputStream();var err=new ByteArrayOutputStream();
        assertEquals(0,AuditCli.run(new String[0],Map.of(),new PrintStream(out),new PrintStream(err)));
        assertTrue(out.toString().contains("--source"));assertEquals("",err.toString());
    }
    @Test void invalidArgumentsDoNotEchoPotentialSecret() {
        var out=new ByteArrayOutputStream();var err=new ByteArrayOutputStream();
        assertEquals(2,AuditCli.run(new String[]{"--secret-value"},Map.of(),new PrintStream(out),new PrintStream(err)));
        assertFalse(err.toString().contains("--secret-value"));
    }
}
