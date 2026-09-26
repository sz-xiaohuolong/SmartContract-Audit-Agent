# 本机 Milvus 与真实模型工程试跑

本页用于检查“固定真实源码 → 本机 Milvus 检索 → 一次模型调用 → 本机报告 → 页面回看”的工程链路。它不是正式论文实验：首批知识与检测样本仍待独立标签审核，本机词法哈希向量只供联调，不能代替正式嵌入模型或 D1 研究对照。

## 数据边界

- 知识候选：`AC-ASE-040` 与 `RE-POP-077` 两个已固定源码的项目组。工程索引含两个原始风险代码片段，以及 `AC-ASE-040` 同组真实修复源码片段，共三条。修复片段仅标为补丁上下文，不被当作全局安全负例。
- 检测目标：开发划分中的固定源码 `AC-ASE-006`。页面不提供更换样本或打开锁定测试的参数。
- 构建前重新核对首批名单的源码、报告和补丁摘要及项目隔离。新 Milvus 集合写完后必须完整回读，校验通过才写入 `active.json`。激活后每次查询再次核对本地源码谱系、快照摘要和集合内容。
- 索引与运行产物分别位于被 Git 忽略的 `.local/mvp-kb/`、`.local/mvp-milvus/`、`.local/mvp-runs/`。这些目录只供本机工程验收；正式科研知识快照仍未激活。

## 启动与人工验收

在项目根目录构建后，启动本机 Milvus 容器 `smartcontract-mvp-milvus-20260926`。首次可使用项目本机 `.local/mvp-milvus/` 中的容器配置，或按 Milvus v2.6.4 standalone embed 官方脚本重建等价容器；本机端口固定为 `127.0.0.1:29531`。然后运行：

```bash
mvn clean verify
PYTHONPATH=tools/experiment python3 tools/experiment/mvp_runtime.py build
PYTHONPATH=tools/experiment python3 tools/experiment/mvp_runtime.py status
PYTHONPATH=tools/experiment python3 tools/experiment/local_ui.py --port 8767
```

打开 `http://127.0.0.1:8767/mvp.html`。页面应显示“快照已就绪”和三条向量片段。点击“调用真实模型并保存结果”会产生**最多一次**火山 Agent Plan 请求；每次点击都是新的付费尝试，历史记录点击只读取磁盘。也可用 `PYTHONPATH=tools/experiment python3 tools/experiment/mvp_runtime.py run` 单独执行一次。需要先在被 Git 忽略的 `config/providers.local.properties` 填好 `providers.ark.api-key`，且模型为已核实的 `deepseek-v4-flash` 或 `deepseek-v4.1-flash`，端点必须是 `https://ark.cn-beijing.volces.com/api/plan/v3`。

每次运行固定为 `1 样本 × 1 策略 × 1 重复 × 1 模型阶段 × 0 重试`，最多一次请求；用户消息不超过 10000 UTF-8 字节，检索证据不超过 2048 字节，`max_completion_tokens=2048` 请求限制回答与推理合计长度，模型等待上限 180 秒。字节上限不等于真实 token 预算；实际输入、输出 token 以供应商 usage 为准，缺失时保持 `null`。任何错误均保留 `FAILED/UNRESOLVED`，不自动重试、不转写为安全。

每个 `.local/mvp-runs/<runId>/` 下依次保存 `plan.json`、`started.json` 和 `result.json`。若中途断电或超时，保留启动标记；再次启动不会自动重放这次请求。报告中的 `researchEligible=false` 表示它只能说明工程链路状态，不能计算 D1 提升或漏洞检测准确率。
