package com.xhl.audit.retrieval;

import java.util.*;
import java.util.regex.Pattern;
import static com.xhl.audit.retrieval.RetrievalData.*;

/** 自动层只消费可见机制改动；片段角色、条件元数据及改动本身均不是安全证明。 */
final class AutomaticContrast {
    private AutomaticContrast() {}
    private record Pair(Candidate before, Candidate after, double score) {}
    private record Event(int start, String signature) {}
    private static final Pattern IGNORED = Pattern.compile("/\\*[\\s\\S]*?\\*/|//[^\\n]*|\"(?:\\\\.|[^\"\\\\])*\"|'(?:\\\\.|[^'\\\\])*'");
    private static final Pattern TOKEN = Pattern.compile("[A-Za-z_$][\\w$]*|\\d+|==|!=|>=|<=|&&|\\|\\||\\+=|-=|[^\\s]");
    private static final Pattern GUARD = Pattern.compile("\\b(?:require|assert|if)\\s*\\(");
    private static final Pattern AC = Pattern.compile("\\b(?:msg\\s*\\.\\s*sender|tx\\s*\\.\\s*origin|ecrecover|hasRole|isOwner|isAuthorized)\\b");
    private static final Pattern RE = Pattern.compile("\\[|\\b(?:lock\\w*|_?status|mutex\\w*|reentr\\w*)\\b", Pattern.CASE_INSENSITIVE);
    private static final Pattern MODIFIER = Pattern.compile("\\b(?:nonReentrant|only[A-Z][A-Za-z0-9_]*|onlyOwner|hasRole|onlyRole)\\b");
    private static final Pattern CALL = Pattern.compile("\\.\\s*(call|send|transfer|transferFrom|safeTransfer|safeTransferFrom)\\b");
    private static final Pattern WRITE = Pattern.compile("\\bdelete\\s+[A-Za-z_$][\\w$]*(?:\\s*\\[[^;\\n]*?\\])?"
        + "|\\b[A-Za-z_$][\\w$]*(?:\\s*\\[[^;\\n]*?\\])+\\s*(?:=|\\+=|-=|\\+\\+|--)"
        + "|\\b[A-Za-z_$][\\w$]*\\s*=\\s*(?:true|false)\\b");
    private static final Set<String> STABLE = Set.of("require", "assert", "if", "msg", "sender", "value", "tx", "origin", "this",
        "true", "false", "ecrecover", "hasRole", "isOwner", "isAuthorized", "delete");

    static EvidenceBundle retrieve(ProgramFacts facts, Target target, CandidatePool pool, Budget budget) {
        var pairs = new ArrayList<Pair>();
        var pairCounts = new HashMap<String, Integer>();
        for (Candidate candidate : pool.candidates()) pairCounts.merge(candidate.pairId(), 1, Integer::sum);
        for (Candidate before : pool.candidates()) for (Candidate after : pool.candidates()) {
            if (!before.role().equals("VULNERABLE") || !after.role().equals("DEFENSE")
                || pairCounts.get(before.pairId()) != 2
                || !before.pairId().equals(after.pairId()) || !before.mechanism().equals(target.mechanism())
                || !after.mechanism().equals(target.mechanism()) || !before.riskKind().equals(after.riskKind())
                || before.chunkId().equals(after.chunkId()) || before.caseId().equals(after.caseId())
                || !changed(before.text(), after.text(), target.mechanism())) continue;
            double score = Math.min(before.denseScore(), after.denseScore()) + .25 * Math.abs(before.denseScore() - after.denseScore());
            pairs.add(new Pair(before, after, score));
        }
        pairs.sort(Comparator.comparingDouble(Pair::score).reversed().thenComparing(p -> p.before().chunkId())
            .thenComparing(p -> p.after().chunkId()));
        var selected = new ArrayList<Selection>();
        var pairIds = new HashSet<String>();
        var texts = new HashSet<String>();
        int used = 0;
        for (Pair pair : pairs) {
            var before = new Selection(pair.before(), "SOFT_SUPPORT", new Binding("UNKNOWN", List.of()));
            var after = new Selection(pair.after(), "SOFT_CONTRAST", new Binding("UNKNOWN", List.of()));
            int cost = RetrievalSupport.bytes(before) + RetrievalSupport.bytes(after);
            if (selected.size() + 2 > budget.maxCases() || used + cost > budget.maxBytes()
                || pairIds.contains(pair.before().pairId()) || texts.contains(pair.before().text()) || texts.contains(pair.after().text())) continue;
            selected.add(before); selected.add(after); used += cost;
            pairIds.add(pair.before().pairId()); texts.add(pair.before().text()); texts.add(pair.after().text());
        }
        var gaps = new ArrayList<String>();
        gaps.add("自动标注软配对：仅表示可见机制改动，未证明漏洞、补丁有效性或目标适用性");
        if (selected.isEmpty()) gaps.add("没有满足机制改动、完整配对与上下文预算的候选");
        return RetrievalSupport.bundle("D1", facts, target, pool, budget, selected, gaps);
    }

    static boolean changed(String before, String after, String mechanism) {
        for (String marker : List.of("【未识别机制保护改动】", "【配对关系不唯一，禁止软配对】"))
            if (before.startsWith(marker) || after.startsWith(marker)) return false;
        var left = events(before, mechanism); var right = events(after, mechanism);
        return (!left.isEmpty() || !right.isEmpty()) && !left.equals(right);
    }

    private static List<String> events(String text, String mechanism) {
        String source = String.join("\n", text.lines().map(line -> line.startsWith("+") || line.startsWith("-") ? line.substring(1) : line).toList());
        String code = IGNORED.matcher(source).replaceAll(match -> match.group().replaceAll("[^\\n]", " "));
        var events = new ArrayList<Event>();
        var guards = GUARD.matcher(code);
        while (guards.find()) {
            int end = guards.end(), depth = 1;
            while (end < code.length() && depth != 0) {
                char c = code.charAt(end++); if (c == '(') depth++; else if (c == ')') depth--;
            }
            if (depth != 0) continue;
            String expression = code.substring(guards.end(), end - 1);
            if ((mechanism.equals("ACCESS_CONTROL") ? AC : RE).matcher(expression).find())
                events.add(new Event(guards.start(), "GUARD:" + normal(expression)));
        }
        var modifiers = MODIFIER.matcher(code);
        while (modifiers.find()) if (mechanism.equals("REENTRANCY") == modifiers.group().equals("nonReentrant"))
            events.add(new Event(modifiers.start(), "MODIFIER:" + modifiers.group()));
        if (mechanism.equals("REENTRANCY")) {
            var calls = CALL.matcher(code);
            while (calls.find()) events.add(new Event(calls.start(), "CALL:" + calls.group(1)));
            var writes = WRITE.matcher(code);
            while (writes.find()) events.add(new Event(writes.start(), "WRITE:" + normal(writes.group())));
        }
        events.sort(Comparator.comparingInt(Event::start).thenComparing(Event::signature));
        return events.stream().map(Event::signature).toList();
    }

    private static String normal(String fragment) {
        var identifiers = new LinkedHashMap<String, String>();
        var result = new StringBuilder(); var tokens = TOKEN.matcher(fragment);
        while (tokens.find()) {
            String token = tokens.group();
            if (token.matches("[A-Za-z_$][\\w$]*") && !STABLE.contains(token))
                token = identifiers.computeIfAbsent(token, key -> "v" + identifiers.size());
            result.append(token);
        }
        return result.toString();
    }
}
