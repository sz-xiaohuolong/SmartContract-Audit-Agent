const $ = id => document.getElementById(id);
const show = value => value === null || value === undefined ? '未返回' : String(value);
const request = async (path, options) => {
  const response = await fetch(path, options);
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || '本机服务返回错误');
  return body;
};
function renderResult(report) {
  const plan = report.plan;
  const result = report.result;
  const container = $('result');
  container.replaceChildren();
  const title = document.createElement('h3');
  title.textContent = `${report.status === 'COMPLETED' ? '模型已返回' : '运行失败／未决'} · ${plan.sampleId}`;
  container.append(title);
  for (const [label, value] of [
    ['模型结论', show(result.conclusion)], ['漏洞类型', show(result.vulnerabilityType)],
    ['理由', show(result.reason)], ['错误类别', show(result.errorCategory)],
    ['输入 token', show(result.inputTokens)], ['输出 token', show(result.outputTokens)],
    ['入选知识片段', report.selectedEvidence.join('、')], ['运行编号', plan.runId],
    ['结果目录', `.local/mvp-runs/${plan.runId}/`]
  ]) {
    const row = document.createElement('p');
    row.textContent = `${label}：${value}`;
    container.append(row);
  }
}
async function refreshHistory() {
  const body = await request('/api/mvp/runs');
  const container = $('history');
  container.replaceChildren();
  if (!body.runs.length) {
    const empty = document.createElement('p'); empty.className = 'empty'; empty.textContent = '尚无运行记录'; container.append(empty);
    return;
  }
  for (const row of body.runs) {
    const button = document.createElement('button');
    button.className = 'history-row'; button.type = 'button';
    button.textContent = `${row.sampleId} · ${row.status} · ${row.runId}`;
    button.addEventListener('click', async () => {
      try { renderResult(await request(`/api/mvp/runs/${row.runId}`)); }
      catch (error) { $('runMessage').textContent = error.message; }
    });
    container.append(button);
  }
}
async function initialize() {
  try {
    const status = await request('/api/mvp/status');
    $('connection').textContent = status.ready ? '本机知识快照已校验' : '知识快照尚未就绪';
    $('snapshotState').textContent = status.ready ? '已就绪' : '未就绪';
    $('snapshotId').textContent = status.ready ? status.snapshot.snapshotId.slice(0, 18) + '…' : '先建立本机快照';
    $('documentCount').textContent = status.ready ? status.snapshot.documentCount : '—';
    $('runMvp').disabled = !status.ready;
    $('runMessage').textContent = status.ready ? '已就绪；点击后会产生一次真实模型请求。' : '请先运行知识快照构建命令。';
    await refreshHistory();
  } catch (error) { $('connection').textContent = '本机服务不可用'; $('runMessage').textContent = error.message; }
}
$('runMvp').addEventListener('click', async () => {
  $('runMvp').disabled = true;
  $('runMessage').textContent = '正在运行，最多等待 90 秒；请勿刷新页面或重复点击。';
  try {
    const report = await request('/api/mvp/run', {method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'});
    renderResult(report);
    $('runMessage').textContent = report.status === 'COMPLETED' ? '结果已保存，可在下方回看。' : '运行未决；结果已保存，不会自动重试。';
    await refreshHistory();
  } catch (error) { $('runMessage').textContent = error.message; }
  finally { $('runMvp').disabled = false; }
});
initialize();
