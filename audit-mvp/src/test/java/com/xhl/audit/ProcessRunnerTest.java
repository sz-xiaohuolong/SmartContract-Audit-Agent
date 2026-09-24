package com.xhl.audit;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import java.nio.file.Path;
import java.time.Duration;
import java.util.List;
import static org.junit.jupiter.api.Assertions.*;

class ProcessRunnerTest {
    @TempDir Path directory;
    private List<String> command(String mode) {
        return List.of(Path.of(System.getProperty("java.home"), "bin", "java").toString(), "-cp",
            Path.of("target/test-classes").toAbsolutePath().toString(), ProcessFixture.class.getName(), mode);
    }
    @Test void timesOutWhileStdoutIsStillOpen() {
        long start = System.nanoTime();
        var result = new ProcessRunner().run(command("hang"), directory, Duration.ofMillis(300), 1024);
        assertEquals(ProcessRunner.Status.TIMEOUT, result.status());
        assertTrue(Duration.ofNanos(System.nanoTime()-start).toMillis() < 2300);
    }
    @Test void drainsBothStreamsAndLimitsRetainedOutput() {
        var result = new ProcessRunner().run(command("flood"), directory, Duration.ofSeconds(4), 1024);
        assertEquals(ProcessRunner.Status.OK, result.status());
        assertTrue(result.truncated());assertTrue(result.stdout().length() <= 1024);
        assertTrue(result.stderr().length() <= 1024);
    }
    @Test void distinguishesNonzeroExitAndMissingExecutable() {
        var result = new ProcessRunner().run(command("fail"), directory, Duration.ofSeconds(4), 1024);
        assertEquals(ProcessRunner.Status.NONZERO_EXIT, result.status());assertEquals(7, result.exitCode());
        assertEquals(ProcessRunner.Status.START_ERROR, new ProcessRunner().run(List.of("/nonexistent/tool"), directory, Duration.ofSeconds(1), 100).status());
    }
    @Test void cleansObservedChildAfterParentExit() {
        var result = new ProcessRunner().run(command("child"), directory, Duration.ofSeconds(4), 1024);
        long pid = Long.parseLong(result.stdout().trim());
        try {
            assertTrue(ProcessHandle.of(pid).map(p -> !p.isAlive()).orElse(true), "不能遗留已观察到的子进程");
            assertTrue(result.cleanedUp());
        } finally {ProcessHandle.of(pid).ifPresent(ProcessHandle::destroyForcibly);}
    }
    public static class ProcessFixture {
        public static void main(String[] args) throws Exception {
            if (args[0].equals("hang")) {System.out.print("started");System.out.flush();Thread.sleep(30000);}
            if (args[0].equals("flood")) {for(int i=0;i<10000;i++){System.out.println("输出 output");System.err.println("错误 stderr");}}
            if (args[0].equals("child")) {
                var child = new ProcessBuilder(Path.of(System.getProperty("java.home"), "bin", "java").toString(),
                    "-cp", System.getProperty("java.class.path"), ProcessFixture.class.getName(), "hang")
                    .redirectOutput(ProcessBuilder.Redirect.DISCARD).redirectError(ProcessBuilder.Redirect.DISCARD).start();
                System.out.println(child.pid());System.out.flush();Thread.sleep(300);
            }
            if (args[0].equals("fail")) System.exit(7);
        }
    }
}
