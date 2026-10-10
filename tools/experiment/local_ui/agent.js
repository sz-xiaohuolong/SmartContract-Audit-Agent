const byId = id => document.getElementById(id);
let targets = [];
let status = null;
let batchPlan = null;
let autoTargets = [];
let autoPlanState = null;
const show = (id, value) => { byId(id).textContent = value; };
const json = value => JSON.stringify(value, null, 2);

async function request(path, options) {
  const response = await fetch(path, options);
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || '请求失败');
  return body;
}

async function load() {
  try {
    const [state, registry] = await Promise.all([request('/api/agent/status'), request('/api/agent/targets')]);
    status = state;
    targets = registry.targets;
    const selector = byId('sample');
    selector.replaceChildren();
    for (const target of targets) {
      const option = document.createElement('option');
      option.value = target.sampleId;
      option.textContent = target.sampleId + (target.split === 'validation' ? ' · 独立验证' : ' · 开发') + (target.runnable ? '' : ' · 暂不可运行');
      option.disabled = !target.runnable;
      selector.append(option);
    }
    selector.selectedIndex = Math.max(0, targets.findIndex(item => item.runnable));
    selector.onchange = showScope;
    showScope();
    show('snapshot', state.ready ? `${state.snapshotId}\n${state.collection || ''}` : '正式快照暂不可用');
    const pending = state.pendingKnowledge;
    show('knowledge-status', state.ready ? `活动知识快照：${state.formalVectors ?? '待核对'} 条向量，标签等级：${state.knowledgeTier === 'AUTO_LABELED' ? '自动标注（未逐案复核）' : '经审'}。${pending ? `探索集合另存 ${pending.vectors} 条候选（AutoMESC ${pending.automescPairs} 组、FORGE ${pending.forgeVfp} 条）；该集合不作为本页批量模型的活动知识。` : ''}` : '知识快照暂不可用。');
    show('provider', state.realReady ? `真实运行：${state.endpoint} · ${state.model}` : '真实模型配置未就绪；仍可查看历史与目标。');
    byId('real').disabled = !state.ready || !state.realReady;
    byId('offline').disabled = !state.ready;
    renderBatchChoices();
    await loadAutoTargets();
    await loadAutoHistory();
    await loadBatchHistory();
    await loadHistory();
    await loadExploratory();
  } catch (error) { show('notice', error.message); }
}
async function loadAutoTargets() {
  try {
    autoTargets = (await request('/api/agent/auto-benchmark/targets')).targets;
    const region = byId('auto-targets'); region.replaceChildren();
    for (const target of autoTargets) {
      const label = document.createElement('label');
      const input = document.createElement('input');
      input.type = 'checkbox'; input.name = 'auto-sample'; input.value = target.sampleId;
      input.checked = !!target.runnable; input.disabled = !target.runnable;
      input.onchange = invalidateAutoPlan;
      label.append(input, document.createTextNode(` ${target.sampleId} · ${target.groundTruth.hasVulnerability ? '数据集漏洞' : '安全对照'}${target.runnable ? '' : ' · 暂不可运行'}`));
      region.append(label);
    }
    show('auto-target-summary', `选择验证目标（${autoTargets.filter(item => item.runnable).length} 个可运行）`);
    show('auto-notice', '可选择目标与策略，查看计划后启动。');
    document.querySelectorAll('input[name="auto-strategy"]').forEach(input => input.onchange = invalidateAutoPlan);
    byId('auto-mode').onchange = invalidateAutoPlan;
    byId('auto-embedding').onchange = invalidateAutoPlan;
  } catch (error) { show('auto-notice', error.message); }
}
function invalidateAutoPlan() {
  autoPlanState = null;
  byId('auto-start').disabled = true;
  show('auto-plan-detail', '选择已改变，请重新查看计划。');
}
function autoChoice() {
  return {sampleIds: [...document.querySelectorAll('input[name="auto-sample"]:checked')].map(input => input.value),
    strategies: [...document.querySelectorAll('input[name="auto-strategy"]:checked')].map(input => input.value),
    mode: byId('auto-mode').value, embeddingProfile: byId('auto-embedding').value};
}
async function previewAutoPlan() {
  invalidateAutoPlan();
  try {
    const plan = await request('/api/agent/auto-benchmark/plan', {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(autoChoice())});
    autoPlanState = plan;
    show('auto-plan-detail', `目标 ${plan.sampleIds.length} × 策略 ${plan.strategies.length}；嵌入 ${plan.embeddingProfile || 'bge'}；快照 ${plan.snapshotId}\n模式：${plan.mode === 'real' ? '真实模型' : '固定离线空假设'}；模型：${plan.provider?.model || '不调用'}；最多 ${plan.requestBounds.maxRequests} 次请求、${plan.requestBounds.maxOutputTokens} 输出 token。\n指标按数据集标签计算；失败和未知不算作安全预测。`);
    byId('auto-start').disabled = false;
    byId('auto-start').textContent = plan.mode === 'real' ? '开始真实批量审计' : '开始离线批量验收';
    show('auto-notice', '计划已固定，点击启动后逐项保存。');
  } catch (error) { show('auto-notice', error.message); }
}
function renderAutoReport(report) {
  const region = byId('auto-result'); region.replaceChildren();
  const summary = document.createElement('p');
  summary.textContent = `${report.status === 'COMPLETED' ? '运行结束' : '运行中'} · 计划 ${report.denominators.planned} · 完成 ${report.denominators.completed} · 失败 ${report.denominators.failed} · 未知 ${report.denominators.unknown} · 待处理 ${report.denominators.pending}`;
  region.append(summary);
  const origin = document.createElement('p');
  origin.textContent = `嵌入：${report.plan.embeddingProfile || 'bge'}；快照：${report.plan.snapshotId}` + (report.plan.parseReplay ? `；原文重放自 ${report.plan.parseReplay.originalBatchId}，追加模型请求 0 次。` : '；原始运行记录。');
  region.append(origin);
  const table = document.createElement('table'); table.className = 'agent-metrics';
  const head = document.createElement('tr');
  for (const title of ['策略', 'TP', 'FP', 'FN', 'TN', 'Precision', 'Recall', 'F1', '类别命中@K', '平均输入 token', '平均输出 token', '平均模型耗时 ms', '模型失败/未知', 'D2 支持/反驳/未知', '流水线失败']) {
    const cell = document.createElement('th'); cell.textContent = title; head.append(cell);
  }
  table.append(head);
  for (const [strategy, row] of Object.entries(report.metrics)) {
    const tr = document.createElement('tr');
    for (const value of [strategy, row.tp, row.fp, row.fn, row.tn, metric(row.precision), metric(row.recall), metric(row.f1),
      metric(row.retrievalHitAtK), metric(row.avgInputTokens), metric(row.avgOutputTokens), metric(row.avgDurationMs), `${row.failed}/${row.unknown}`,
      row.d2NotRun === row.planned ? '未核验（历史版本）' : `${row.d2Supported || 0}/${row.d2Refuted || 0}/${row.d2Unknown || 0}`,
      row.pipelineFailed ?? '—']) {
      const cell = document.createElement('td'); cell.textContent = String(value); tr.append(cell);
    }
    table.append(tr);
  }
  region.append(table);
  const pairedTitle = document.createElement('h3');
  pairedTitle.textContent = `三策略共同有效目标对照（${report.pairedSamples?.length || 0} 个目标）`;
  region.append(pairedTitle);
  const paired = document.createElement('table'); paired.className = 'agent-metrics';
  const pairedHead = document.createElement('tr');
  for (const title of ['策略', '共同目标', 'TP', 'FP', 'FN', 'TN', 'Precision', 'Recall', 'F1']) {
    const cell = document.createElement('th'); cell.textContent = title; pairedHead.append(cell);
  }
  paired.append(pairedHead);
  for (const [strategy, row] of Object.entries(report.pairedMetrics || {})) {
    const tr = document.createElement('tr');
    for (const value of [strategy, row.samples, row.tp, row.fp, row.fn, row.tn,
      metric(row.precision), metric(row.recall), metric(row.f1)]) {
      const cell = document.createElement('td'); cell.textContent = String(value); tr.append(cell);
    }
    paired.append(tr);
  }
  region.append(paired);
  const progressTitle = document.createElement('h3'); progressTitle.textContent = '逐项运行进度';
  region.append(progressTitle);
  const progressWrap = document.createElement('div'); progressWrap.className = 'agent-progress-scroll';
  const progress = document.createElement('table'); progress.className = 'agent-metrics';
  const progressHead = document.createElement('tr');
  for (const title of ['目标', '策略', '数据集标签', '模型状态', '模型结论', '流水线状态', 'D2 漏洞裁决', '最终结论', '错误类别', '模型耗时 ms']) {
    const cell = document.createElement('th'); cell.textContent = title; progressHead.append(cell);
  }
  progress.append(progressHead);
  const resultIndex = new Map(report.samples.map(item => [`${item.sampleId}|${item.strategy}`, item]));
  for (const sampleId of report.plan.sampleIds) for (const strategy of report.plan.strategies) {
    const row = resultIndex.get(`${sampleId}|${strategy}`);
    const tr = document.createElement('tr');
    const label = report.plan.labels[sampleId].hasVulnerability ? '漏洞' : '安全对照';
    for (const value of [sampleId, strategy, label, row?.status || '待处理', row?.prediction || '—',
      row?.pipelineStatus || '—', row?.d2?.verdict || '未核验', row?.conclusion || '—',
      row?.errorCategory || '—', metric(row?.durationMs, '—')]) {
      const cell = document.createElement('td'); cell.textContent = String(value); tr.append(cell);
    }
    progress.append(tr);
  }
  progressWrap.append(progress); region.append(progressWrap);
  const note = document.createElement('p'); note.className = 'agent-muted';
  note.textContent = 'TP/FP/FN/TN 保留模型“报告／未报告”的原口径；工具失败另列流水线失败，最终结论保持未决。D2 裁决以漏洞假设为对象，反驳特定假设不表示全合约安全；旧报告未核验。类别命中仅为代理指标，离线空假设保持未知。';
  region.append(note);
  if (report.poolConflicts.length) {
    const conflict = document.createElement('p'); conflict.textContent = '候选池不一致：' + report.poolConflicts.join('、'); region.append(conflict);
  }
  if (report.error) { const error = document.createElement('p'); error.textContent = report.error; region.append(error); }
  const details = document.createElement('details');
  const title = document.createElement('summary'); title.textContent = `查看 ${report.samples.length} 条逐样本记录`; details.append(title);
  const body = document.createElement('pre'); body.textContent = json(report.samples); details.append(body); region.append(details);
  byId('auto-jsonl').href = '/api/agent/auto-benchmark/runs/' + report.batchId + '/samples.jsonl';
  byId('auto-csv').href = '/api/agent/auto-benchmark/runs/' + report.batchId + '/samples.csv';
  byId('auto-jsonl').hidden = report.samples.length === 0;
  byId('auto-csv').hidden = report.samples.length === 0;
}
async function pollAuto(batchId) {
  for (let attempt = 0; attempt < 1200; attempt++) {
    const report = await request('/api/agent/auto-benchmark/runs/' + batchId);
    renderAutoReport(report);
    if (report.status === 'COMPLETED' || report.error) {
      show('auto-notice', `报告目录：.local/auto-benchmark-runs/${batchId}/`);
      await loadAutoHistory(); return;
    }
    await new Promise(resolve => setTimeout(resolve, 2000));
  }
  show('auto-notice', `页面等待结束，可从历史记录继续查看 ${batchId}。`);
}
async function startAuto() {
  if (!autoPlanState) return;
  byId('auto-start').disabled = true;
  try {
    const created = await request('/api/agent/auto-benchmark/runs', {method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({...autoChoice(), planHash: autoPlanState.planHash})});
    show('auto-notice', '批量运行中，逐项结果已开始写入。');
    await pollAuto(created.batchId);
  } catch (error) { show('auto-notice', error.message); }
  finally { byId('auto-start').disabled = false; }
}
async function loadAutoHistory() {
  try {
    const {batches} = await request('/api/agent/auto-benchmark/runs');
    const region = byId('auto-history'); region.replaceChildren();
    if (!batches.length) { region.textContent = '暂无自动知识批量历史。'; return; }
    for (const item of batches) {
      const button = document.createElement('button'); button.className = 'agent-history';
      button.textContent = `${item.batchId.slice(0, 8)} · ${item.planned} 项 · ${item.status} · ${item.mode} · ${item.embeddingProfile || 'bge'}${item.parseReplay ? ' · 原文重放' : ''}`;
      button.onclick = async () => {
        try { renderAutoReport(await request('/api/agent/auto-benchmark/runs/' + item.batchId)); }
        catch (error) { show('auto-notice', error.message); }
      };
      region.append(button);
    }
  } catch (error) { show('auto-history', error.message); }
}
async function loadExploratory() {
  try {
    const state = await request('/api/agent/exploratory');
    const region = byId('exploratory-result'); region.replaceChildren();
    if (!state.report) { region.textContent = state.running ? '正在检索并逐样本保存。' : '尚无探索性运行。'; return; }
    const report = state.report;
    const rows = report.results.filter(item => item.status === 'COMPLETED');
    const count = strategy => rows.filter(item => item.selected[strategy]?.length).length;
    const summary = document.createElement('p');
    summary.textContent = `${state.running ? '运行中 · ' : ''}计划 ${report.denominators.planned} 个源码，已完成 ${report.denominators.completed}，失败 ${report.denominators.failed}，未知 ${report.denominators.unknown}。有证据入选的目标：向量 ${count('DENSE')}、条件过滤 ${count('FIELD_FILTER')}、D1 ${count('D1')}。`;
    region.append(summary);
    const note = document.createElement('p'); note.className = 'agent-muted';
    note.textContent = '入选数量只反映检索覆盖；待审补丁与仅来源头标签不能证明哪种策略更会发现真实漏洞。检测召回率与 D1 增益保持空值。';
    region.append(note);
    const details = document.createElement('details');
    const title = document.createElement('summary'); title.textContent = `查看 ${report.results.length} 条逐样本检索记录`; details.append(title);
    const body = document.createElement('pre'); body.textContent = json(report.results); details.append(body); region.append(details);
    if (state.running) setTimeout(loadExploratory, 2000);
  } catch (error) { show('exploratory-result', error.message); }
}
async function startExploratory() {
  byId('exploratory-start').disabled = true;
  try {
    await request('/api/agent/exploratory', {method: 'POST'});
    await loadExploratory();
  } catch (error) { show('exploratory-result', error.message); }
  finally { byId('exploratory-start').disabled = false; }
}
function renderBatchChoices() {
  const region = byId('batch-targets');
  region.replaceChildren();
  for (const target of targets.filter(item => item.split === 'validation')) {
    const label = document.createElement('label');
    const input = document.createElement('input');
    input.type = 'checkbox'; input.name = 'batch-sample'; input.value = target.sampleId;
    input.checked = !!target.runnable; input.disabled = !target.runnable;
    input.onchange = invalidateBatchPlan;
    label.append(input, document.createTextNode(` ${target.sampleId} · ${target.scope === 'FUNCTION' ? '函数级' : '完整源码'}${target.runnable ? '' : ' · 暂不可运行'}`));
    region.append(label);
  }
  document.querySelectorAll('input[name="batch-strategy"]').forEach(input => input.onchange = invalidateBatchPlan);
  byId('batch-mode').onchange = invalidateBatchPlan;
}
function invalidateBatchPlan() {
  batchPlan = null;
  byId('batch-start').disabled = true;
  show('batch-plan-detail', '选择已改变，请重新查看运行计划。');
}
function batchChoice() {
  return {sampleIds: [...document.querySelectorAll('input[name="batch-sample"]:checked')].map(input => input.value),
    strategies: [...document.querySelectorAll('input[name="batch-strategy"]:checked')].map(input => input.value), mode: byId('batch-mode').value};
}
async function previewBatchPlan() {
  invalidateBatchPlan();
  try {
    const plan = await request('/api/agent/batches/plan', {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(batchChoice())});
    batchPlan = plan;
    const bounds = plan.requestBounds;
    show('batch-plan-detail', `${bounds.samples} 个目标 × ${bounds.strategies} 种策略 × ${bounds.repeats} 次重复 × ${bounds.modelStages} 个模型阶段 × ${bounds.attemptsPerUnit} 次尝试\n正式快照：${plan.snapshotId}\n模型：${plan.provider ? plan.provider.endpoint + ' · ' + plan.provider.model : '固定离线空假设'}\n请求上界：${bounds.maxRequests}；输出 token 上界：${bounds.maxOutputTokens}；输入字节上界：${bounds.maxInputBytes}；完整输入 token 上界：${metric(bounds.maxInputTokens, '尚未锁定')}；费用上界：${metric(bounds.maxCost, '尚未锁定')}。\n每项结果写入本机报告，失败和未知单独统计。`);
    byId('batch-start').disabled = false;
    byId('batch-start').textContent = plan.mode === 'real' ? '开始真实批量对照' : '开始离线批量对照';
    show('batch-notice', plan.mode === 'real' ? '计划已固定；点击启动后将逐项调用真实模型。' : '计划已固定，可以开始离线对照。');
  } catch (error) { show('batch-notice', error.message); }
}
function metric(value, unavailable = '待核验') { return value === null || value === undefined ? unavailable : String(value); }
function renderBatchReport(report) {
  const region = byId('batch-result');
  region.replaceChildren();
  const heading = document.createElement('p');
  heading.textContent = `${report.status === 'COMPLETED' ? '运行结束' : '运行中'} · 计划 ${report.denominators.planned} · 完成 ${report.denominators.completed} · 失败 ${report.denominators.failed} · 未知 ${report.denominators.unknown} · 待处理 ${report.denominators.pending}`;
  region.append(heading);
  const table = document.createElement('table'); table.className = 'agent-metrics';
  const head = document.createElement('tr');
  for (const value of ['策略', '完成', '失败', '未知', '报告漏洞', '未决', '入选证据', '输入 token', '输出 token', '检测召回', '检索 Recall@K / nDCG']) {
    const cell = document.createElement('th'); cell.textContent = value; head.append(cell);
  }
  table.append(head);
  for (const [strategy, row] of Object.entries(report.metrics)) {
    const tr = document.createElement('tr');
    for (const value of [strategy, row.completed, row.failed, row.unknown, row.reported ?? 0, row.unresolved ?? 0, row.selectedEvidence,
      metric(row.inputTokens, '未返回'), metric(row.outputTokens, '未返回'), metric(row.detectionRecall),
      `${metric(row.retrievalRecallAtK)} / ${metric(row.ndcgAtK)}`]) {
      const cell = document.createElement('td'); cell.textContent = String(value); tr.append(cell);
    }
    table.append(tr);
  }
  region.append(table);
  const blockers = document.createElement('p');
  blockers.className = 'agent-muted'; blockers.textContent = `论文指标暂不可计算：${report.metricBlockers.join('；')}。${report.poolConflicts.length ? '候选池不一致：' + report.poolConflicts.join('、') : '已记录同目标候选池一致性。'}`;
  region.append(blockers);
  const samples = document.createElement('details');
  const title = document.createElement('summary'); title.textContent = `查看逐样本状态（${report.samples.length} 项）`; samples.append(title);
  const body = document.createElement('pre'); body.textContent = json(report.samples); samples.append(body); region.append(samples);
  const link = byId('batch-report'); link.href = '/api/agent/batches/' + report.batchId + '/report'; link.hidden = report.samples.length === 0;
}
async function startBatch() {
  if (!batchPlan) return;
  byId('batch-start').disabled = true;
  show('batch-notice', '批量对照已开始，结果会逐项写入。');
  try {
    const created = await request('/api/agent/batches', {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({...batchChoice(), planHash: batchPlan.planHash})});
    const identifier = created.batchId;
    for (let attempt = 0; attempt < 360; attempt++) {
      await new Promise(resolve => setTimeout(resolve, 1000));
      let report;
      try { report = await request('/api/agent/batches/' + identifier); }
      catch (error) { if (attempt < 3) continue; throw error; }
      renderBatchReport(report);
      if (report.status === 'COMPLETED') {
        show('batch-notice', `已保存：.local/audit-batches/${identifier}/`);
        await loadBatchHistory(); return;
      }
    }
    show('batch-notice', `页面等待结束，可从历史打开运行 ${identifier}。`);
  } catch (error) { show('batch-notice', error.message); }
}
async function loadBatchHistory() {
  try {
    const {batches} = await request('/api/agent/batches');
    const region = byId('batch-history'); region.replaceChildren();
    if (!batches.length) { region.textContent = '暂无批量历史。'; return; }
    for (const item of batches) {
      const button = document.createElement('button'); button.className = 'agent-history';
      button.textContent = `${item.batchId.slice(0, 8)} · ${item.planned} 项 · ${item.status} · ${item.mode}`;
      button.onclick = async () => {
        try { renderBatchReport(await request('/api/agent/batches/' + item.batchId)); }
        catch (error) { show('batch-notice', error.message); }
      };
      region.append(button);
      if (item.status === 'RUNNING') {
        const resume = document.createElement('button'); resume.className = 'agent-history';
        resume.textContent = `继续未完成的${item.mode === 'real' ? '真实' : '离线'}批量运行 ${item.batchId.slice(0, 8)}`;
        resume.onclick = async () => {
          try {
            const report = await request('/api/agent/batches/' + item.batchId);
            await request('/api/agent/batches/' + item.batchId + '/resume', {method: 'POST',
              headers: {'Content-Type': 'application/json'}, body: JSON.stringify({planHash: report.plan.planHash})});
            show('batch-notice', '续跑已启动；曾开始但没有结果的项记为未决，不会重新调用。');
          } catch (error) { show('batch-notice', error.message); }
        };
        region.append(resume);
      }
    }
  } catch (error) { show('batch-history', error.message); }
}
function showScope() {
  const target = targets.find(item => item.sampleId === byId('sample').value);
  show('scope', target ? `${target.split === 'validation' ? '独立验证' : '工程开发'} · ${target.scope === 'FUNCTION' ? '函数级，非完整合约' : '整份源码'} · ${target.reason || '可运行'} · 原始行 ${target.lineStart || '?'}–${target.lineEnd || '?'}` : '无可运行目标');
}
async function preview() {
  try {
    const data = await request('/api/agent/preview?sampleId=' + encodeURIComponent(byId('sample').value) + '&strategy=' + encodeURIComponent(byId('strategy').value));
    show('retrieval', json({snapshotId: data.snapshotId, collection: data.collection,
      strategy: data.strategy, poolHash: data.poolHash, candidatePool: data.pool, selected: data.d1.selected, status: data.d1.status,
      gaps: data.d1.gaps, evaluations: data.d1.evaluations}));
  } catch (error) { show('retrieval', error.message); }
}
function showResult(data) {
  show('result', json({sampleId: data.plan.sampleId, scope: data.plan.scope,
    strategy: data.plan.strategy, poolHash: data.plan.poolHash,
    status: data.status, conclusion: data.conclusion, model: data.model,
    tools: data.tools, d2: data.d2,
    d2VerdictSubject: data.d2?.schemaVersion === '2' ? '漏洞假设' : '保护覆盖（历史版本）',
    denominators: data.denominators,
    sourceHash: data.plan.sourceHash, snapshotId: data.plan.snapshotId}));
  const link = byId('report');
  link.href = '/api/agent/runs/' + data.runId + '/report';
  link.hidden = false;
}
async function run(mode) {
  const target = targets.find(item => item.sampleId === byId('sample').value);
  if (!target || !target.runnable) return;
  if (mode === 'real') {
    const choice = window.confirm(`确认运行 ${target.sampleId}（${target.scope === 'FUNCTION' ? '函数级' : '整份源码'}）？\n策略：${byId('strategy').value}\n端点：${status.endpoint}\n模型：${status.model}\n最多 2 次请求（瞬时错误仅重试一次），输出上限 2048 token。`);
    if (!choice) return;
  }
  byId('offline').disabled = true;
  byId('real').disabled = true;
  show('notice', mode === 'real' ? '真实模型运行中，请勿重复点击。' : '离线演练运行中。');
  try {
    const data = await request('/api/agent/runs', {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({sampleId: target.sampleId, mode, strategy: byId('strategy').value})});
    showResult(data);
    show('notice', `运行记录：.local/audit-runs/${data.runId}/`);
    await loadHistory();
  } catch (error) { show('notice', error.message); }
  finally { byId('offline').disabled = !status.ready; byId('real').disabled = !status.realReady; }
}
async function loadHistory() {
  try {
    const data = await request('/api/agent/runs');
    const region = byId('history');
    region.replaceChildren();
    if (!data.runs.length) { region.textContent = '暂无历史记录。'; return; }
    for (const item of data.runs) {
      const button = document.createElement('button');
      button.className = 'agent-history';
      button.textContent = `${item.sampleId} · ${item.strategy || 'D1'} · ${item.mode} · ${item.status} · ${item.createdAt}`;
      button.onclick = async () => {
        try { showResult(await request('/api/agent/runs/' + item.runId)); }
        catch (error) { show('notice', error.message); }
      };
      region.append(button);
    }
  } catch (error) { show('history', error.message); }
}
byId('preview').onclick = preview;
byId('batch-plan').onclick = previewBatchPlan;
byId('batch-start').onclick = startBatch;
byId('offline').onclick = () => run('offline');
byId('real').onclick = () => run('real');
byId('auto-plan').onclick = previewAutoPlan;
byId('auto-start').onclick = startAuto;
byId('exploratory-start').onclick = startExploratory;
byId('exploratory-refresh').onclick = loadExploratory;

/* 单合约主工作区使用同一后端审计契约；批量视图按需加载。 */
(() => {
  const state = {status: {}, targets: [], preview: null, data: null, busy: false,
    revision: 0, statusRevision: 0, batchLoaded: false, pairs: [], sourceKind: 'full'};
  const obligations = [['actor', '主体绑定'], ['resource', '资源绑定'], ['pre_risk_guard', '风险前保护'],
    ['entry_coverage', '入口覆盖'], ['state_version', '状态版本'], ['bypass', '旁路检查']];
  const stages = [['FACTS', '程序事实'], ['D1', '对比检索'], ['MODEL', '模型假设'],
    ['TOOLS', '静态分析'], ['D2', '保护核验'], ['REPORT', '保存报告']];
  const statusLabels = {UNKNOWN: '未知', SUPPORTED: '获支持', REFUTED: '被反证',
    OK: '运行成功', COMPLETED: '已完成', FAILED: '失败', PROCESS_ERROR: '进程错误',
    PARSE_ERROR: '解析错误', TIMEOUT: '超时', SKIPPED: '未执行', RUNNING: '运行中',
    INTERRUPTED: '已中断', PARTIAL: '部分覆盖', COMPLETE: '范围完整',
    REACHABLE: '路径可达', BLOCKED: '路径阻断', NOT_STARTED: '待执行'};
  const textValue = (value, fallback = '—') => value === null || value === undefined || value === '' ? fallback : String(value);
  const list = value => Array.isArray(value) ? value : [];
  const node = (tag, className, value) => {
    const item = document.createElement(tag);
    if (className) item.className = className;
    if (value !== undefined) item.textContent = value;
    return item;
  };
  const selectedStrategy = () => document.querySelector('input[name="ws-strategy"]:checked').value;
  const isSimulation = data => data?.kind === 'SYNTHETIC_DEMO';
  function message(value, kind = '') {
    show('ws-message', value);
    byId('ws-notice').className = 'ws-notice' + (kind ? ` is-${kind}` : '');
  }
  function updateControls() {
    const selected = state.targets.find(row => row.sampleId === byId('ws-sample').value);
    const hasInput = byId('ws-input-mode').value === 'source'
      ? !!byId('ws-source-input').value.trim() && new TextEncoder().encode(byId('ws-source-input').value).length <= 131072
      : !!selected?.runnable;
    const real = byId('ws-mode').value === 'real';
    byId('ws-preview').disabled = state.busy || !state.status.ready || !hasInput || (real && !state.status.realReady);
    byId('ws-run').disabled = state.busy || !state.preview || !state.status.ready ||
      (real && (!state.status.realReady || !byId('ws-consent').checked));
    byId('ws-run').textContent = state.busy ? '处理中…' : real ? '开始真实审计' : '开始审计';
    byId('ws-simulate').disabled = state.busy;
    byId('ws-refresh').disabled = state.busy;
    byId('ws-export').disabled = !state.data || state.busy;
    byId('ws-print').disabled = !state.data || state.busy;
    document.querySelectorAll('.ws-toolbar input, #ws-embedding, .ws-editor input, .ws-editor select, #ws-source-input, #ws-edit-source')
      .forEach(control => { control.disabled = state.busy; });
    byId('ws-sample').disabled = state.busy || !state.targets.length;
  }
  function setBusy(value) { state.busy = value; updateControls(); byId('workspace-panel').setAttribute('aria-busy', String(value)); }
  function invalidate() {
    state.revision++;
    state.preview = null;
    state.data = null;
    byId('ws-consent').checked = false;
    renderEvidence({});
    updateControls();
    message('输入或配置已改变，请重新预览计划与证据。');
  }
  async function refreshStatus() {
    const revision = ++state.statusRevision;
    show('ws-service-text', '正在连接');
    try {
      const data = await request('/api/agent/workspace?embeddingProfile=' + encodeURIComponent(byId('ws-embedding').value));
      if (revision !== state.statusRevision) return;
      state.status = data.status;
      state.targets = list(data.targets);
      const oldValue = byId('ws-sample').value;
      const options = state.targets.map(target => {
        const option = node('option', '', target.sampleId + (target.runnable ? '' : ' · 不可运行'));
        option.value = target.sampleId; option.disabled = !target.runnable; return option;
      });
      byId('ws-sample').replaceChildren(...options);
      if (state.targets.some(row => row.sampleId === oldValue && row.runnable)) byId('ws-sample').value = oldValue;
      else byId('ws-sample').selectedIndex = state.targets.findIndex(row => row.runnable);
      if (!options.length) byId('ws-sample').append(node('option', '', '暂无预置样本，支持粘贴源码'));
      byId('ws-refresh').className = 'ws-service ws-badge' + (data.status.ready ? ' ws-good' : '');
      show('ws-service-text', data.status.ready ? '系统就绪' : '服务待配置');
      show('ws-context', data.status.ready ? `固定快照 ${textValue(data.status.snapshotId).slice(0, 10)} · ${byId('ws-embedding').selectedOptions[0].textContent}` : '本机工作台 · 模拟随时可用');
      show('ws-limits', `模型：${textValue(data.status.model, '尚未配置')}；最多 ${data.status.maxRequests ?? 2} 次请求，每次最多 ${data.status.maxOutputTokens ?? 2048} 输出 token。`);
      if (!state.data && byId('ws-input-mode').value === 'preset') await loadSource();
      if (data.targetError || !data.status.ready) message(data.targetError || '知识服务暂不可用。可查看源码、运行模拟或读取历史。');
    } catch (error) {
      if (revision !== state.statusRevision) return;
      state.status = {};
      show('ws-service-text', '连接失败');
      byId('ws-refresh').className = 'ws-service ws-badge ws-bad';
      message(`${error.message}。点击状态按钮重试。`, 'error');
    } finally { if (revision === state.statusRevision) updateControls(); }
  }
  async function loadSource() {
    const sampleId = byId('ws-sample').value;
    if (!state.targets.some(row => row.sampleId === sampleId && row.runnable)) return;
    const revision = state.revision;
    try {
      const data = await request('/api/agent/workspace/target?sampleId=' + encodeURIComponent(sampleId));
      if (revision !== state.revision) return;
      renderSource(data);
      show('ws-file', sampleId + '.sol');
      show('ws-scope', `${data.target.scope === 'FUNCTION' ? '函数范围' : '完整源码'} · 原始行 ${data.target.lineStart}–${data.target.lineEnd}`);
      show('ws-scope-label', data.target.function || '已登记范围');
    } catch (error) { if (revision === state.revision) message(error.message, 'error'); }
  }
  function choice() {
    const result = {strategy: selectedStrategy(), embeddingProfile: byId('ws-embedding').value, mode: byId('ws-mode').value};
    if (byId('ws-input-mode').value === 'preset') result.sampleId = byId('ws-sample').value;
    else {
      result.source = byId('ws-source-input').value;
      result.mechanism = byId('ws-mechanism').value;
      if (byId('ws-function').value.trim()) result.function = byId('ws-function').value.trim();
      if (byId('ws-risk-line').value) result.riskLine = Number(byId('ws-risk-line').value);
    }
    return result;
  }
  async function previewWorkspace() {
    if (state.busy) return;
    setBusy(true);
    message('正在绑定源码范围与固定知识快照…', 'busy');
    try {
      const data = await request('/api/workbench/preview', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: json(choice())});
      state.preview = data;
      renderDocument(data);
      message(`预览已固定 · ${list(data.retrieval?.d1?.selected).length} 条入选证据 · ${data.plan?.maxRequests ?? 0} 次模型请求上限。`);
    } catch (error) { state.preview = null; message(`${error.message}。修正输入或刷新服务后重试。`, 'error'); }
    finally { setBusy(false); }
  }
  async function simulate() {
    if (state.busy) return;
    setBusy(true); state.revision++; state.preview = null;
    message('正在读取本机合成证据…', 'busy');
    try {
      const data = await request('/api/agent/workspace/simulation?strategy=' + encodeURIComponent(selectedStrategy()));
      useSourceInput(data);
      renderDocument(data);
      message(data.notice);
    } catch (error) { message(error.message, 'error'); }
    finally { setBusy(false); }
  }
  function useSourceInput(data) {
    byId('ws-input-mode').value = 'source';
    byId('ws-source-input').value = data.source?.full || data.target?.fullSource || '';
    byId('ws-source-input').hidden = true;
    byId('ws-sample').hidden = true;
    byId('ws-edit-source').hidden = false;
    byId('ws-byte-count').hidden = false;
    byId('ws-function').value = data.target?.function || '';
    byId('ws-risk-line').value = data.target?.riskLine || '';
    if (data.target?.mechanism) byId('ws-mechanism').value = data.target.mechanism;
    if (isSimulation(data)) byId('ws-mode').value = 'offline';
    byId('ws-consent').checked = false;
    byId('ws-consent-region').hidden = byId('ws-mode').value !== 'real';
    const size = new TextEncoder().encode(byId('ws-source-input').value).length;
    show('ws-byte-count', `${size.toLocaleString('zh-CN')} / 131072 字节`);
    state.sourceKind = 'full'; byId('ws-source-kind').value = 'full';
  }
  async function runWorkspace() {
    if (state.busy || !state.preview || byId('ws-run').disabled) return;
    setBusy(true);
    message('审计已提交，结果将逐阶段保存到本机…', 'busy');
    let runId;
    try {
      const created = await request('/api/workbench/runs', {method: 'POST', headers: {'Content-Type': 'application/json'},
        body: json({...choice(), planHash: state.preview.planHash})});
      runId = created.runId;
      state.preview = null;
      for (let index = 0; index < 900; index++) {
        const data = await request('/api/agent/workspace/runs/' + encodeURIComponent(runId));
        renderDocument(data);
        if (data.status !== 'RUNNING') {
          message(data.status === 'COMPLETED' ? '审计已保存，可定位证据或导出报告。' : `运行${statusLabels[data.status] || data.status}，裁决保持未决。查看工具诊断与报告。`, data.status === 'COMPLETED' ? '' : 'error');
          return;
        }
        await new Promise(resolve => setTimeout(resolve, 1000));
      }
      message(`运行 ${runId.slice(0, 8)} 仍在处理。可从运行历史读取进度。`);
    } catch (error) { message(error.message + (runId ? `。运行 ${runId.slice(0, 8)} 可在历史中继续查看。` : '。请重新预览后再试。'), 'error'); }
    finally { setBusy(false); }
  }
  function highlight(text) {
    const fragment = document.createDocumentFragment();
    const pattern = /(\/\/.*|\/\*.*?\*\/|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|\b(?:pragma|solidity|contract|function|returns|return|external|public|private|internal|view|pure|payable|mapping|address|uint\d*|bool|require|if|else|modifier|event|emit|memory|storage)\b|\b\d+\b)/g;
    let cursor = 0;
    for (const match of text.matchAll(pattern)) {
      fragment.append(document.createTextNode(text.slice(cursor, match.index)));
      const className = match[0].startsWith('//') || match[0].startsWith('/*') ? 'comment'
        : /^["']/.test(match[0]) ? 'string' : /^\d/.test(match[0]) ? 'number' : 'keyword';
      fragment.append(node('span', 'ws-syntax-' + className, match[0]));
      cursor = match.index + match[0].length;
    }
    fragment.append(document.createTextNode(text.slice(cursor)));
    return fragment;
  }
  function renderSource(data) {
    const target = data.target || {};
    const source = data.source || {full: target.fullSource || target.source || '', model: target.modelSource || '', lineStart: 1, modelLineStart: target.lineStart || 1};
    const modelView = state.sourceKind === 'model';
    const text = modelView ? source.model : source.full;
    const start = modelView ? source.modelLineStart : source.lineStart;
    const region = byId('ws-source-view'); region.replaceChildren();
    byId('ws-source-input').hidden = true;
    region.hidden = false;
    byId('ws-source-kind').hidden = !source.model;
    const riskLines = new Set([target.riskLine, ...list(data.model?.hypotheses).map(row => row.riskLine)].filter(Number.isInteger));
    const refs = new Set(list(data.d2?.assessments).flatMap(row => list(row.obligations).flatMap(item => list(item.references).map(ref => ref.line))).filter(Number.isInteger));
    if (!text) {
      region.append(node('div', 'ws-empty', '暂无源码。选择预置样本、粘贴 Solidity，或运行模拟。'));
      return;
    }
    const fragment = document.createDocumentFragment();
    text.split('\n').forEach((value, index) => {
      const line = Number(start || 1) + index;
      const row = node('div', 'ws-source-row'); row.dataset.line = String(line);
      const code = node('code'); code.append(highlight(value || ' '));
      row.append(node('span', 'ws-line-number', line), code);
      if (riskLines.has(line)) { row.classList.add('is-risk'); row.append(node('span', 'ws-line-tag', '风险位置')); }
      else if (refs.has(line)) row.classList.add('is-reference');
      fragment.append(row);
    });
    region.append(fragment);
    show('ws-file', textValue(target.sampleId, target.contract || 'Contract') + '.sol');
    show('ws-scope', `${target.scope === 'FUNCTION' ? '函数范围' : '完整源码'} · 原始行 ${target.lineStart || 1}–${target.lineEnd || text.split('\n').length}`);
  }
  function lineLink(line, label) {
    const button = node('button', 'ws-line-link', label || `第 ${line} 行`); button.type = 'button';
    button.onclick = () => {
      if (!Number.isInteger(line)) return;
      state.sourceKind = 'full'; byId('ws-source-kind').value = 'full';
      renderSource(state.data || state.preview || {});
      const row = byId('ws-source-view').querySelector(`[data-line="${line}"]`);
      if (!row) { message(`第 ${line} 行不在当前源码中，引用尚未绑定。`, 'error'); return; }
      row.classList.add('is-focused');
      row.scrollIntoView({block: 'center', behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth'});
      byId('ws-source-view').focus({preventScroll: true});
    };
    return button;
  }
  function renderRetrieval(data) {
    const d1 = data.retrieval?.d1 || {};
    const selected = list(d1.selected);
    const groups = new Map();
    for (const entry of selected) {
      const candidate = entry.candidate || entry;
      const key = candidate.pairId || candidate.caseId || `未配对-${groups.size}`;
      if (!groups.has(key)) groups.set(key, {key, entries: []});
      groups.get(key).entries.push({candidate, binding: entry.binding || d1.evaluations?.[candidate.chunkId] || {}});
    }
    state.pairs = [...groups.values()];
    const selector = byId('ws-pair');
    selector.replaceChildren(...state.pairs.map((pair, index) => {
      const option = node('option', '', `配对 ${index + 1} · ${pair.key}`); option.value = String(index); return option;
    }));
    selector.hidden = state.pairs.length < 2;
    show('ws-match', selected.length ? `${selected.length} 条证据` : '等待检索');
    const region = byId('ws-candidates'); region.replaceChildren();
    for (const entry of selected) {
      const candidate = entry.candidate || entry;
      const article = node('article');
      article.append(node('strong', '', `${textValue(candidate.caseId)} · ${candidate.role === 'VULNERABLE' ? '漏洞侧' : candidate.role === 'DEFENSE' ? '修复侧' : textValue(candidate.role)}`),
        node('p', '', `来源：${textValue(candidate.provenance, '未提供')}；标签：${candidate.reviewed ? '已登记审核状态' : '待核验'}`),
        node('pre', '', json({binding: entry.binding || d1.evaluations?.[candidate.chunkId], conditions: candidate.conditions})));
      region.append(article);
    }
    if (!selected.length) region.append(node('p', 'ws-caption', '暂无入选案例。'));
    if (list(d1.gaps).length) region.append(node('pre', '', json({gaps: d1.gaps})));
    if (data.retrieval?.pool) region.append(node('pre', '', json({candidatePool: data.retrieval.pool, budget: d1.budget, usedBytes: d1.usedBytes})));
    renderPair();
  }
  function renderPair() {
    const pair = state.pairs[Number(byId('ws-pair').value) || 0];
    const entries = pair?.entries || [];
    const vulnerable = entries.find(row => row.candidate.role === 'VULNERABLE');
    const defense = entries.find(row => row.candidate.role === 'DEFENSE');
    show('ws-vulnerable-code', vulnerable?.candidate.text || '尚无同组漏洞证据。');
    show('ws-defense-code', defense?.candidate.text || '尚无同组修复证据。');
    show('ws-vuln-state', statusLabels[vulnerable?.binding.applicability] || '未绑定');
    show('ws-defense-state', statusLabels[defense?.binding.applicability] || '未绑定');
    show('ws-pair-note', pair ? `配对：${pair.key}。${vulnerable && defense ? '已展示同组两侧；修复侧入选不代表目标保护成立。' : '配对侧缺失，证据仍有缺口。'}` : '预览后展示入选案例与条件绑定，不将检索相似度视为安全证明。');
  }
  function renderTools(data) {
    const region = byId('ws-tool-list'); region.replaceChildren();
    const tools = list(data.tools);
    const failed = tools.some(row => !['OK', 'SKIPPED'].includes(row.status));
    const status = byId('ws-tool-status');
    status.className = 'ws-badge' + (failed ? ' ws-bad' : tools.some(row => row.status === 'OK') ? ' ws-good' : '');
    status.textContent = failed ? '存在失败' : tools.length ? tools.every(row => row.status === 'SKIPPED') ? '未执行' : '已返回' : '尚未运行';
    for (const tool of tools) {
      const detail = node('details'); const summary = node('summary');
      const dot = node('span', 'ws-dot');
      dot.classList.add(tool.status === 'OK' ? 'ws-tool-ok' : 'ws-tool-unknown');
      summary.append(dot, node('span', '', `${textValue(tool.engine)} · ${statusLabels[tool.status] || textValue(tool.status)}`),
        node('span', 'ws-tool-time', tool.durationMs == null ? '—' : `${tool.durationMs} ms`));
      detail.append(summary);
      for (const issue of list(tool.issues)) {
        const item = node('p', '', `${textValue(issue.check || issue.title, '工具告警')} · ${textValue(issue.impact || issue.severity)} `);
        const refs = list(issue.references).concat(list(issue.lines).map(line => ({line})), issue.line ? [{line: issue.line}] : []);
        for (const ref of refs) if (Number.isInteger(ref.line)) item.append(lineLink(ref.line));
        detail.append(item);
      }
      detail.append(node('p', '', tool.status === 'OK' ? `${list(tool.issues).length} 条告警；运行成功不等于安全。` : '此工具没有可用的安全判定。'), node('pre', '', json(tool)));
      region.append(detail);
    }
    if (!tools.length) region.append(node('p', 'ws-muted', '审计后展示工具状态、诊断与定位。'));
  }
  function renderObligations(data) {
    const assessments = list(data.d2?.assessments);
    const count = Math.max(assessments.length, list(data.model?.hypotheses).length);
    const selector = byId('ws-assessment');
    const old = selector.value;
    selector.replaceChildren(...Array.from({length: count}, (_, index) => {
      const row = assessments[index] || {};
      const option = node('option', '', `假设 ${(row.hypothesisIndex ?? index) + 1} · ${statusLabels[row.verdict] || '未知'}`);
      option.value = String(index); return option;
    }));
    if (Number(old) < count) selector.value = old;
    selector.hidden = count < 2;
    renderAssessment(data);
  }
  function renderAssessment(data) {
    const assessment = list(data.d2?.assessments)[Number(byId('ws-assessment').value) || 0] || {};
    const region = byId('ws-obligations'); region.replaceChildren();
    for (const [key, title] of obligations) {
      const obligation = list(assessment.obligations).find(row => row.name === key) || {status: 'UNKNOWN'};
      const card = node('div', 'ws-obligation');
      const badge = node('span', 'ws-badge' + (obligation.status === 'SUPPORTED' ? ' ws-good' : obligation.status === 'REFUTED' ? ' ws-bad' : ''),
        obligation.status === 'SUPPORTED' ? '保护获支持' : obligation.status === 'REFUTED' ? '保护被反证' : '未知');
      card.append(node('h3', '', title), badge);
      card.title = obligation.reason || '尚无充分证据';
      const refs = list(obligation.references).filter(ref => Number.isInteger(ref.line));
      if (refs.length) for (const ref of refs.slice(0, 2)) card.append(lineLink(ref.line));
      else card.append(node('p', '', '无绑定证据'));
      region.append(card);
    }
    show('ws-path', assessment.pathEvidence ? `${statusLabels[assessment.pathEvidence.status] || '路径未知'} · ${textValue(assessment.pathEvidence.reason, '未提供路径说明')}` : '路径尚未核验，缺少证据的义务保持未知。');
    renderHypothesis(data, Number(byId('ws-assessment').value) || 0);
  }
  function meta(region, title, value) {
    const row = node('dl', 'ws-meta'); const content = node('dd');
    content.append(value instanceof Node ? value : document.createTextNode(textValue(value)));
    row.append(node('dt', '', title), content); region.append(row);
  }
  function renderHypothesis(data, index = 0) {
    const region = byId('ws-hypothesis'); region.replaceChildren();
    const hypothesis = list(data.model?.hypotheses)[index];
    const target = data.target || {};
    show('ws-hypothesis-status', hypothesis ? `${list(data.model.hypotheses).length} 项候选` : '未生成');
    meta(region, '合约', hypothesis?.contract || target.contract || target.sampleId);
    meta(region, '函数', hypothesis?.function || target.function);
    const line = hypothesis?.riskLine || target.riskLine;
    meta(region, '风险位置', Number.isInteger(line) ? lineLink(line) : '—');
    meta(region, '审计范围', target.scope === 'FUNCTION' ? '指定函数' : target.scope ? '完整源码' : '等待输入');
    meta(region, 'D2 裁决', {SUPPORTED: '漏洞假设获支持', REFUTED: '漏洞假设被反驳', UNKNOWN: '未知'}[data.d2?.verdict] || '未知');
    const reason = hypothesis?.reason || (data.model?.rejectedHypotheses?.length ? '部分模型假设未通过绑定校验，结果保持未决。' : '尚无模型假设。无假设不代表全合约安全。');
    region.append(node('p', 'ws-hypothesis-note', reason));
  }
  function renderVerdict(data) {
    const banner = byId('ws-verdict-banner'); banner.className = 'ws-verdict-banner';
    const conclusion = data.status === 'FAILED' || data.plan?.mode === 'offline' || data.model?.fixture ? 'UNRESOLVED' : data.conclusion;
    const mapping = {VULNERABILITY_SUPPORTED: ['漏洞假设获支持', '可行反例与工具证据支持当前漏洞假设。', 'is-supported'],
      HYPOTHESES_REFUTED: ['当前假设被反驳', '保护证据覆盖当前假设，不推断全合约安全。', 'is-refuted'],
      NO_CONFIRMED_FINDINGS: ['未确认漏洞', '本次没有确认的漏洞，仍需结合覆盖范围审查。', ''],
      UNRESOLVED: ['审计结论未决', '当前证据不足，保留未知。', '']};
    let entry = mapping[conclusion] || ['等待审计', '让每一个结论都有证据。', ''];
    if (isSimulation(data)) entry = ['模拟 · 保持未决', '合成夹具仅展示证据，不构成真实检测结果。', ''];
    else if (data.status === 'RUNNING') entry = ['正在审计', '证据逐阶段保存，请稍候。', ''];
    else if (data.status === 'FAILED' || data.status === 'INTERRUPTED') entry = ['运行未完成', '阶段失败或中断，审计结论保持未决。', ''];
    else if (data.planHash && !data.status) entry = ['计划已就绪', '已固定本次输入、检索证据与请求上限。', ''];
    show('ws-verdict', entry[0]); show('ws-verdict-note', entry[1]); if (entry[2]) banner.classList.add(entry[2]);
  }
  function renderTelemetry(data) {
    const telemetry = data.telemetry || {};
    const duration = telemetry.durationMs;
    show('ws-tokens', telemetry.totalTokens == null ? '—' : Number(telemetry.totalTokens).toLocaleString('zh-CN'));
    show('ws-latency', duration == null ? '—' : duration < 1000 ? `${duration}ms` : `${(duration / 1000).toFixed(1)}s`);
    show('ws-cost', telemetry.cost == null ? '—' : String(telemetry.cost));
    show('ws-run-kind', isSimulation(data) ? '合成模拟' : data.plan?.mode === 'real' ? '真实运行' : data.status ? '离线演练' : '未运行');
    show('ws-usage-note', `输入 ${textValue(telemetry.inputTokens)} / 输出 ${textValue(telemetry.outputTokens)} token。${telemetry.totalTokens == null ? '缺失用量保留 null；费用未提供。' : '费用以返回记录为准。'}`);
    const region = byId('ws-stages'); region.replaceChildren();
    const recorded = new Map(list(data.stages).map(stage => [stage.name, stage]));
    const events = list(data.events);
    for (const [key, title] of stages) {
      const record = recorded.get(key) || [...events].reverse().find(event => event.kind === key + '_RESULT')?.value;
      const started = events.some(event => event.kind === key + '_STARTED');
      const label = record?.status ? statusLabels[record.status] || record.status : isSimulation(data) ? key === 'D1' || key === 'FACTS' ? '已存夹具' : '未执行' : started ? '运行中' : '待执行';
      const phase = record?.status === 'FAILED' ? 'failed' : record ? 'done' : started ? 'active' : '';
      const row = node('li', phase ? 'is-' + phase : '');
      row.append(node('span', 'ws-dot'), node('span', '', title), node('span', '', label));
      region.append(row);
    }
  }
  function renderEvidence(data) {
    renderRetrieval(data); renderTools(data); renderObligations(data); renderVerdict(data); renderTelemetry(data);
    const facts = data.retrieval?.facts || {};
    const types = [...new Set(list(facts.facts).map(fact => fact.kind))];
    const names = {CALL: '外部调用', WRITE: '状态写入', CHECK: '权限检查', READ: '状态读取', LOCK: '互斥保护'};
    byId('ws-facts').replaceChildren(...(types.length ? types.slice(0, 4).map(type => node('span', 'ws-chip', names[type] || type)) : [node('span', 'ws-chip', '等待预览')]));
    if (facts.status) byId('ws-facts').append(node('span', 'ws-chip', statusLabels[facts.status] || facts.status));
    show('ws-raw', Object.keys(data).length ? json(data) : '尚无审计记录。');
  }
  function renderDocument(data) {
    state.data = data;
    if (data.target) renderSource(data);
    show('ws-scope-label', data.target?.function || '访问控制 / 重入');
    byId('ws-stage-details').open = data.status === 'RUNNING';
    renderEvidence(data);
    updateControls();
  }
  async function loadWorkspaceHistory() {
    const region = byId('ws-history-list'); region.replaceChildren(node('p', 'ws-muted', '正在读取本机报告…'));
    try {
      const data = await request('/api/agent/workspace/runs');
      region.replaceChildren();
      for (const item of list(data.runs)) {
        const button = node('button', 'ws-history-row'); button.type = 'button';
        const title = node('div');
        title.append(node('strong', '', textValue(item.sampleId, item.runId.slice(0, 8))),
          node('span', 'ws-caption', `${textValue(item.strategy, '未登记')} · ${item.mode === 'real' ? '真实运行' : item.mode === 'offline' ? '离线演练' : '模式未登记'} · ${textValue(item.createdAt)}`));
        button.append(title, node('span', 'ws-badge', statusLabels[item.status] || textValue(item.status)));
        button.onclick = async () => {
          if (state.busy) { message('当前审计仍在处理，完成后可回放历史。'); return; }
          setBusy(true); state.revision++;
          try {
            const record = await request('/api/agent/workspace/runs/' + encodeURIComponent(item.runId));
            state.preview = null;
            useSourceInput(record);
            renderDocument(record); switchPanel('workspace');
            message(`已读取 ${item.runId.slice(0, 8)} · ${record.plan?.parseReplay || record.plan?.toolReplay ? '派生记录' : '原始记录'} · 零新增模型请求。`);
          } catch (error) { message(error.message, 'error'); }
          finally { setBusy(false); }
        };
        region.append(button);
      }
      if (!list(data.runs).length) region.append(node('div', 'ws-empty', '暂无保存记录。完成一次审计后，可在此回放并导出。'));
    } catch (error) { region.replaceChildren(node('p', 'ws-muted', error.message + '。点击刷新历史重试。')); }
  }
  function switchPanel(name) {
    for (const key of ['workspace', 'batch', 'history']) {
      byId(key + '-tab').setAttribute('aria-selected', String(key === name));
      byId(key + '-tab').tabIndex = key === name ? 0 : -1;
      byId(key + '-panel').hidden = key !== name;
    }
    if (name === 'batch' && !state.batchLoaded) { state.batchLoaded = true; load(); }
    if (name === 'history') loadWorkspaceHistory();
    byId('ws-print').disabled = name !== 'workspace' || !state.data || state.busy;
  }
  for (const name of ['workspace', 'batch', 'history']) byId(name + '-tab').onclick = () => switchPanel(name);
  document.querySelector('.ws-tabs').onkeydown = event => {
    const tabs = ['workspace', 'batch', 'history'];
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
    const index = tabs.findIndex(name => byId(name + '-tab') === document.activeElement);
    const next = event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 : (index + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length;
    event.preventDefault(); switchPanel(tabs[next]); byId(tabs[next] + '-tab').focus();
  };
  byId('ws-input-mode').onchange = () => {
    invalidate();
    const paste = byId('ws-input-mode').value === 'source';
    byId('ws-sample').hidden = paste; byId('ws-byte-count').hidden = !paste; byId('ws-edit-source').hidden = !paste;
    byId('ws-source-input').hidden = !paste; byId('ws-source-view').hidden = paste; byId('ws-source-kind').hidden = true;
    if (paste) { byId('ws-source-input').focus(); show('ws-file', 'Contract.sol'); }
    else loadSource();
  };
  byId('ws-sample').onchange = () => { invalidate(); loadSource(); };
  byId('ws-source-input').oninput = () => {
    invalidate();
    const size = new TextEncoder().encode(byId('ws-source-input').value).length;
    show('ws-byte-count', `${size.toLocaleString('zh-CN')} / 131072 字节`);
    if (size > 131072) message('源码超过 128 KiB，请缩小输入范围。', 'error');
  };
  byId('ws-edit-source').onclick = () => { invalidate(); byId('ws-source-view').hidden = true; byId('ws-source-input').hidden = false; byId('ws-source-input').focus(); };
  byId('ws-source-kind').onchange = () => { state.sourceKind = byId('ws-source-kind').value; if (state.data) renderSource(state.data); };
  document.querySelectorAll('input[name="ws-strategy"]').forEach(input => { input.onchange = invalidate; });
  for (const id of ['ws-mechanism', 'ws-function', 'ws-risk-line']) byId(id).oninput = invalidate;
  byId('ws-embedding').onchange = () => { invalidate(); refreshStatus(); };
  byId('ws-mode').onchange = () => { invalidate(); byId('ws-consent-region').hidden = byId('ws-mode').value !== 'real'; };
  byId('ws-consent').onchange = updateControls;
  byId('ws-refresh').onclick = () => { invalidate(); refreshStatus(); };
  byId('ws-preview').onclick = previewWorkspace;
  byId('ws-simulate').onclick = simulate;
  byId('ws-run').onclick = runWorkspace;
  byId('ws-pair').onchange = renderPair;
  byId('ws-assessment').onchange = () => renderAssessment(state.data || {});
  byId('ws-history-refresh').onclick = loadWorkspaceHistory;
  byId('ws-export').onclick = () => {
    if (!state.data) return;
    const blob = new Blob([json(state.data) + '\n'], {type: 'application/json;charset=utf-8'});
    const url = URL.createObjectURL(blob);
    const link = node('a'); link.href = url; link.download = `VeriRAG-${state.data.runId || (isSimulation(state.data) ? 'synthetic-demo' : 'preview')}.json`;
    document.body.append(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    message('完整 JSON 已导出，包含源码、证据、裁决与缺失用量。');
  };
  byId('ws-print').onclick = () => { if (state.data) window.print(); };
  renderEvidence({});
  refreshStatus();
})();
