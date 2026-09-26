const names = {
  DENSE: ['向量召回', '传统检索'], HYBRID: ['混合检索', '向量与词法'],
  CONTRASTIVE: ['普通正反例', '直接配对'], FIELD_FILTER: ['简单条件过滤', '强基线'],
  D1: ['D1 条件对比', '目标绑定与互补选择'],
  D1_NO_BINDING: ['D1 去掉目标绑定', '消融对照'],
  D1_NO_COMPLEMENT: ['D1 去掉互补选择', '消融对照']
};
const order = ['DENSE', 'HYBRID', 'CONTRASTIVE', 'FIELD_FILTER', 'D1', 'D1_NO_BINDING', 'D1_NO_COMPLEMENT'];
const $ = id => document.getElementById(id);
let context;
let record;
let selected = 'D1';

function node(tag, className, content) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (content !== undefined) element.textContent = content;
  return element;
}

async function getJson(path, options) {
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || '本地服务请求失败');
  return data;
}

function ratio(value) { return value === null || value === undefined ? '待审' : `${(value * 100).toFixed(1)}%`; }
function compact(value) { return value ? `${value.slice(0, 8)}…` : '未知'; }
function sample() { return record?.result?.samples?.[0]; }

function renderSummary() {
  const data = record.result;
  $('sampleCount').textContent = String(data.denominators.planned);
  $('strategyCount').textContent = String(Object.keys(sample()?.strategies || {}).length);
  $('tokenBudget').textContent = String(data.tokenProfile.maxTokens);
  $('eligibleCount').textContent = String(data.denominators.researchEligible);
  $('poolId').textContent = `候选池 ${compact(sample()?.poolHash)}`;
  $('runLabel').textContent = record.createdAt ? `本机运行 ${new Date(record.createdAt).toLocaleString('zh-CN')}` : '仓库内演示结果';
  const link = $('reportLink');
  link.hidden = !record.report;
  link.href = record.report ? `/api/runs/${record.runId}/report` : '#';
  $('reportPath').textContent = record.report ? `报告目录：${record.report.directory}` : '';
}

function renderComparison() {
  const body = $('strategyRows');
  body.replaceChildren();
  const strategies = sample()?.strategies || {};
  for (const key of order) {
    const rowData = strategies[key];
    if (!rowData) continue;
    const row = node('tr', key === selected ? 'is-selected' : '');
    row.tabIndex = 0;
    row.setAttribute('aria-label', `查看${names[key][0]}的案例证据`);
    const label = node('td', 'strategy-name', names[key][0]);
    label.append(node('small', '', names[key][1]));
    row.append(label);
    const rank = node('td', 'rank');
    rowData.selected.forEach((caseId, index) => {
      if (index) rank.append(node('span', 'rank-sep', '→'));
      rank.append(node('span', '', caseId === 'defense' ? '防御案例' : '漏洞案例'));
    });
    row.append(rank);
    row.append(node('td', '', ratio(rowData.metrics.recallAtK)));
    row.append(node('td', '', ratio(rowData.metrics.ndcgAtK)));
    const complement = node('td');
    complement.append(node('span', `pill ${rowData.metrics.complementCoverage ? 'primary-pill' : ''}`, rowData.metrics.complementCoverage ? '已覆盖' : '未覆盖'));
    row.append(complement);
    row.append(node('td', '', `${rowData.promptTokens} / ${rowData.budgetTokens}`));
    row.addEventListener('click', () => { selected = key; renderComparison(); renderEvidence(); });
    row.addEventListener('keydown', event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); row.click(); } });
    body.append(row);
  }
}

function renderEvidence() {
  $('targetSource').textContent = context.target.source;
  $('targetQuestion').textContent = context.target.question;
  const strategy = sample()?.strategies?.[selected];
  $('selectedDescription').textContent = `${names[selected][0]}：按入选顺序展示条件判断与人工样例标签。`;
  const list = $('selectedCases');
  list.replaceChildren();
  if (!strategy || !strategy.selected.length) { list.append(node('p', 'empty', '该策略没有选中案例。')); return; }
  strategy.selected.forEach((caseId, index) => {
    const item = context.cases[caseId];
    const judgment = context.judgments[caseId];
    const card = node('article', 'case-card');
    const head = node('div', 'case-top');
    head.append(node('strong', '', `${index + 1}. ${item.role === 'DEFENSE' ? '防御案例' : '漏洞案例'}`));
    head.append(node('span', '', item.binding.applicability === 'SUPPORTED' ? '条件支持' : item.binding.applicability === 'CONTRADICTED' ? '条件反证' : '条件待确认'));
    card.append(head);
    card.append(node('p', '', `案例 ${caseId}，合成标签适用性 ${judgment.applicability}/3；仅供机制演示。`));
    card.append(node('code', '', item.text));
    for (const condition of item.binding.conditions) {
      card.append(node('p', 'condition', `${condition.condition.predicate}：${condition.reason}（${condition.state}）`));
    }
    card.append(node('span', 'label', `来源：${judgment.reviewer}。该标签不具备研究效力。`));
    list.append(card);
  });
}

function show(next) {
  record = next;
  if (!sample()) throw new Error('结果中没有可展示的样本');
  renderSummary(); renderComparison(); renderEvidence();
}

async function refreshHistory() {
  const data = await getJson('/api/runs');
  const list = $('historyList');
  list.replaceChildren();
  if (!data.runs.length) { list.append(node('p', 'empty', '本机还没有新的运行记录。点击上方按钮运行固定的离线样例。')); return; }
  for (const run of data.runs) {
    const button = node('button', 'history-row');
    button.type = 'button';
    button.append(node('strong', '', `合成样例 ${compact(run.runId)}`));
    button.append(node('small', '', new Date(run.createdAt).toLocaleString('zh-CN')));
    button.addEventListener('click', async () => {
      try { show(await getJson(`/api/runs/${run.runId}`)); $('comparison').scrollIntoView({behavior: 'smooth'}); }
      catch (error) { $('runStatus').textContent = error.message; }
    });
    list.append(button);
  }
}

async function run() {
  const button = $('runButton');
  button.disabled = true;
  $('runStatus').textContent = '正在运行固定的离线样例…';
  try {
    show(await getJson('/api/runs', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: '{}'}));
    await refreshHistory();
    $('runStatus').textContent = '已完成，结果保存在本机。';
  } catch (error) { $('runStatus').textContent = error.message; }
  finally { button.disabled = false; }
}

async function init() {
  try {
    const [details, demo] = await Promise.all([getJson('/api/context'), getJson('/api/demo')]);
    context = details;
    show(demo);
    await refreshHistory();
    $('connection').textContent = '本地服务已连接';
    $('runStatus').textContent = '可随时重新运行固定样例';
    $('runButton').disabled = false;
  } catch (error) {
    $('connection').textContent = '本地服务不可用';
    $('runStatus').textContent = error.message;
  }
}

$('runButton').addEventListener('click', run);
$('demoButton').addEventListener('click', async () => { try { show(await getJson('/api/demo')); } catch (error) { $('runStatus').textContent = error.message; } });
init();
