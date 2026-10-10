(() => {
  'use strict';

  const API = '/api/workbench';
  const SOURCE_LIMIT = 128 * 1024;
  const MODEL_LIMIT = 16 * 1024;
  const CONTEXT_LIMIT = 4096;
  const encoder = new TextEncoder();
  const byId = id => document.getElementById(id);
  const list = value => Array.isArray(value) ? value : [];
  const object = value => value && typeof value === 'object' && !Array.isArray(value) ? value : {};
  const asText = (value, fallback = '未提供') => value == null ? fallback : typeof value === 'string' ? value : JSON.stringify(value, null, 2);
  const bytes = value => encoder.encode(typeof value === 'string' ? value : '').length;
  const state = {
    inputKind: 'preset', status: null, targets: [], revision: 0, preview: null,
    previewAbort: null, previewBusy: false, postBusy: false, activeRunId: null,
    viewEpoch: 0, readAbort: null, pollTimer: null, viewedRunId: null, displayed: null,
    statusEpoch: 0, historyEpoch: 0, marks: {}, lineCount: 0, fullLines: new Map(), modelLines: new Map()
  };
  const LABELS = {
    OK: '正常', COMPLETED: '完成', RUNNING: '运行中', STARTED: '已开始', PENDING: '等待',
    FAILED: '失败', ERROR: '错误', INTERRUPTED: '已中断', SKIPPED: '已跳过',
    UNKNOWN: '未知', UNRESOLVED: '未决', SUPPORTED: '证据支持', REFUTED: '已反证',
    CONTRADICTED: '条件矛盾', PROCESS_ERROR: '执行失败', TIMEOUT: '超时',
    NOT_INSTALLED: '工具不可用', TOOL_UNAVAILABLE: '工具不可用', PARSE_ERROR: '解析失败',
    MODEL_CALL_ERROR: '模型调用失败', MODEL_PARSE_ERROR: '模型解析失败',
    NO_RISK_FACT: '无唯一风险事实', PARTIAL: '信息不完整', COMPLETE: '受限完整',
    REENTRANCY: '重入', ACCESS_CONTROL: '访问控制',
    WRITES_BEFORE_CALLS: '已识别写入先于调用', WRITE_AFTER_CALL: '已识别调用后写入',
    SUPPORT: '支持参考', CONTRAST: '对比参考', SOFT_SUPPORT: '软配对参考', SOFT_CONTRAST: '软配对对比',
    VULNERABLE: '漏洞侧', DEFENSE: '修复侧', FIXED: '修复侧', REFERENCE: '参考',
    HIGH: '高', MEDIUM: '中', LOW: '低', INFORMATIONAL: '信息', OPTIMIZATION: '优化'
  };
  const STAGES = [
    ['FACTS', '程序事实'], ['D1', '检索对比'], ['MODEL', '模型假设'],
    ['TOOLS', '工具验证'], ['D2', '保护核验'], ['REPORT', '报告保存']
  ];
  const OBLIGATIONS = [
    ['actor', '调用者身份'], ['resource', '受保护资源'], ['pre_risk_guard', '风险前守卫'],
    ['entry_coverage', '入口覆盖'], ['state_version', '状态版本'], ['bypass', '绕过路径']
  ];
  const label = value => LABELS[asText(value, '').toUpperCase()] || asText(value, '未知');
  const tone = value => {
    const code = asText(value, '').toUpperCase();
    if (['FAILED', 'ERROR', 'PROCESS_ERROR', 'TIMEOUT', 'PARSE_ERROR'].includes(code)) return 'bad';
    if (['UNKNOWN', 'UNRESOLVED', 'INTERRUPTED', 'PARTIAL', 'NO_RISK_FACT'].includes(code)) return 'warn';
    if (['RUNNING', 'STARTED'].includes(code)) return 'active';
    if (['OK', 'COMPLETED', 'SUPPORTED'].includes(code)) return 'good';
    return 'neutral';
  };

  // 所有远端内容只作为文本节点呈现，包括源码、模型输出与诊断信息。
  function el(tag, className, value) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (value !== undefined) node.textContent = asText(value, '');
    return node;
  }
  function badge(value, textValue) { return el('span', `badge ${tone(value)}`, textValue || label(value)); }
  function empty(region, message) { region.replaceChildren(el('p', 'empty-state', message)); }
  function message(value, isError = false) {
    byId('action-message').textContent = value;
    byId('action-message').classList.toggle('error', isError);
  }
  function details(title, value) {
    const node = el('details');
    node.append(el('summary', '', title), el('pre', 'raw-view', value));
    return node;
  }
  function receipt(region, rows) {
    region.replaceChildren();
    for (const [name, value] of rows) region.append(el('dt', '', name), el('dd', '', asText(value)));
  }
  function summary(title, description, kind = 'neutral') {
    const region = byId('result-summary');
    region.dataset.tone = kind;
    region.replaceChildren(el('strong', '', title), el('p', '', description));
  }
  function setReport(runId, available) {
    const link = byId('report-link');
    link.hidden = !available;
    if (available) link.href = `${API}/runs/${encodeURIComponent(runId)}/report`;
    else link.removeAttribute('href');
  }

  async function request(path, options = {}, timeoutMs = 30000) {
    const controller = new AbortController();
    const external = options.signal;
    const abort = () => controller.abort();
    if (external?.aborted) controller.abort();
    else external?.addEventListener('abort', abort, {once: true});
    const timer = setTimeout(abort, timeoutMs);
    try {
      const response = await fetch(path, {...options, signal: controller.signal, credentials: 'same-origin', cache: 'no-store'});
      const body = await response.json().catch(() => null);
      if (!response.ok) {
        const error = new Error(asText(body?.error || body?.message, `请求失败（HTTP ${response.status}），请刷新状态后重试。`));
        error.httpStatus = response.status;
        throw error;
      }
      if (!body || typeof body !== 'object') throw new Error('接口未返回有效 JSON，请核对服务是否已就绪。');
      return body;
    } catch (error) {
      if (controller.signal.aborted && !external?.aborted) throw new Error('请求等待超时，请从历史核对记录；页面不会自动重发审计。');
      throw error;
    } finally {
      clearTimeout(timer);
      external?.removeEventListener('abort', abort);
    }
  }
  const post = (path, payload, signal) => request(path, {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload), signal
  }, 90000);

  function initTabs(ids, onSelect) {
    const tabs = ids.map(byId);
    function select(tab) {
      for (const item of tabs) {
        const selected = item === tab;
        item.setAttribute('aria-selected', String(selected));
        item.tabIndex = selected ? 0 : -1;
        byId(item.getAttribute('aria-controls')).hidden = !selected;
      }
      if (onSelect) onSelect(tab.id);
    }
    tabs.forEach((tab, index) => {
      tab.addEventListener('click', () => select(tab));
      tab.addEventListener('keydown', event => {
        let next;
        if (event.key === 'ArrowRight') next = (index + 1) % tabs.length;
        if (event.key === 'ArrowLeft') next = (index + tabs.length - 1) % tabs.length;
        if (event.key === 'Home') next = 0;
        if (event.key === 'End') next = tabs.length - 1;
        if (next == null) return;
        event.preventDefault();
        tabs[next].focus();
        select(tabs[next]);
      });
    });
    return id => select(byId(id));
  }

  function selectedTarget() {
    const value = byId('sample-select').value;
    return value === '' ? null : state.targets[Number(value)] || null;
  }
  function inputValid() {
    if (state.inputKind === 'preset') return !!selectedTarget()?.runnable;
    return byId('source-input').value.trim().length > 0 && bytes(byId('source-input').value) <= SOURCE_LIMIT
      && byId('risk-line').validity.valid;
  }
  function updateActions() {
    const ready = state.status?.ready === true;
    const isReal = byId('mode-select').value === 'real';
    const busy = state.previewBusy || state.postBusy;
    byId('preview-button').disabled = !ready || !inputValid() || busy || !!state.activeRunId || (isReal && !state.status?.realReady);
    byId('preview-button').textContent = state.previewBusy ? '正在预览…' : '预览审计计划';
    byId('run-button').disabled = !ready || !state.preview || busy || !!state.activeRunId
      || (isReal && (!state.status?.realReady || !byId('real-consent').checked));
    byId('run-button').textContent = state.postBusy ? '正在创建运行…' : isReal ? '开始真实审计' : '开始离线演练';
    byId('real-consent-region').hidden = !isReal;
    byId('mode-note').textContent = isReal ? '预览不调用审计模型；核对计划和模型后，明确勾选并点击开始才发起真实审计。'
      : '离线演练验证审计链路；固定假设不代表真实检测结论，结论仍保留未决。';
    const maxRequests = state.preview?.data.plan?.maxRequests ?? state.status?.maxRequests ?? 2;
    const maxOutput = state.preview?.data.plan?.maxOutputTokens ?? state.status?.maxOutputTokens ?? 2048;
    const provider = state.preview?.data.plan?.provider;
    byId('real-limits').textContent = `真实调用会发送本次审计输入，可能计费。每次输出最多 ${maxOutput} token，最多 ${maxRequests} 次请求。`
      + (provider ? ` 已选模型：${asText(provider.model)}；端点：${asText(provider.endpoint)}。` : ' 预览后查看本次模型与端点。');
  }
  function invalidatePreview(note = '输入或模式已改变，请重新预览。') {
    state.revision += 1;
    state.preview = null;
    state.previewAbort?.abort();
    state.previewAbort = null;
    state.previewBusy = false;
    byId('real-consent').checked = false;
    byId('plan-state').textContent = note;
    updateActions();
    if (state.displayed?.kind === 'preview') {
      state.displayed = null;
      summary('预览已失效', '输入、模式或知识模型已改变。重新预览后才能使用对应计划启动审计。', 'warn');
      clearEvidence();
    }
  }
  function originKey(target) {
    // 优先使用服务端来源；兼容尚未显式提供来源的正式与 benchmark 登记。
    const origin = target.origin ?? target.sourceKind ?? target.dataset ?? target.inputKind;
    if (typeof origin === 'string' && origin) return origin;
    if (typeof target.source === 'string' && !target.source.includes('\n') && target.source.length < 100) return target.source;
    return target.benchmark || target.datasetSource || target.vulnerableLines ? 'benchmarks' : 'formal';
  }
  function originLabel(key) {
    return {formal: '正式目标', FORMAL: '正式目标', PRESET: '正式目标', benchmarks: '公开数据集 · benchmarks',
      BENCHMARK: '公开数据集 · benchmarks', benchmark: '公开数据集 · benchmarks'}[key] || key;
  }
  function populateTargets() {
    const region = byId('sample-select');
    const previous = region.value;
    const origin = byId('target-origin').value;
    region.replaceChildren();
    state.targets.forEach((target, index) => {
      if (origin !== 'all' && originKey(target) !== origin) return;
      const option = el('option', '', `${asText(target.sampleId)} · ${asText(target.function, '未指定函数')}${target.runnable ? '' : ' · 暂不可运行'}`);
      option.value = String(index);
      // 不可运行的样本仍可选中，以查看其原因，但不能预览或执行。
      region.append(option);
    });
    if (!region.options.length) {
      const option = el('option', '', '当前来源暂无目标'); option.value = ''; region.append(option);
      region.disabled = true;
    } else {
      region.disabled = false;
      if ([...region.options].some(option => option.value === previous)) region.value = previous;
      else region.value = ([...region.options].find(option => state.targets[Number(option.value)]?.runnable) || region.options[0]).value;
    }
    updateTargetFields();
  }
  function updateTargetFields() {
    const preset = state.inputKind === 'preset';
    byId('source-input').disabled = preset;
    for (const id of ['mechanism-select', 'function-input', 'risk-line']) byId(id).disabled = preset;
    if (preset) {
      const target = selectedTarget();
      if (['REENTRANCY', 'ACCESS_CONTROL'].includes(target?.mechanism)) byId('mechanism-select').value = target.mechanism;
      byId('function-input').value = target?.function || '';
      byId('risk-line').value = target?.riskLine || list(target?.vulnerableLines)[0] || '';
      byId('sample-note').textContent = target ? `${originLabel(originKey(target))} · ${label(target.mechanism)} · ${target.scope === 'FUNCTION' ? '函数范围' : '完整源码'}。${target.runnable ? '可运行。' : '暂不可运行。'} ${asText(target.reason, '')}` : '当前没有登记目标，可切换至粘贴源码。';
    }
    updateActions();
  }
  async function loadTargets() {
    try {
      const data = await request(`${API}/targets`);
      if (!Array.isArray(data.targets)) throw new Error('目标列表格式无效。');
      state.targets = data.targets.filter(target => typeof target?.sampleId === 'string');
      const origin = byId('target-origin');
      origin.replaceChildren();
      const all = el('option', '', '全部来源'); all.value = 'all'; origin.append(all);
      for (const key of new Set(state.targets.map(originKey))) {
        const option = el('option', '', originLabel(key)); option.value = key; origin.append(option);
      }
      origin.disabled = false;
      populateTargets();
    } catch (error) {
      byId('sample-note').textContent = `预置目标读取失败：${error.message} 可粘贴源码或刷新页面重试。`;
    }
  }
  async function loadStatus() {
    const epoch = ++state.statusEpoch;
    const profile = byId('embedding-select').value;
    byId('refresh-status').disabled = true;
    try {
      const data = await request(`${API}/status?embeddingProfile=${encodeURIComponent(profile)}`);
      if (epoch !== state.statusEpoch || profile !== byId('embedding-select').value) return;
      const previous = state.status;
      state.status = data;
      if (state.preview && (data.ready !== true || previous?.snapshotId !== data.snapshotId
          || (byId('mode-select').value === 'real' && !data.realReady))) invalidatePreview('快照或真实模型状态已改变，请重新预览。');
      const service = byId('service-state');
      service.textContent = data.ready ? '知识就绪' : '知识未就绪';
      service.className = `badge ${data.ready ? 'good' : 'warn'}`;
      byId('snapshot-state').textContent = data.ready ? `快照 ${asText(data.snapshotId)} · ${profile === 'nomic' ? 'Nomic' : 'BGE'} ${asText(data.dimension, '维度待确认')} 维` : asText(data.reason, '知识暂不可用，仍可读取历史报告。');
      byId('real-state').textContent = data.realReady ? `真实调用已配置${data.model ? ` · ${data.model}` : ''}` : '真实调用未就绪';
    } catch (error) {
      if (epoch !== state.statusEpoch) return;
      state.status = null;
      invalidatePreview('状态读取失败，刷新状态后重新预览。');
      byId('service-state').textContent = '连接失败';
      byId('service-state').className = 'badge warn';
      byId('snapshot-state').textContent = error.message;
      byId('real-state').textContent = '真实调用状态待确认';
    } finally {
      if (epoch === state.statusEpoch) { byId('refresh-status').disabled = false; updateActions(); }
    }
  }
  function payload() {
    const choice = {strategy: byId('strategy-select').value, embeddingProfile: byId('embedding-select').value, mode: byId('mode-select').value};
    if (state.inputKind === 'preset') {
      const target = selectedTarget();
      if (!target?.runnable) throw new Error('请选择可运行的预置样本。');
      return {sampleId: target.sampleId, ...choice};
    }
    const source = byId('source-input').value;
    if (!source.trim()) throw new Error('请粘贴完整 Solidity 源码。');
    if (bytes(source) > SOURCE_LIMIT) throw new Error('粘贴源码超过 128 KiB，请缩小输入。');
    const data = {source, mechanism: byId('mechanism-select').value, ...choice};
    const functionName = byId('function-input').value.trim();
    if (functionName) data.function = functionName;
    if (byId('risk-line').value !== '') {
      const riskLine = Number(byId('risk-line').value);
      if (!Number.isSafeInteger(riskLine) || riskLine < 1 || riskLine > source.split('\n').length) throw new Error('风险行须为完整源码范围内的正整数。');
      data.riskLine = riskLine;
    }
    return data;
  }

  function stopReading() {
    state.viewEpoch += 1;
    clearTimeout(state.pollTimer);
    state.pollTimer = null;
    state.readAbort?.abort();
    state.readAbort = null;
  }
  function clearEvidence() {
    for (const [id, text] of [
      ['retrieval-panel', '重新预览后查看本次检索证据。'], ['hypotheses-panel', '运行后展示模型提出的假设。'],
      ['tools-panel', '运行后展示工具状态与告警。'], ['d2-panel', '运行后展示六项保护义务的核验结果。'],
      ['source-full', '预览后展示完整源码。'], ['source-model', '预览后展示模型使用的源码片段。']
    ]) empty(byId(id), text);
    state.fullLines.clear(); state.modelLines.clear(); state.lineCount = 0;
    state.marks = {risk: new Set(), hypothesis: new Set(), tool: new Set(), d2: new Set()};
    byId('source-scope').textContent = '完整源码等待预览';
    byId('source-message').textContent = '';
    byId('source-receipt').replaceChildren();
    byId('result-meta').replaceChildren();
    byId('event-details').hidden = true;
    byId('syntax-summary').textContent = '结构解析采用受限 SolidityStructure，不承诺完整编译 AST、类型解析或路径证明。';
    empty(byId('syntax-content'), '预览后查看解析到的合约与函数。');
    renderStages({});
    setReport('', false);
  }
  async function preview(event) {
    event?.preventDefault();
    if (byId('preview-button').disabled) return;
    invalidatePreview('正在绑定当前输入与知识快照…');
    stopReading();
    state.viewedRunId = null;
    const revision = state.revision;
    const controller = new AbortController();
    state.previewAbort = controller;
    state.previewBusy = true;
    updateActions();
    message('正在预览源码范围与案例，不调用审计模型。');
    try {
      const choice = payload();
      const data = await post(`${API}/preview`, choice, controller.signal);
      if (revision !== state.revision) return;
      if (typeof data.planHash !== 'string' || !data.planHash || !data.target || !data.retrieval) throw new Error('预览缺少计划摘要或审计证据，请重新预览。');
      if (data.plan?.mode && data.plan.mode !== choice.mode) throw new Error('返回计划的模式与输入不一致，请重新预览。');
      const source = data.target.source ?? data.target.fullSource;
      if (typeof source !== 'string' || !source.trim()) throw new Error('预览未返回完整源码，不能启动审计。');
      const context = data.retrieval.d1?.context;
      if (bytes(context) > CONTEXT_LIMIT || bytes(data.target.modelSource) > MODEL_LIMIT) throw new Error('预览超过上下文或模型片段上限，不能启动审计。');
      state.preview = {data, choice, revision};
      state.displayed = {kind: 'preview', data};
      renderData(data);
      summary('审计计划已预览', '核对源码范围、检索案例与解析限制；本次尚未调用审计模型。');
      renderStages({});
      byId('plan-state').textContent = `计划已绑定${choice.mode === 'real' ? '真实' : '离线'}模式；修改任何输入须重新预览。`;
      message(choice.mode === 'real' ? '请核对已选模型与端点，勾选真实调用后点击开始。' : '预览已就绪，可以开始离线演练。');
    } catch (error) {
      if (revision !== state.revision || controller.signal.aborted) return;
      message(`预览失败：${error.message}`, true);
      byId('plan-state').textContent = '未形成有效计划，请修正输入后重新预览。';
    } finally {
      if (revision === state.revision) { state.previewBusy = false; state.previewAbort = null; updateActions(); }
    }
  }

  function makeLines(region, source, start, registry) {
    region.replaceChildren(); registry.clear();
    if (typeof source !== 'string') { empty(region, '未返回源码文本。'); return; }
    const code = el('code', 'source-code');
    const fragment = document.createDocumentFragment();
    source.replace(/\r\n?/g, '\n').split('\n').forEach((text, index) => {
      const line = start + index;
      const row = el('span', 'source-line'); row.dataset.line = String(line); row.tabIndex = -1;
      const number = el('span', 'line-number', line); number.setAttribute('aria-hidden', 'true');
      row.append(number, el('span', 'line-text', text || ' '));
      registry.set(line, row); fragment.append(row);
    });
    code.append(fragment); region.append(code);
  }
  function collectLines(reference, seen = new Set()) {
    if (reference == null) return seen;
    if (typeof reference === 'number' && Number.isSafeInteger(reference) && reference > 0) seen.add(reference);
    else if (typeof reference === 'string') {
      const match = reference.match(/^(?:L|行\s*)?(\d+)(?:\s*[-–:]\s*(?:L)?(\d+))?$/i);
      if (match) {
        const start = Number(match[1]), end = Number(match[2] || start);
        for (let at = start; at <= Math.min(end, state.lineCount); at++) seen.add(at);
      }
    } else if (Array.isArray(reference)) reference.forEach(row => collectLines(row, seen));
    else if (typeof reference === 'object') {
      for (const key of ['line', 'lines', 'riskLine', 'vulnerableLines', 'source_mapping', 'sourceMapping', 'location', 'locations', 'references', 'elements']) collectLines(reference[key], seen);
      const start = reference.lineStart ?? reference.startLine;
      const end = reference.lineEnd ?? reference.endLine ?? start;
      if (Number.isSafeInteger(start) && Number.isSafeInteger(end)) {
        for (let at = Math.max(1, start); at <= Math.min(end, state.lineCount); at++) seen.add(at);
      }
      if (reference.engine && Number.isInteger(reference.issueIndex)) {
        const tool = list(state.displayed?.data.tools).find(row => row.engine === reference.engine);
        const issue = list(tool?.issues)[reference.issueIndex];
        if (issue && issue !== reference) collectLines(issue, seen);
      }
    }
    return seen;
  }
  function targetLines(reference) {
    const target = state.displayed?.data.target;
    if (reference && typeof reference === 'object' && reference.sourceHash
        && reference.sourceHash !== (target?.fullSourceHash ?? target?.sourceHash)) return [];
    return [...collectLines(reference)].filter(line => line <= state.lineCount).sort((a, b) => a - b);
  }
  function mark(reference, kind) {
    if (!state.marks[kind]) return;
    for (const line of targetLines(reference)) state.marks[kind].add(line);
  }
  function paintMarks() {
    for (const registry of [state.fullLines, state.modelLines]) {
      for (const [line, row] of registry) {
        const names = [];
        for (const [kind, title] of [['risk', '风险行'], ['hypothesis', '模型假设'], ['tool', '工具告警'], ['d2', 'D2 引用']]) {
          const marked = state.marks[kind].has(line);
          row.classList.toggle(`mark-${kind}`, marked);
          if (marked) names.push(title);
        }
        row.title = `原始行 ${line}${names.length ? ` · ${names.join('、')}` : ''}`;
      }
    }
  }
  function locate(lines, kind = 'd2') {
    selectSourceTab('source-full-tab');
    const found = lines.filter(line => state.fullLines.has(line));
    if (!found.length) { byId('source-message').textContent = '这条证据没有可定位到完整源码的行号。'; return; }
    for (const row of state.fullLines.values()) row.classList.remove('is-focused');
    for (const line of found) {
      state.fullLines.get(line).classList.add('is-focused');
      if (state.marks[kind]) state.marks[kind].add(line);
    }
    paintMarks();
    const row = state.fullLines.get(found[0]);
    row.scrollIntoView({block: 'center', inline: 'nearest', behavior: 'auto'});
    row.focus({preventScroll: true});
    byId('source-message').textContent = `已定位原始源码：第 ${found.join('、')} 行。`;
  }
  function references(parent, value, kind, prefix = '') {
    const refs = Array.isArray(value) ? value : value == null ? [] : [value];
    if (!refs.length) return;
    const region = el('div', 'references');
    for (const ref of refs) {
      const lines = targetLines(ref);
      if (!lines.length) {
        region.append(el('span', 'help', `${prefix}引用未提供可定位行号${ref?.engine ? ` · ${ref.engine}` : ''}`));
        continue;
      }
      const short = lines.length > 5 ? `${lines[0]}–${lines[lines.length - 1]}` : lines.join('、');
      const button = el('button', 'reference-button', `${prefix}${ref?.engine ? `${ref.engine} · ` : ''}原始行 ${short}`);
      button.type = 'button';
      button.addEventListener('click', () => locate(lines, kind));
      region.append(button); mark(ref, kind);
    }
    parent.append(region);
  }
  function renderSource(data) {
    const target = data.target || {};
    const source = target.source ?? target.fullSource;
    state.marks = {risk: new Set(), hypothesis: new Set(), tool: new Set(), d2: new Set()};
    state.lineCount = typeof source === 'string' ? source.replace(/\r\n?/g, '\n').split('\n').length : 0;
    makeLines(byId('source-full'), source, 1, state.fullLines);
    const full = typeof source === 'string' ? source.replace(/\r\n?/g, '\n') : '';
    const model = typeof target.modelSource === 'string' ? target.modelSource.replace(/\r\n?/g, '\n') : null;
    let modelStart = null;
    if (model != null) {
      const expected = Number.isSafeInteger(target.lineStart) ? target.lineStart : 1;
      const slice = full.split('\n').slice(expected - 1, expected - 1 + model.split('\n').length).join('\n');
      if (slice === model) modelStart = expected;
      else {
        const position = full.indexOf(model);
        if (position >= 0 && (position === 0 || full[position - 1] === '\n')) modelStart = full.slice(0, position).split('\n').length;
      }
    }
    makeLines(byId('source-model'), model, modelStart ?? 1, state.modelLines);
    if (modelStart == null) state.modelLines.clear();
    byId('source-line-note').textContent = modelStart != null ? '两种视图均使用原始源码行号' : '模型片段使用局部行号；引用定位完整源码';
    byId('source-scope').textContent = `${target.scope === 'FUNCTION' ? '模型使用函数范围' : '模型使用完整范围'} · 原始行 ${asText(target.lineStart)}–${asText(target.lineEnd)} · ${asText(target.function, '函数待确认')}`;
    mark({lines: target.vulnerableLines, line: target.riskLine}, 'risk');
    receipt(byId('source-receipt'), [
      ['目标编号', target.sampleId], ['审计方向', label(target.mechanism)], ['模型范围', target.scope],
      ['完整源码字节', bytes(source)], ['模型片段字节', bytes(target.modelSource)],
      ['完整源码摘要', target.fullSourceHash ?? target.sourceHash], ['模型片段摘要', target.modelSourceHash],
      ['计划摘要', data.planHash], ['快照', data.retrieval?.snapshotId ?? data.plan?.snapshotId]
    ]);
    const syntax = object(target.syntax);
    const region = byId('syntax-content'); region.replaceChildren();
    const limitations = list(syntax.limitations);
    byId('syntax-summary').textContent = `受限结构解析${syntax.status ? ` · ${label(syntax.status)}` : ''}。`
      + (limitations.length ? limitations.map(value => asText(value)).join('；') : '未提供完整编译 AST、类型解析或路径证明。');
    for (const contract of list(syntax.contracts)) {
      const section = el('div', 'finding');
      section.append(el('h3', '', asText(contract.name, '未命名合约')));
      for (const fn of list(contract.functions)) {
        const row = el('div', 'fact-row');
        row.append(el('strong', '', asText(fn.name)), el('span', '', `外部调用 ${list(fn.externalCalls).length} · 状态写入 ${list(fn.stateWrites).length} · ${label(fn.cei)}`), badge(fn.complete ? 'COMPLETED' : 'PARTIAL', fn.complete ? '受限解析完整' : '受限解析不完整'));
        references(row, {lineStart: fn.lineStart, lineEnd: fn.lineEnd}, 'focus');
        section.append(row, details('查看调用与写入结构', {externalCalls: fn.externalCalls, stateWrites: fn.stateWrites, cei: fn.cei}));
      }
      region.append(section);
    }
    if (!region.childElementCount) empty(region, '服务端未返回可定位的函数结构，解析能力与限制保持未知。');
  }

  function renderRetrieval(data) {
    const view = object(data.retrieval), d1 = object(view.d1), plan = object(data.plan);
    const region = byId('retrieval-panel'); region.replaceChildren();
    const candidates = Array.isArray(view.pool) ? view.pool : list(view.pool?.candidates);
    const selected = list(d1.selected);
    const selectedById = new Map(selected.map(row => [row.candidate?.chunkId, row]));
    const measured = bytes(d1.context);
    const budget = el('div', 'budget-row');
    budget.append(el('strong', '', `${plan.strategy || view.strategy || 'D1'} · ${label(d1.status)}`),
      el('span', '', `${selected.length} 条入选 / ${candidates.length} 条候选`),
      badge(measured > CONTEXT_LIMIT ? 'FAILED' : 'OK', `上下文 ${measured} / ${plan.maxContextBytes ?? CONTEXT_LIMIT} 字节`));
    region.append(budget, el('p', 'evidence-note', '4096 字节为 UTF-8 上下文预算。案例标签来自自动标注，待核验；修复侧入选不代表目标的保护已获证明。'));
    if (list(d1.gaps).length) {
      const gaps = el('ul', 'gap-list');
      for (const gap of d1.gaps) gaps.append(el('li', '', asText(gap)));
      region.append(gaps);
    }
    const groups = new Map();
    for (const row of selected) {
      const candidate = object(row.candidate);
      const key = candidate.pairId || candidate.caseId || candidate.chunkId || '未标识案例';
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push({candidate, selection: row});
    }
    // 同组未入选的另一侧作为对照展示，明确标识其未进入上下文。
    for (const [key, rows] of groups) {
      for (const candidate of candidates) {
        if ((candidate.pairId || candidate.caseId || candidate.chunkId) === key
            && !rows.some(row => row.candidate.chunkId === candidate.chunkId)) rows.push({candidate, selection: null});
      }
    }
    const pairs = el('div', 'pair-list');
    for (const [key, rows] of groups) {
      const section = el('article', 'pair-block');
      const header = el('div', 'pair-heading');
      header.append(el('h3', '', key), badge('UNKNOWN', '自动标注 · 待核验'));
      const grid = el('div', 'pair-grid');
      for (const [side, title] of [['vulnerable', '漏洞侧 · vulnerable'], ['fixed', '修复侧 · fixed']]) {
        const column = el('div', 'pair-side'); column.append(el('h4', '', title));
        const matches = rows.filter(row => side === 'vulnerable' ? row.candidate.role === 'VULNERABLE' : ['FIXED', 'DEFENSE'].includes(row.candidate.role));
        for (const row of matches) column.append(renderCandidate(row.candidate, row.selection, d1.evaluations));
        if (!matches.length) column.append(el('p', 'empty-state', '当前候选池未返回这一侧。'));
        grid.append(column);
      }
      section.append(header, grid);
      for (const row of rows.filter(row => !['VULNERABLE', 'FIXED', 'DEFENSE'].includes(row.candidate.role))) section.append(renderCandidate(row.candidate, row.selection, d1.evaluations));
      pairs.append(section);
    }
    if (groups.size) region.append(pairs);
    else region.append(el('p', 'empty-state', '没有入选案例。保留检索缺口与未知状态，不能据此推断无漏洞。'));
    const poolDetails = el('details'); poolDetails.append(el('summary', '', `查看候选池（${candidates.length} 条）`));
    for (const candidate of candidates) poolDetails.append(renderCandidate(candidate, selectedById.get(candidate.chunkId), d1.evaluations));
    region.append(poolDetails, details('实际检索上下文', asText(d1.context, '未提供上下文')), details('条件评估与绑定原始记录', d1.evaluations ?? {}));
    const factsDetails = el('details'); factsDetails.append(el('summary', '', '程序事实与解析限制'));
    const factRows = Array.isArray(view.facts) ? view.facts : list(view.facts?.facts);
    const facts = el('div', 'fact-list');
    for (const fact of factRows) {
      const row = el('div', 'fact-row');
      row.append(el('span', '', `${asText(fact.kind)} · ${asText(fact.resource, '')} · ${asText(fact.scope, '')}`));
      references(row, {line: fact.line}, 'focus'); facts.append(row);
    }
    factsDetails.append(facts, el('pre', 'raw-view', view.facts));
    region.append(factsDetails, details('检索快照与预算摘要', {
      snapshotId: view.snapshotId, collection: view.collection, poolHash: view.poolHash ?? plan.poolHash,
      embedding: data.embedding ?? plan.embedding, contextBytes: plan.contextBytes, measuredContextBytes: measured,
      maxContextBytes: plan.maxContextBytes ?? CONTEXT_LIMIT, researchEligible: false
    }));
  }
  function renderCandidate(candidate, selection, evaluations) {
    const node = el('div', 'candidate');
    const head = el('div', 'candidate-head');
    const score = typeof candidate.denseScore === 'number' && Number.isFinite(candidate.denseScore) ? candidate.denseScore.toFixed(4) : '未提供';
    head.append(el('strong', '', asText(candidate.chunkId, '案例片段')), badge(selection ? 'COMPLETED' : 'PENDING', selection ? '已入选' : '未入选'),
      el('span', '', `向量分数 ${score} · ${label(candidate.mechanism)}`));
    node.append(head, el('pre', '', asText(candidate.text, '未提供案例文本')));
    const condition = el('div', 'candidate-condition');
    condition.append(el('strong', '', '适用条件：'), el('span', '', candidate.conditions == null || (Array.isArray(candidate.conditions) && !candidate.conditions.length) ? '未提供，适用性待核验' : asText(candidate.conditions)));
    const evaluation = Array.isArray(evaluations) ? evaluations.find(row => row.chunkId === candidate.chunkId) : object(evaluations)[candidate.chunkId];
    const binding = selection?.binding ?? evaluation;
    node.append(condition, el('p', 'candidate-condition', `用途：${selection ? label(selection.use) : '仅展示同池候选'}；条件绑定：${label(binding?.applicability ?? 'UNKNOWN')}`));
    if (binding != null) node.append(details('查看条件绑定', binding));
    return node;
  }
  function field(parent, name, value) {
    if (value == null || value === '') return;
    const row = el('p', 'field-text'); row.append(el('strong', '', `${name}：`), el('span', '', asText(value))); parent.append(row);
  }
  function renderHypotheses(data) {
    const region = byId('hypotheses-panel'); region.replaceChildren();
    const model = object(data.model);
    if (!data.model) { empty(region, '运行后展示模型提出的假设；预览不会调用审计模型。'); return; }
    const meta = el('div', 'tool-meta');
    meta.append(badge(model.status), el('span', '', `输入 token：${asText(model.inputTokens, '未返回（null）')}`),
      el('span', '', `输出 token：${asText(model.outputTokens, '未返回（null）')}`));
    if (model.fixture || data.plan?.mode === 'offline') meta.append(badge('UNKNOWN', '离线固定假设 · 非检测结论'));
    region.append(meta);
    if (model.errorCategory) region.append(el('p', 'tool-error', `模型状态异常：${asText(model.errorCategory)}。已返回的假设仍保留，结论保持未决。`));
    const hypotheses = list(model.hypotheses);
    const cards = el('div', 'finding-list');
    hypotheses.forEach((hypothesis, index) => {
      const row = object(hypothesis), node = el('article', 'finding');
      const heading = el('div', 'finding-heading');
      heading.append(el('h3', '', `假设 ${index + 1} · ${asText(row.title ?? row.mechanism ?? row.vulnerabilityType, label(data.target?.mechanism))}`), badge('UNKNOWN', '待证据核验'));
      node.append(heading);
      if (typeof hypothesis === 'string') node.append(el('p', 'finding-body', hypothesis));
      for (const [name, value] of [
        ['假设内容', row.claim ?? row.description ?? row.reason ?? row.vulnerabilityReason],
        ['合约 / 函数', [row.contract, row.function].filter(Boolean).join('.')], ['案例引用', row.evidenceIds],
        ['攻击者', row.actor], ['资源', row.resource], ['前提条件', row.preconditions ?? row.conditions],
        ['风险操作', row.riskOperation], ['攻击路径', row.attackPath], ['保护', row.protection], ['置信度', row.confidence]
      ]) field(node, name, value);
      references(node, {riskLine: row.riskLine, references: row.references, lines: row.lines}, 'hypothesis');
      node.append(details('查看完整假设', hypothesis)); cards.append(node);
    });
    region.append(cards);
    if (!hypotheses.length) region.append(el('p', 'empty-state', model.status === 'COMPLETED' ? '模型没有返回假设；空假设不能作为安全证明。' : '没有可用的模型假设；调用或解析失败保持未决。'));
    if (list(model.rejectedHypotheses).length) region.append(details('未通过结构校验的假设', model.rejectedHypotheses));
    region.append(details('模型返回状态与用量', model));
  }
  function renderTools(data) {
    const region = byId('tools-panel'); region.replaceChildren();
    if (!data.tools) { empty(region, '运行后展示工具状态、耗时与告警。'); return; }
    region.append(el('p', 'evidence-note', '工具失败、超时、跳过或没有告警，均不能证明合约安全。'));
    for (const tool of list(data.tools)) {
      const node = el('article', 'finding');
      const heading = el('div', 'finding-heading');
      heading.append(el('h3', '', asText(tool.engine, '未标识工具')), badge(tool.status));
      const meta = el('div', 'tool-meta');
      meta.append(el('span', '', `版本：${asText(tool.version)}`), el('span', '', `耗时：${tool.durationMs == null ? '未返回' : `${tool.durationMs} ms`}`), el('span', '', `告警：${list(tool.issues).length}`));
      node.append(heading, meta);
      if (!['OK', 'COMPLETED'].includes(tool.status)) field(node, '状态说明', tool.reason ?? tool.errorCategory ?? tool.error ?? '本工具未产生可用于完整判定的结果。');
      list(tool.issues).forEach((issue, index) => {
        const card = el('div', 'issue');
        card.append(el('h4', '', `${index + 1}. ${asText(issue.check ?? issue.title ?? issue.name, '工具告警')}`));
        field(card, '级别', label(issue.impact ?? issue.severity ?? 'UNKNOWN'));
        field(card, '说明', issue.description ?? issue.message ?? issue.reason);
        references(card, issue, 'tool'); card.append(details('查看完整告警', issue)); node.append(card);
      });
      if (!list(tool.issues).length) node.append(el('p', 'help', tool.status === 'OK' ? '本次工具没有返回告警。' : '没有可用告警记录。'));
      node.append(details('工具记录', tool)); region.append(node);
    }
    if (!list(data.tools).length) empty(region, '工具结果缺失，判断保持未决。');
  }
  function protectionLabel(status) {
    return {SUPPORTED: '保护获支持', REFUTED: '保护被反证', UNKNOWN: '保护未知'}[status] || label(status);
  }
  function vulnerabilityLabel(status) {
    return {SUPPORTED: '漏洞假设获支持', REFUTED: '漏洞假设被反驳', UNKNOWN: '漏洞假设未知'}[status] || label(status);
  }
  function renderD2(data) {
    const region = byId('d2-panel'); region.replaceChildren();
    const d2 = object(data.d2);
    if (!data.d2) { empty(region, '运行后展示 D2 六项核验；缺少绑定证据时保持未知。'); return; }
    const header = el('div', 'finding-heading');
    header.append(el('h3', '', 'D2 汇总'), badge(d2.verdict, vulnerabilityLabel(d2.verdict)));
    region.append(header, el('p', 'evidence-note', '六项表格评估保护义务；保护被反证与漏洞假设被反驳具有不同含义。未知项显示证据缺口，不能推断安全。'));
    let assessments = list(d2.assessments);
    if (!assessments.length) {
      region.append(el('p', 'help', '暂无逐假设核验记录。以下展示尚未获得证据的六项保护义务。'));
      assessments = [{verdict: 'UNKNOWN', protectionVerdict: 'UNKNOWN', obligations: []}];
    }
    for (const assessment of assessments) {
      const section = el('article', 'assessment');
      const heading = el('div', 'finding-heading');
      heading.append(el('h3', '', Number.isInteger(assessment.hypothesisIndex) ? `假设 ${assessment.hypothesisIndex + 1}` : '未绑定假设'),
        badge(assessment.verdict, vulnerabilityLabel(assessment.verdict)), badge(assessment.protectionVerdict, protectionLabel(assessment.protectionVerdict)));
      section.append(heading);
      const scroll = el('div', 'table-scroll'), table = el('table'), head = el('thead'), body = el('tbody');
      const headRow = el('tr');
      for (const title of ['保护义务', '状态', '绑定证据', '原因 / 未知说明']) { const th = el('th', '', title); th.scope = 'col'; headRow.append(th); }
      head.append(headRow);
      for (const [key, title] of OBLIGATIONS) {
        const obligation = list(assessment.obligations).find(row => row.name === key) || {status: 'UNKNOWN'};
        const row = el('tr'), status = el('td'), evidence = el('td');
        status.append(badge(obligation.status));
        references(evidence, obligation.references, 'd2');
        if (!evidence.childElementCount) evidence.append(el('span', 'help', '无绑定证据'));
        row.append(el('td', '', title), status, evidence, el('td', '', asText(obligation.reason,
          obligation.status === 'UNKNOWN' || !obligation.status ? '尚无与完整源码绑定的充分证据；此项保持未知。' : '返回结果未提供判定原因，需结合证据核验。')));
        body.append(row);
      }
      table.append(head, body); scroll.append(table); section.append(scroll);
      references(section, assessment.references, 'd2');
      field(section, '路径证据', assessment.pathEvidence?.reason);
      references(section, assessment.pathEvidence?.references, 'd2');
      field(section, '说明', assessment.note);
      section.append(details('完整 D2 核验记录', assessment)); region.append(section);
    }
  }

  function renderStages(data) {
    const recorded = new Map(list(data.stages).map(stage => [stage.name, stage]));
    for (const event of list(data.events)) {
      const match = asText(event.kind, '').match(/^(FACTS|D1|MODEL|TOOLS|D2|REPORT)_(STARTED|RESULT|COMPLETED|FAILED)$/);
      if (!match) continue;
      const value = object(event.value);
      recorded.set(match[1], {name: match[1], status: value.status || {STARTED: 'RUNNING', RESULT: 'UNKNOWN', COMPLETED: 'COMPLETED', FAILED: 'FAILED'}[match[2]], durationMs: value.durationMs, reason: value.reason});
    }
    const region = byId('stage-list'); region.replaceChildren();
    STAGES.forEach(([name, title], index) => {
      const stage = recorded.get(name);
      const status = stage?.status || (data.status === 'INTERRUPTED' ? 'INTERRUPTED' : ['FAILED', 'COMPLETED'].includes(data.status) ? 'UNKNOWN' : 'PENDING');
      const node = el('li'); node.dataset.tone = tone(status);
      node.append(el('span', 'stage-number', String(index + 1).padStart(2, '0')), el('span', 'stage-name', title),
        el('span', 'stage-status', `${label(status)}${stage?.durationMs != null ? ` · ${stage.durationMs} ms` : ''}`));
      if (stage?.reason) node.title = asText(stage.reason);
      region.append(node);
    });
    const events = list(data.events);
    byId('event-details').hidden = !events.length;
    byId('event-list').replaceChildren();
    for (const event of events) {
      const row = el('div', 'event-row');
      row.append(el('time', '', formatTime(event.at)), el('span', '', `${asText(event.kind)} · ${asText(event.value, '')}`));
      byId('event-list').append(row);
    }
  }
  function renderMeta(data) {
    const plan = object(data.plan), target = object(data.target);
    const region = byId('result-meta'); region.replaceChildren();
    const embedding = object(data.embedding ?? plan.embedding);
    for (const value of [
      target.sampleId ?? plan.sampleId, label(target.mechanism), plan.strategy,
      plan.mode === 'real' ? '真实审计' : plan.mode === 'offline' ? '离线演练' : null,
      embedding.dimension ? `${plan.embeddingProfile === 'bge' ? 'BGE' : 'Nomic'} ${embedding.dimension} 维` : null,
      data.runId ? `记录 ${data.runId}` : null
    ]) if (value) region.append(el('span', '', value));
  }
  function renderData(data) {
    if (data.target) renderSource(data);
    if (data.retrieval) renderRetrieval(data);
    renderMeta(data);
    renderHypotheses(data); renderTools(data); renderD2(data); renderStages(data); paintMarks();
    setReport(data.runId, !!data.runId && ['COMPLETED', 'FAILED'].includes(data.status) && !!data.conclusion);
  }
  function renderResult(data) {
    const previous = state.displayed?.data;
    // 封口时接口可能只返回状态与事件，仍保留同一运行已读取的源码及证据。
    if (previous?.runId === data.runId) data = {...previous, ...data,
      target: data.target ?? previous.target, retrieval: data.retrieval ?? previous.retrieval, plan: data.plan ?? previous.plan};
    state.displayed = {kind: 'run', data};
    renderData(data);
    if (data.status === 'RUNNING') summary('审计进行中', '阶段状态随记录更新；当前页面只轮询读取，不追加模型请求。');
    else if (data.status === 'INTERRUPTED') summary('运行已中断 · 未决', '运行中断或服务重启后尚未形成完整报告。仅保留已有记录，不自动续发模型请求。', 'warn');
    else {
      const conclusions = {
        VULNERABILITY_SUPPORTED: ['有证据支持漏洞', '结合模型假设、工具告警和 D2 引用核对受影响的函数与路径。', 'bad'],
        HYPOTHESES_REFUTED: ['本次假设已被反驳', '此结论只针对已核验的假设，不能外推为完整合约安全。', 'neutral'],
        NO_CONFIRMED_FINDINGS: ['未确认漏洞', '本次未形成已确认发现；没有发现不等于合约安全。', 'neutral'],
        UNRESOLVED: ['审计未决', '证据、保护义务或执行状态尚不充分，请核对未知原因和阶段记录。', 'warn']
      };
      if (data.plan?.mode === 'offline' || data.model?.fixture) summary('离线演练 · 未决', '固定假设用于检查审计链路，不构成真实检测结论。可查看各阶段和报告记录。', 'warn');
      else if (data.status === 'FAILED' || data.model?.status === 'FAILED') summary('运行失败 · 未决', '已返回的模型假设和证据仍保留。执行失败不能解释为安全，请查看失败阶段与未知原因。', 'warn');
      else summary(...(conclusions[data.conclusion] || ['结论未提供 · 未决', '结果缺少有效结论，判断保持未知。', 'warn']));
    }
  }
  function readRecovery(runId, error) {
    message(`运行记录读取失败：${error.message}。请重新读取或从报告历史打开；不会重发审计。`, true);
    const button = el('button', 'button secondary small', '重新读取此运行'); button.type = 'button';
    button.addEventListener('click', () => watchRun(runId));
    byId('result-summary').append(button);
  }
  async function watchRun(runId) {
    stopReading();
    const epoch = state.viewEpoch;
    state.viewedRunId = runId;
    let reads = 0;
    async function readNext() {
      if (epoch !== state.viewEpoch) return;
      const controller = new AbortController(); state.readAbort = controller;
      try {
        const data = await request(`${API}/runs/${encodeURIComponent(runId)}`, {signal: controller.signal});
        if (epoch !== state.viewEpoch) return;
        if (data.runId !== runId) throw new Error('返回的运行编号不一致，停止显示此记录。');
        renderResult(data);
        document.querySelectorAll('.history-row').forEach(row => row.setAttribute('aria-current', String(row.dataset.runId === runId)));
        if (data.status === 'RUNNING') {
          reads += 1;
          if (reads < 400) state.pollTimer = setTimeout(readNext, 1500);
          else readRecovery(runId, new Error('页面读取等待已结束，运行状态仍待确认'));
        } else {
          if (state.activeRunId === runId) state.activeRunId = null;
          updateActions();
          message(data.status === 'INTERRUPTED' ? '运行已中断，仅查看保存记录，不自动续发。' : '已读取运行记录，可查看证据或下载完整报告。');
          await loadHistory();
        }
      } catch (error) {
        if (epoch !== state.viewEpoch || controller.signal.aborted) return;
        readRecovery(runId, error);
      }
    }
    await readNext();
  }
  async function startRun() {
    if (byId('run-button').disabled || !state.preview) return;
    const prepared = state.preview;
    if (prepared.revision !== state.revision || JSON.stringify(payload()) !== JSON.stringify(prepared.choice)) {
      invalidatePreview(); message('当前输入与预览不一致，请重新预览。', true); return;
    }
    const isReal = prepared.choice.mode === 'real';
    if (isReal && (!state.status?.realReady || !byId('real-consent').checked)) return;
    state.postBusy = true; updateActions();
    message(isReal ? '正在创建已确认的真实审计，请勿重复点击。' : '正在创建离线演练。');
    try {
      // 创建请求绝不自动重试；成功后消耗预览，避免重复点击同一计划。
      const created = await post(`${API}/runs`, {...prepared.choice, planHash: prepared.data.planHash});
      if (typeof created.runId !== 'string' || !created.runId) throw new Error('未返回运行编号，请从历史核对是否已创建记录。');
      state.activeRunId = created.runId;
      state.preview = null; byId('real-consent').checked = false;
      byId('plan-state').textContent = '计划已执行；再次审计须重新预览。';
      stopReading(); clearEvidence();
      state.displayed = {kind: 'run', data: {...prepared.data, runId: created.runId}};
      renderData(prepared.data);
      summary('运行已创建', `运行编号 ${created.runId}。正在读取六阶段进度。`);
      await loadHistory();
      await watchRun(created.runId);
    } catch (error) {
      invalidatePreview('创建结果需核对；刷新历史后重新预览。');
      message(`创建审计失败或状态未确认：${error.message} 请先刷新历史核对，页面不会自动重发。`, true);
    } finally { state.postBusy = false; updateActions(); }
  }
  function formatTime(value) {
    if (!value) return '时间未提供';
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? asText(value) : new Intl.DateTimeFormat('zh-CN', {month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false}).format(date);
  }
  async function loadHistory() {
    const epoch = ++state.historyEpoch;
    byId('refresh-history').disabled = true;
    try {
      const data = await request(`${API}/runs`);
      if (epoch !== state.historyEpoch) return;
      if (!Array.isArray(data.runs)) throw new Error('运行历史格式无效。');
      const region = byId('history-list'); region.replaceChildren();
      for (const run of data.runs) {
        if (typeof run.runId !== 'string') continue;
        if (state.activeRunId === run.runId && ['COMPLETED', 'FAILED', 'INTERRUPTED'].includes(run.status)) { state.activeRunId = null; updateActions(); }
        const button = el('button', 'history-row'); button.type = 'button'; button.dataset.runId = run.runId;
        button.setAttribute('aria-current', String(state.viewedRunId === run.runId));
        const title = el('span'); title.append(el('strong', '', asText(run.sampleId, '自定义合约')), el('small', '', run.runId));
        const time = el('time', 'help', formatTime(run.createdAt)); if (run.createdAt) time.dateTime = run.createdAt;
        button.append(title, badge(run.status), time);
        button.addEventListener('click', () => {
          invalidatePreview('当前查看历史记录；如需新审计，请重新预览当前输入。');
          clearEvidence(); state.displayed = null;
          summary('正在读取历史报告', `运行编号 ${run.runId}。读取不会调用模型。`);
          watchRun(run.runId);
        });
        region.append(button);
      }
      if (!region.childElementCount) empty(region, '暂无运行记录。先预览一个目标，再开始离线演练或明确选择真实审计。');
    } catch (error) {
      if (epoch === state.historyEpoch) empty(byId('history-list'), `历史读取失败：${error.message} 点击刷新历史可重试。`);
    } finally { if (epoch === state.historyEpoch) byId('refresh-history').disabled = false; }
  }

  initTabs(['input-preset-tab', 'input-source-tab'], id => {
    const kind = id === 'input-preset-tab' ? 'preset' : 'source';
    if (kind === state.inputKind) return;
    state.inputKind = kind;
    if (kind === 'source') { byId('function-input').value = ''; byId('risk-line').value = ''; }
    updateTargetFields(); invalidatePreview();
  });
  const selectSourceTab = initTabs(['source-full-tab', 'source-model-tab']);
  initTabs(['retrieval-tab', 'hypotheses-tab', 'tools-tab', 'd2-tab']);
  byId('target-origin').addEventListener('change', () => { populateTargets(); invalidatePreview(); });
  byId('sample-select').addEventListener('change', () => { updateTargetFields(); invalidatePreview(); });
  for (const id of ['source-input', 'function-input', 'risk-line', 'mechanism-select', 'strategy-select', 'mode-select']) {
    byId(id).addEventListener(['source-input', 'function-input', 'risk-line'].includes(id) ? 'input' : 'change', () => {
      invalidatePreview();
      if (id === 'source-input') {
        const length = bytes(byId(id).value);
        byId('source-byte-count').textContent = `${length} / ${SOURCE_LIMIT} 字节 · ${length > SOURCE_LIMIT ? '已超过 128 KiB，请缩小输入。' : '风险行使用完整源码的行号。'}`;
        byId(id).setCustomValidity(length > SOURCE_LIMIT ? '源码超过 128 KiB' : '');
      }
      updateActions();
    });
  }
  byId('embedding-select').addEventListener('change', () => {
    state.status = null; invalidatePreview('知识向量模型已切换，正在核对对应快照。'); loadStatus();
  });
  byId('real-consent').addEventListener('change', updateActions);
  byId('audit-input').addEventListener('submit', preview);
  byId('run-button').addEventListener('click', startRun);
  byId('refresh-status').addEventListener('click', loadStatus);
  byId('refresh-history').addEventListener('click', loadHistory);
  byId('line-form').addEventListener('submit', event => {
    event.preventDefault();
    const line = Number(byId('line-jump').value);
    if (!Number.isSafeInteger(line) || !state.fullLines.has(line)) { byId('source-message').textContent = '请输入完整源码范围内的有效行号。'; return; }
    locate([line], 'focus');
  });
  window.addEventListener('pagehide', () => { stopReading(); state.previewAbort?.abort(); });
  updateTargetFields(); renderStages({});
  // 初始化与历史回放仅调用读取接口，绝不自动创建审计。
  Promise.allSettled([loadStatus(), loadTargets(), loadHistory()]);
})();
