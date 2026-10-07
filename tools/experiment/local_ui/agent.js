const byId = id => document.getElementById(id);
let targets = [];
let status = null;
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
    show('provider', state.realReady ? `真实运行：${state.endpoint} · ${state.model}` : '真实模型配置未就绪；仍可查看历史与目标。');
    byId('real').disabled = !state.ready || !state.realReady;
    byId('offline').disabled = !state.ready;
    await loadHistory();
  } catch (error) { show('notice', error.message); }
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
byId('offline').onclick = () => run('offline');
byId('real').onclick = () => run('real');
load();
