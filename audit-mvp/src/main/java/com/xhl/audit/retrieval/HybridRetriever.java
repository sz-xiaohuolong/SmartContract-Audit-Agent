package com.xhl.audit.retrieval;

/** 共享候选池上的向量与词法分数相加对照，不使用条件过滤。 */
public final class HybridRetriever extends DenseRetriever {
    @Override protected boolean hybrid() {return true;}
    @Override protected String name() {return "HYBRID";}
}
