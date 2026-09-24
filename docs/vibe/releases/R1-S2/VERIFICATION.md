# S2 D1 验证记录

日期：2026-09-22。执行目录：`/Users/daiyifei/Documents/code/SmartContract-agent`，分支 main，Git 基点 `66161d5b74a6df980425f37c913e63591d246d2a`。保留原有未提交修改，未创建隔离工作树，未提交/推送/发布。

Verification Status：VERIFIED（下表工程行为）；Review Status：独立复审通过，所发现问题已修复并通过回归。S2 研究效果：UNVERIFIED。Shipping Authorization：NOT_REQUESTED。

| 验收项 | 实际证据 | 结论 |
|---|---|---|
| D1-01 状态变量、主体、修饰器与调用时序 | `test_program_facts.py` 11 项；Java FactsAdapterTest 3 项 | 通过；受限语义覆盖见 DESIGN |
| D1-02 独立对照、相同候选池与预算 | RetrievalStrategy 四实现、RetrievalCliTest；`demo/comparison.json` | 通过，四策略共用同一 poolHash、同一 budget |
| D1-03 条件绑定、错误主体/资源、过晚、旁路和未知 | RetrievalTest；无效检查、动态索引、权限状态变化回归 | 通过；不支持语义不转为保护存在/不存在 |
| D1-04 正反例配对、过滤和缺口 | 审核 pairId/机制/风险种类/条件差异；未知和不足预算不选完整对 | 通过 |
| D1-05 解释、去重及硬预算 | 全候选 evaluations、作用域来源、重复块/条件配对、实际 context 字节断言 | 通过 |
| D1-06 保持离线测试 | Maven 35 项、Python 52 项 | 全部通过 |
| 本地 Milvus 可用性 | 独立容器 v2.6.4、快照集合完整读回与检索、对照本地余弦 | 通过，未依赖外部 embedding/模型 |

## 本轮实际执行

```bash
mvn clean verify
PYTHONPATH=tools/experiment python3 -m unittest discover -s tools/experiment/tests -v
java -jar audit-mvp/target/audit-mvp-0.1.0-SNAPSHOT.jar --retrieval \
  --source docs/vibe/releases/R1-S2/evidence/demo/target.sol \
  --request docs/vibe/releases/R1-S2/evidence/demo/request.json \
  --worker tools/experiment/program_facts.py --strategy compare
```

- [Maven 完整日志](evidence/maven-clean-verify.log)：35 tests，0 failures/errors/skipped，BUILD SUCCESS。原 19 项保留，新增 16 项。
- [Python 完整日志](evidence/python-unittest.log)：52 tests，OK。原 S1 35 项保留，新增 17 项。
- [CLI 完整对照](evidence/demo/comparison.json)、[摘要](evidence/comparison-summary.json)：四策略候选池摘要相同；所选上下文均 282 字节。传统对照按相似度返回案例；D1 将条件适用的防御例标为 SUPPORT、漏洞例标为 CONTRAST。该结果只说明机制路径，不是性能提升或统计显著性。
- [CLI 帮助](evidence/retrieval-help.log)：新入口可独立运行，不装配模型。
- [Milvus 冒烟](evidence/milvus-smoke.json)：两份知识块、合成 2 维向量；本地与真实 Milvus 返回的 pool 完全相同。全量快照内容已读回并通过 S1b 激活门禁。
- 源码及文档摘要、空白检查记录在 [产物检查](evidence/artifact-check.json)。

## Milvus 运行记录

本地已有镜像 `milvusdb/milvus:v2.6.4`（arm64）。使用本轮专属容器 `smartcontract-s2-milvus-20260921`，只绑定 `127.0.0.1:29530` 与 `127.0.0.1:29091`；使用嵌入式 etcd、本地存储和唯一 `s1b_` 集合，未访问或修改旧集合。

首次启动因镜像在命令行初始化前读取部署模式而失败，日志为 [首次启动记录](evidence/milvus-initial-start.log)。核对 v2.6.4 源码后设置 `DEPLOY_MODE=STANDALONE`，健康检查 OK，后续创建/插入/读回/激活/搜索全部成功。验证后停止本轮容器释放资源，保留容器及合成数据，未删除用户镜像或现有服务。

自动化单元测试不连接该容器。REST 适配的网络测试仅启动临时本地 HTTP 夹具；Java 模型测试沿用原有本地 HTTP 夹具，程序事实执行本仓库确定性 Python 脚本。

## 审查与限制

见 [REVIEW](REVIEW.md)：09-22 独立复审已完成，短路、多维索引、下标重绑定及双向别名问题已闭环，最新全套验证通过。当前工程状态为 READY_TO_SHIP；研究效果仍 UNVERIFIED，未执行发布。Milvus 冒烟运行日期为 09-21，本次未重启或修改该容器。

示例中的 REVIEWED 仅指人工构造机制夹具的明确预期，不能作为真实项目的人工/专家审核证据。没有真实开发配对、正式检索相关性标签、模型下游实验或同 token 预算显著性结果；S2 的“可证伪先导”研究部分仍需后续执行。轻量词法结构提取不提供编译、CFG、跨函数可达性或通用保护有效性证明；STATE_WRITE_BEFORE 不证明具体更新值已足以消除重入。未将工程接口完成表述为论文创新已经成立。
