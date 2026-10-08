package com.xhl.audit.retrieval;

import java.util.ArrayList;
import java.util.List;
import java.util.Set;
import static com.xhl.audit.retrieval.RetrievalData.*;

/** 仅匹配明确主体、资源、作用域与执行次序，不推断变量名的权限含义。 */
public final class ConditionBinder {
    public Binding bind(ProgramFacts facts, Target target, Candidate candidate) {
        RetrievalSupport.validateFacts(facts, target);
        RetrievalSupport.validateCandidate(candidate);
        Fact risk = facts.facts().stream().filter(f -> f.id().equals(target.riskFactId())).findFirst().orElseThrow();
        Scope scope = facts.scopes().stream().filter(s -> s.id().equals(risk.scope())).findFirst().orElseThrow();
        if (!candidate.mechanism().equals(target.mechanism()) || !candidate.riskKind().equals(risk.kind()))
            return new Binding("CONTRADICTED", List.of());
        var result = new ArrayList<BoundCondition>();
        for (Condition condition : candidate.conditions()) {
            String subject = resolve(condition.subject(), target), resource = resolve(condition.resource(), target);
            String state = "UNKNOWN", reason = "角色未绑定或资源无法定位";
            var evidence = new ArrayList<String>();
            boolean knownResource = resource != null && facts.stateVariables().stream()
                .anyMatch(v -> v.contract().equals(scope.contract()) && (resource.equals(v.name()) || resource.startsWith(v.name() + "[")));
            boolean modifierPredicate = Set.of("NON_REENTRANT", "ONLY_OWNER", "HAS_ROLE", "CUSTOM_LOCK").contains(condition.predicate());
            boolean modifierObserved = scope.modifiers().stream().anyMatch(name -> switch (condition.predicate()) {
                case "NON_REENTRANT" -> name.equalsIgnoreCase("nonReentrant");
                case "ONLY_OWNER" -> name.equalsIgnoreCase("onlyOwner");
                case "HAS_ROLE" -> name.equalsIgnoreCase("onlyRole") || name.equalsIgnoreCase("hasRole");
                case "CUSTOM_LOCK" -> name.toLowerCase(java.util.Locale.ROOT).matches(".*(?:lock|reentr|mutex).*");
                default -> false;
            });
            if (modifierPredicate && modifierObserved && subject != null && resource != null) {
                state = condition.expected() ? "SUPPORTED" : "CONTRADICTED";
                reason = "目标函数显式声明匹配的防护修饰器；不推断修饰器实现的运行时覆盖";
            } else if (!scope.complete() || facts.status().equals("FAILED")) {
                reason = "该作用域包含未支持语义，不能从缺失事实推断保护存在或不存在";
            } else if (modifierPredicate && subject != null && resource != null) {
                state = condition.expected() ? "CONTRADICTED" : "SUPPORTED";
                reason = "目标函数未声明该名称的修饰器；不推断其他防护不存在";
            } else if (subject != null && knownResource) {
                String kind = condition.predicate().equals("CHECK_BEFORE") ? "CHECK" : "WRITE";
                boolean invalidated = false, aliasUnknown = false;
                for (Fact fact : facts.facts()) {
                    if (!fact.scope().equals(risk.scope()) || fact.order() >= risk.order() || !fact.kind().equals(kind)) continue;
                    boolean direct = fact.subject().equals(subject) && fact.resource().equals(resource);
                    String comparedResource = fact.subject().equals(subject) ? fact.resource()
                        : kind.equals("CHECK") && fact.resource().equals(subject) ? fact.subject() : null;
                    if (comparedResource != null && !comparedResource.equals(resource)
                        && root(comparedResource).equals(root(resource))
                        && (comparedResource.contains("[") || resource.contains("["))) aliasUnknown = true;
                    boolean symmetric = kind.equals("CHECK") && fact.subject().equals(resource) && fact.resource().equals(subject);
                    if (direct || symmetric) {
                        boolean changed = kind.equals("CHECK") && facts.facts().stream().anyMatch(later -> later.scope().equals(risk.scope())
                            && later.order() > fact.order() && later.order() < risk.order()
                            && (later.kind().equals("CALL") || later.kind().equals("WRITE") && root(later.resource()).equals(root(resource))));
                        if (changed) invalidated = true;
                        else evidence.add(fact.id());
                    }
                }
                boolean observed = !evidence.isEmpty();
                state = observed == condition.expected() ? "SUPPORTED" : "CONTRADICTED";
                reason = observed ? "同作用域、同主体及资源的条件在风险操作之前出现"
                    : "受支持的直线作用域内没有匹配的前置条件；其他主体、资源或过晚检查不计入";
                if (!observed && aliasUnknown) {
                    state = "UNKNOWN";
                    reason = "同一状态槽的不同索引可能别名，不能仅凭表达式不同判定资源不相同";
                }
                if (!observed && invalidated) {
                    state = "UNKNOWN";
                    reason = "检查与风险操作之间存在权限状态更新或外部调用，原检查不能提供确定绑定";
                }
            }
            result.add(new BoundCondition(condition, subject, resource, state, List.copyOf(evidence), reason));
        }
        String applicability = result.stream().anyMatch(c -> c.state().equals("CONTRADICTED")) ? "CONTRADICTED"
            : result.stream().anyMatch(c -> c.state().equals("UNKNOWN")) ? "UNKNOWN" : "SUPPORTED";
        return new Binding(applicability, List.copyOf(result));
    }
    private static String root(String resource) {
        int bracket = resource.indexOf('[');
        return bracket < 0 ? resource : resource.substring(0, bracket);
    }
    private String resolve(String expression, Target target) {
        return expression.startsWith("$") ? target.bindings().get(expression.substring(1)) : expression;
    }
}
