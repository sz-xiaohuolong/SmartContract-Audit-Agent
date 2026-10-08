const byId = id => document.getElementById(id);
let targets = [];
let status = null;
let batchPlan = null;
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
    show('knowledge-status', state.ready ? `本次实验使用正式知识 ${state.formalVectors ?? '待核对'} 条向量。${pending ? `另有 ${pending.vectors} 条待审向量（AutoMESC ${pending.automescPairs} 组改动、FORGE ${pending.forgeVfp} 条审计资料），仅供在 Attu 查看，不进入 D1 实验。` : '待审语料未就绪或未入库。'}` : '正式知识快照暂不可用。');
    show('provider', state.realReady ? `真实运行：${state.endpoint} · ${state.model}` : '真实模型配置未就绪；仍可查看历史与目标。');
    byId('real').disabled = !state.ready || !state.realReady;
    byId('offline').disabled = !state.ready;
    renderBatchChoices();
    await loadBatchHistory();
    await loadHistory();
  } catch (error) { show('notice', error.message); }
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
load();
