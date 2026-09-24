package com.xhl.audit;

import java.io.InputStream;
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.time.Duration;
import java.util.List;
import java.util.concurrent.*;

/** 从启动计时；输出排空与超时等待互相独立。 */
public final class ProcessRunner {
    public enum Status { OK, NONZERO_EXIT, TIMEOUT, START_ERROR, INTERRUPTED, CAPTURE_ERROR }
    // cleanedUp 仅覆盖父进程与运行期间可观察到的后代；不提供操作系统进程组级隔离。
    public record Result(Status status, Integer exitCode, String stdout, String stderr, boolean truncated, boolean cleanedUp, long durationMs) {}
    private record Capture(String text, boolean truncated) {}
    public Result run(List<String> command, Path directory, Duration timeout, int outputLimit) {
        if (command == null || command.isEmpty() || timeout.isNegative() || timeout.isZero() || outputLimit < 1)
            throw new IllegalArgumentException("无效进程参数");
        long start=System.nanoTime(); Process process=null;
        var observed = new java.util.HashSet<ProcessHandle>();
        var executor=Executors.newVirtualThreadPerTaskExecutor();
        try {
            process=new ProcessBuilder(List.copyOf(command)).directory(directory.toFile()).start();
            process.getOutputStream().close();
            final Process running=process;
            var stdout=executor.submit(() -> capture(running.getInputStream(),outputLimit));
            var stderr=executor.submit(() -> capture(running.getErrorStream(),outputLimit));
            boolean completed;
            do {
                process.descendants().forEach(observed::add);
                long remaining = timeout.toMillis() - elapsed(start);
                if (remaining <= 0) { completed = !process.isAlive(); break; }
                completed = process.waitFor(Math.min(10, remaining), TimeUnit.MILLISECONDS);
            } while (!completed);
            boolean cleaned = terminate(process, observed);
            Capture out=stdout.get(1,TimeUnit.SECONDS), err=stderr.get(1,TimeUnit.SECONDS);
            Integer exit=process.isAlive()?null:process.exitValue();
            return new Result(completed?(exit==0?Status.OK:Status.NONZERO_EXIT):Status.TIMEOUT,exit,out.text(),err.text(),out.truncated()||err.truncated(),cleaned,elapsed(start));
        } catch(InterruptedException e) {
            Thread.currentThread().interrupt();
            boolean cleaned=process==null||terminate(process, observed);
            return new Result(Status.INTERRUPTED,null,"","",false,cleaned,elapsed(start));
        } catch(Exception e) {
            boolean cleaned=process==null||terminate(process, observed);
            return new Result(process==null?Status.START_ERROR:Status.CAPTURE_ERROR,null,"","",false,cleaned,elapsed(start));
        } finally {
            if(process!=null&&process.isAlive()) terminate(process, observed);
            executor.shutdownNow();
        }
    }
    private static Capture capture(InputStream input,int limit) throws Exception {
        try(input;var kept=new ByteArrayOutputStream()) {
            byte[] buffer=new byte[4096];int count;boolean truncated=false;
            while((count=input.read(buffer))!=-1) {
                int retain=Math.min(count,Math.max(0,limit-kept.size()));
                if(retain>0)kept.write(buffer,0,retain);
                if(retain<count)truncated=true;
            }
            return new Capture(kept.toString(StandardCharsets.UTF_8),truncated);
        }
    }
    private static boolean terminate(Process process, java.util.Set<ProcessHandle> observed) {
        process.descendants().forEach(observed::add);
        observed.stream().filter(ProcessHandle::isAlive).forEach(ProcessHandle::destroyForcibly);
        if (process.isAlive()) process.destroyForcibly();
        long deadline = System.nanoTime() + TimeUnit.MILLISECONDS.toNanos(500);
        while (process.isAlive() || observed.stream().anyMatch(ProcessHandle::isAlive)) {
            if (System.nanoTime() >= deadline || Thread.currentThread().isInterrupted()) break;
            try {Thread.sleep(5);} catch (InterruptedException e) {Thread.currentThread().interrupt();break;}
        }
        return !process.isAlive() && observed.stream().noneMatch(ProcessHandle::isAlive);
    }
    private static long elapsed(long start){return(System.nanoTime()-start)/1_000_000;}
}
