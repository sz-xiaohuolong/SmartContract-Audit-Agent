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
  for (const title of ['策略', 'TP', 'FP', 'FN', 'TN', 'Precision', 'Recall', 'F1', '类别命中@K', '平均输入 token', '平均输出 token', '平均耗时 ms', '失败/未知']) {
    const cell = document.createElement('th'); cell.textContent = title; head.append(cell);
  }
  table.append(head);
  for (const [strategy, row] of Object.entries(report.metrics)) {
    const tr = document.createElement('tr');
    for (const value of [strategy, row.tp, row.fp, row.fn, row.tn, metric(row.precision), metric(row.recall), metric(row.f1),
      metric(row.retrievalHitAtK), metric(row.avgInputTokens), metric(row.avgOutputTokens), metric(row.avgDurationMs), `${row.failed}/${row.unknown}`]) {
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
  for (const title of ['目标', '策略', '数据集标签', '状态', '模型结论', '错误类别', '耗时 ms']) {
    const cell = document.createElement('th'); cell.textContent = title; progressHead.append(cell);
  }
  progress.append(progressHead);
  const resultIndex = new Map(report.samples.map(item => [`${item.sampleId}|${item.strategy}`, item]));
  for (const sampleId of report.plan.sampleIds) for (const strategy of report.plan.strategies) {
    const row = resultIndex.get(`${sampleId}|${strategy}`);
    const tr = document.createElement('tr');
    const label = report.plan.labels[sampleId].hasVulnerability ? '漏洞' : '安全对照';
    for (const value of [sampleId, strategy, label, row?.status || '待处理', row?.prediction || '—',
      row?.errorCategory || '—', metric(row?.durationMs, '—')]) {
      const cell = document.createElement('td'); cell.textContent = String(value); tr.append(cell);
    }
    progress.append(tr);
  }
  progressWrap.append(progress); region.append(progressWrap);
  const note = document.createElement('p'); note.className = 'agent-muted';
  note.textContent = 'TP/FP/FN/TN 以数据集标签和结构化模型的“报告／未报告”为口径；未报告不等于证明安全。类别命中@K 仅按漏洞类型匹配，是检索代理指标；离线空假设及错误项保持未知。';
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
    tools: data.tools, d2: data.d2, denominators: data.denominators,
    sourceHash: data.plan.sourceHash, snapshotId: data.plan.snapshotId}));
  const link = byId('report');
  link.href = '/api/agent/runs/' + data.runId + '/report';
  link.hidden = false;
}
async function run(mode) {
  const target = targets.find(item => item.sampleId === byId('sample').value);
  if (!target || !target.runnable) return;
  if (mode === 'real') {
    const choice = window.confirm(`确认运行 ${target.sampleId}（${target.scope === 'FUNCTION' ? '函数级' : '整份源码'}）？\n策略：${byId('strategy').value}\n端点：${status.endpoint}\n模型：${status.model}\n最多 1 次请求，输出上限 2048 token，零重试。`);
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
load();
