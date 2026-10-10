# R1-S9 实施计划与技术边界

当前阶段：Testing 已完成；状态：READY_TO_SHIP / ACTIVE；工程验证 VERIFIED，正式发布授权 NOT_REQUESTED。需求基线见 [SPEC](SPEC.md)，[评审](REVIEW.md)和[验收](VERIFICATION.md)保存完成证据。开发基点：`0b40b4b`；本轮完成提交以 Git 历史为准，开始时无关改动保留。

复用 `BenchmarkRuntime` 的 Nomic/BGE 查询与 Java D1、`audit_run.model_runner/tool_runner` 的受控子进程。新增工作台编排负责目标输入、预览冻结、六阶段事件和内容摘要校验。HTTP 使用现有本机服务与全局运行锁；不接受可执行路径、模型端点或集合名。前端使用独立静态资源，源码和模型输出只作为文本。

1. 输入与编排：解析受限语法树，绑定源码/函数/行范围；预置与粘贴统一进入固定快照；计划绑定源码、候选池、上下文、模式与供应商。默认离线不会运行模型或真实工具。
2. D2：逐项核查六类义务；`verdict` 针对漏洞，`protectionVerdict` 针对保护；证据不足保持 UNKNOWN。此纯函数任务与新前端可并行，其他公共接口串行整合。
3. 前端：预览后才运行，显示六阶段与过程证据，下载和重放报告，链接批量台。
4. 集成：单样本与批量共用 D2；更新旧入口聚合语义，历史 schema=1 不重写。
5. Review：独立审查规格与代码，抽查安全与公用函数；局部测试通过后才进入系统验收。
6. Testing：根 Maven、Python、脚本检查及真实 Chromium；固定本机 Nomic 检索冒烟零付费请求。证据在 `.evidence/R1-S9/`，不把工程演练写成科研结论。
7. 依项目约定检查差异和凭证，完成后提交及同步 origin/main；外部正式部署/发布不在本次范围。

任务契约：目标为 SPEC 中的七项功能与输入门禁；测试缝为注入检索、模型、工具适配器及临时目录 HTTP。**REQUIRED SUB-SKILL:** Use superpowers:test-driven-development。初轮可用目录未列出 superpowers，采用原生失败用例→实现→回归、方案比较、依赖顺序与代理契约；复审修复阶段发现缓存中的 TDD 与 verification-before-completion 文件并完整读取执行。独立规格、代码、消肿和安全评审记录在 REVIEW。配置差异反复出现时暂停补丁，按 investigate 完成根因调查与恢复。

持久化仅新增 `.local/audit-workbench-runs/`，每个运行保存 plan、target、preview、events、result 与 sample.jsonl；摘要覆盖目标、检索、计划和结果。读取方为 HTTP、页面和离线报告；运行中状态来自内存活动编号与事件，服务重启后未封口运行标为 INTERRUPTED，不自动补发模型请求。
