# 开题报告工作流工具

本目录管理本地材料快照、任务依赖、摘要验收、合成辅助及 Word 样例填充。代理派发与学术判断由当前 Codex 会话执行；脚本不会调用模型、自动开展研究实验或建立后台服务。

## 验证

```bash
PYTHONPATH=tools/proposal_workflow python3 -m unittest discover -s tools/proposal_workflow/tests -v
```

检查依赖、重复派发、输入和产物漂移、空输出、路径及符号链接越界、原子写入、嵌套题录、错批次数字与未验收合成。Word 验证使用真实样例生成与逐页渲染，不能由单元测试代替。

## 新轮次

使用 `init` 配置显式的 Git 提交、需要冻结的已提交文件和本地原件。初始化拒绝覆盖既有状态或目录，不读取整个仓库；凭证文件不得登记。旧轮次必须先人工确认并保留，新控制目录可另行指定。

```json
{
  "commit": "明确的提交或引用",
  "git_paths": ["已提交文档或源码的相对路径"],
  "local_paths": ["本地已固定原件的相对路径"],
  "batch_id": "需要使用的研究批次或空值"
}
```

```bash
python3 tools/proposal_workflow/workflow.py --root . --run thesis/开题报告/自动化工作流/runs/新轮次 init /tmp/本轮输入.json
```

本地原件登记 SHA-256；已提交资料复制到本轮快照。以后派发与验收都先核对材料摘要，变化时停止该动作并报出具体路径。脚本只固定显式输入，原始文献仍可通过独立的主张与来源台账登记。

## 当前轮次的常用操作

```bash
PROPOSAL_RUN=thesis/开题报告/自动化工作流/runs/proposal-20261010-01
python3 tools/proposal_workflow/workflow.py --run "$PROPOSAL_RUN" verify
python3 tools/proposal_workflow/workflow.py --run "$PROPOSAL_RUN" status
python3 tools/proposal_workflow/workflow.py --run "$PROPOSAL_RUN" start T02 --agent /root/literature_writer
python3 tools/proposal_workflow/workflow.py --run "$PROPOSAL_RUN" accept T02 "$PROPOSAL_RUN/草稿/L/正文.md" --note 已核对正文和原始证据
python3 tools/proposal_workflow/workflow.py --run "$PROPOSAL_RUN" assemble "$PROPOSAL_RUN/草稿/拼接.md" "$PROPOSAL_RUN/草稿/L/正文.md"
python3 tools/proposal_workflow/workflow.py --run "$PROPOSAL_RUN" check "$PROPOSAL_RUN/交付/正文_稳定引用键.md" "$PROPOSAL_RUN/引用工作集.bib"
python3 tools/proposal_workflow/workflow.py --run "$PROPOSAL_RUN" metrics "$PROPOSAL_RUN/数字主张.json" "$PROPOSAL_RUN/最新实验数字.json"
```

已执行或已验收任务不能重复 `start`。状态中执行中任务的代理 ID 仅是会话句柄，总控应实际核对是否存活。文件存在或代理结束均不能代替内容验收。公共 JSON 用原子替换，事件追加并 fsync；操作锁防止同时修改状态，不提供整轮跨会话的自动租约或代理运行服务。

`assemble` 只合成已验收且摘要未变的产物；总控仍需处理顺序、重复章节、论证与图表。`check` 检查稳定引用键、链接和围栏；`metrics` 按已登记路径核对数字与父批次。它们不能判断引文支持强度或自动解释未登记的正文数字，完整事实审查必须读原始证据。

## Word 生成

先遵循 documents 技能：解析并保留参考样例、完成本轮 `artifact.md` 格式契约，成功执行一次官方文档创建标记。随后用 Codex 依赖加载器返回的 Python 运行：

```bash
"$PROPOSAL_PYTHON" tools/proposal_workflow/build_docx.py \
  --reference /绝对路径/保留的参考.docx \
  --markdown /绝对路径/已审查正文.md \
  --output /绝对路径/开题报告审阅稿.docx \
  --contract /绝对路径/artifact.md \
  --reference-sha256 已核对的参考摘要
```

生成器针对本轮海南大学样例的五部分表单槽位，不是任意学校模板转换器。保留样例页几何、网格、全部表单行与未编辑包成员，替换正文、旧身份及旧意见，插入三图和数字参考资料；行政字段明确待填，真实评审为空。样例封面跨页及页码框截断按契约修复。已定位的标题与首段使用无边框组件分组，报告会区域移为同网格续表，修复长表单中的孤立标题和表头分离。Word 的正文、题录、表格可编辑；图另附可编辑 SVG 与 Mermaid 源。

必须继续使用 documents 的 `render_docx.py` 渲染并逐页检查。文件生成成功不表示排版通过。该工具不自动安装字体、刷新 Word 缓存或使用 LibreOffice 保存最终文件；设置 `updateFields`，页码在 Word 打开时更新。任务使用本地字体映射时在本轮 `fonts.conf` 中记录，不改原件字体声明。

## 本轮边界

本轮首期只形成开题审阅稿和可恢复证据，不自动发送导师或提交学院。工程与实验只使用指定快照；自动化写作流程不属于毕设算法创新。新增研究付费调用上限为零。
