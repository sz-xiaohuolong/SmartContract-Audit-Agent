# 毕设项目总体架构（2026-10-04）

![智能合约审计毕设项目总体架构](assets/thesis-architecture-20261004.png)

图例：青色实线表示已有工程能力；橙色虚线表示尚未完成研究验证的方法。架构图表达**目标方案与当前进度**，不代表所有箭头已形成运行时闭环。

## 可编辑的准确结构

```mermaid
flowchart LR
  subgraph DATA[数据与治理]
    S[公开合约／审计报告／真实补丁]
    P[来源登记与项目／事件／补丁／克隆分组]
    SPLIT[知识／开发／验证／锁定测试隔离]
    G1{{G1：真实数据准入}}
    S --> P --> SPLIT --> G1
  end

  subgraph RET[研究方向 D1：安全条件感知证据检索]
    SRC[待审 Solidity 源码]
    FACT[程序事实：主体／资源／作用域／顺序]
    KB[已审核知识快照与候选池]
    BASE[Dense／Hybrid／普通正反例／字段过滤]
    BIND[目标—案例安全条件绑定]
    SEL[互补支持与反证选择]
    EB[带来源的证据包]
    SRC --> FACT --> BIND
    KB --> BASE
    KB --> BIND --> SEL --> EB
  end

  subgraph AUDIT[审计与工具证据]
    LLM[可替换模型提供方／漏洞假设]
    ADAPTER[Slither／Mythril 工具适配器]
    TE[发现／失败／超时分开记录]
    EB --> LLM
    LLM -. 可选编排 .-> ADAPTER --> TE
  end

  subgraph VERIFY[研究方向 D2：路径覆盖义务验证]
    H[固定候选假设]
    O[主体／资源／保护作用域／顺序／可达性]
    J[支持／反驳／未知]
    H --> O --> J
    TE -. 拟议证据输入 .-> O
  end

  subgraph OUTPUT[结构化结果与实验]
    R[漏洞发现／位置／证据来源／未决与失败]
    EV[同池同完整提示预算比较／消融／跨项目评测]
    MET[适用性指标／检测指标／双向错误／成本]
    R --> EV --> MET
  end

  LLM --> R
  LLM -. 候选假设 .-> H
  J -. D2 完成后接入 .-> R
  BASE --> EV
  SPLIT --> EV
  G1 -. 通过后准入 .-> KB

  classDef planned fill:#fff7ed,stroke:#d97706,stroke-width:2px,stroke-dasharray:6 4;
  classDef gate fill:#fef2f2,stroke:#b91c1c,stroke-width:2px;
  class H,O,J planned;
  class G1 gate;
```

## 当前状态与研究门禁

1. 数据谱系、分组门禁、D1 检索策略、工具适配器和本地演示链路已有工程实现。正式知识快照尚未激活，现有演示 Milvus 集合不能用于论文效果结论。
2. D1 的核心方法尚须在真实、独立审核样本上，以相同知识快照、候选池、完整提示 token 预算与强基线比较。S2/S3 离线测试验证工程契约，不验证科研收益。
3. Slither/Mythril 已有适配接口；图中到 D2 的工具证据箭头是后续编排方向，不表示当前运行时自动执行完整验证。
4. D2 目前只有固定候选与简单基线的数据契约；路径覆盖义务及定向补查仍属高风险研究设计。支持／反驳／未知不能误写成已完成系统能力。
5. G1 为数据准入，当前未通过；G2 为 D1 真实效果检验；G3 为 D2 固定候选方法检验；G4 为锁定测试与论文评估。锁定测试不能用于调参。

依据：[当前进度](../../../PROGRESS.md)、[S3 需求](../SPEC.md#r1-data)、[D1 知识库准入记录](D1_KB_READINESS.md)、[D1/D2 第二轮查新](../../../../../thesis/D1_D2第二轮查新与立题裁决_20260924.md)。
