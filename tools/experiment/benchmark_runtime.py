"""自动标注 S1b 快照上的同池三策略与结构化模型审计适配。"""
from pathlib import Path
from time import monotonic
import uuid
import hashlib
from storage import durable_write

from audit_run import model_runner as default_model_runner, tool_runner as default_tool_runner
from evaluation_input import clean_evaluation_source
from formal_recall import CONTEXT_BYTES, java_retrieval, select_strategy
from program_facts import extract_facts
from recall import _recall_candidates
from snapshots import active_snapshot, vector32, verify_snapshot
from storage import decode, fingerprint
from d1_consumption import risk_bindings, soft_pairs


def interpret_model(model, mode):
    if mode != 'real' or model.get('status') != 'COMPLETED':
        return 'UNKNOWN'
    return {'VULNERABILITY_REPORTED': 'REPORT',
            'NO_CONFIRMED_FINDINGS': 'NO_REPORT'}.get(model.get('conclusion'), 'UNKNOWN')


def soft_without_risk(pool, mechanism):
    return soft_pairs(pool, mechanism, CONTEXT_BYTES, 4)


def _risk_fact(facts, target):
    if facts['status'] == 'FAILED':
        return None
    task_kind = target.get('taskKind', 'DISCOVERY')
    if task_kind not in ('DISCOVERY', 'CLAIM_VALIDATION'):
        raise ValueError('评测任务类型无效')
    risk_line = target.get('riskLine') if task_kind == 'CLAIM_VALIDATION' else None
    if task_kind == 'CLAIM_VALIDATION' and risk_line is None and target.get('claimOrigin') != 'REGISTERED_FUNCTION_SCOPE':
        return None
    if risk_line is not None and (type(risk_line) is not int or risk_line < 1):
        return None
    kinds = {'CALL'} if target['mechanism'] == 'REENTRANCY' else {'CALL', 'WRITE'}
    scopes = {row['id'] for row in facts['scopes'] if task_kind == 'DISCOVERY' and target.get('scope') == 'FULL'
              or row['name'] == target['function']
              and (not target.get('contract') or row['contract'] == target['contract'])}
    matches = [row for row in facts['facts'] if row['kind'] in kinds
               and (risk_line is None or row['line'] == risk_line)
               and (target.get('lineStart') is None or target['lineStart'] <= row['line'])
               and (target.get('lineEnd') is None or row['line'] <= target['lineEnd'])
               and row['scope'] in scopes]
    return matches[0] if len(matches) == 1 else None


def _validate_input(target):
    if target.get('runnable') is False:
        raise ValueError(target.get('inputReason') or '目标不可运行，请显式选择有效的源码范围')
    source, model = target.get('fullSource'), target.get('modelSource')
    if not isinstance(source, str) or not isinstance(model, str):
        raise ValueError('消费源码缺失')
    source_hash = hashlib.sha256(source.encode('utf-8')).hexdigest()
    model_hash = hashlib.sha256(model.encode('utf-8')).hexdigest()
    if (target.get('sourceHash') != source_hash or target.get('fullSourceHash') != source_hash
            or target.get('modelSourceHash') != model_hash):
        raise ValueError('消费源码与模型输入摘要不一致')
    if 'originalSource' in target or 'originalSourceHash' in target:
        original = target.get('originalSource')
        if (not isinstance(original, str)
                or hashlib.sha256(original.encode('utf-8')).hexdigest() != target.get('originalSourceHash')):
            raise ValueError('原件源码与原件摘要不一致')
        if clean_evaluation_source(original)['fullSource'] != source:
            raise ValueError('清理全文无法追溯到声明的原件')
    scope = target.get('scope')
    start, end = target.get('lineStart'), target.get('lineEnd')
    if (scope not in ('FULL', 'FUNCTION') or type(start) is not int or type(end) is not int
            or not 1 <= start <= end <= len(source.splitlines())):
        raise ValueError('模型输入的原始行范围无效')
    expected = source if scope == 'FULL' else '\n'.join(source.splitlines()[start - 1:end])
    if model != expected or scope == 'FULL' and (start != 1 or end != len(source.splitlines())):
        raise ValueError('模型输入与清理全文或声明的行范围不一致')
    receipt = target.get('inputGovernanceReceipt')
    if receipt is not None and (not isinstance(receipt, dict)
            or receipt.get('originalSourceHash') != target.get('originalSourceHash')
            or receipt.get('fullSourceHash') != source_hash
            or receipt.get('modelSourceHash', model_hash) != model_hash):
        raise ValueError('输入清理回执与消费摘要不一致')


class BenchmarkRuntime:
    def __init__(self, root, index, encoder, model_runner=default_model_runner, java_runner=None,
                 snapshot_root=None, tool_runner=default_tool_runner):
        self.root = Path(root).resolve()
        self.index = index
        self.encoder = encoder
        self.model_runner = model_runner
        self.tool_runner = tool_runner
        self.java_runner = java_runner or (lambda source, request: java_retrieval(self.root, source, request))
        self.store = Path(snapshot_root) if snapshot_root is not None else self.root / 'research-artifacts/snapshots/bge'
        self.pointer = active_snapshot(self.store, index)
        self.snapshot = verify_snapshot(self.store, self.pointer['snapshot_id'])
        embedding = self.snapshot['embedding']
        if embedding['model'].startswith('ollama/') and (
                getattr(encoder, 'digest', None) != embedding['revision']
                or embedding['dimension'] != 768):
            raise ValueError('Nomic 查询模型与活动知识快照不一致')
        if not all(row['review_status'] == 'AUTO_LABELED' for row in self.snapshot['manifest']['samples']):
            raise ValueError('当前活动快照不是自动标注知识层')
        self.catalog = decode((self.store / 'catalogs' / (self.pointer['snapshot_id'] + '.json')).read_bytes())
        self.views = {}

    def preview(self, target):
        if decode((self.store / 'active.json').read_bytes()) != self.pointer:
            raise ValueError('批量过程中活动知识快照已改变')
        _validate_input(target)
        original_hash = target.get('originalSourceHash', target['sourceHash'])
        if any(row['split'] == 'knowledge' and row['source_hash'] in (target['sourceHash'], original_hash)
               for row in self.snapshot['manifest']['samples']):
            raise ValueError('目标原件或消费源码属于知识划分，拒绝评测')
        key = fingerprint({name: target.get(name) for name in
                           ('sampleId', 'sourceHash', 'modelSourceHash', 'mechanism', 'function',
                            'scope', 'contract', 'lineStart', 'lineEnd', 'taskKind', 'riskLine')})
        if key in self.views:
            return self.views[key]
        if hasattr(self.encoder, 'encode_query'):
            encoded, query_receipt = self.encoder.encode_query(target['modelSource'])
        else:
            vectors = self.encoder([target['modelSource']])
            if len(vectors) != 1:
                raise ValueError('查询向量数量无效')
            encoded, query_receipt = vectors[0], None
        query = vector32([float(value) for value in encoded], self.snapshot['embedding']['dimension'])
        recalled = _recall_candidates(self.store, self.pointer['snapshot_id'], self.catalog,
            query, target['modelSource'], min(80, len(self.snapshot['rows'])),
            lambda value, limit: self.index.search(self.pointer['collection'], value, limit),
            target['sourceHash'], True)
        pool = recalled['pool']
        facts = extract_facts(target['fullSource'])
        risk = _risk_fact(facts, target)
        if risk is None:
            d1 = soft_without_risk(pool, target['mechanism'])
        else:
            request = {'target': {'mechanism': target['mechanism'], 'riskFactId': risk['id'],
                       'bindings': risk_bindings(facts, risk)},
                       'pool': pool, 'budget': {'maxBytes': CONTEXT_BYTES, 'maxCases': 4}}
            response = self.java_runner(target['fullSource'], request)
            results = response.get('results') if isinstance(response, dict) else None
            if (not isinstance(results, list) or len(results) != 1 or results[0].get('strategy') != 'D1'
                    or results[0].get('sourceHash') != target['sourceHash']
                    or results[0].get('snapshotId') != self.pointer['snapshot_id']):
                raise ValueError('Java D1 返回的源码或快照身份无效')
            d1 = results[0]
            d1 = {**d1, 'consumptionVersion': recalled['recall']['consumptionVersion']}
        view = {'pool': pool, 'd1': d1, 'snapshotId': self.pointer['snapshot_id'],
                'collection': self.pointer['collection'], 'sourceHash': target['sourceHash'],
                'modelSourceHash': target['modelSourceHash'], 'taskKind': target.get('taskKind', 'DISCOVERY'),
                'inputGovernanceReceipt': target.get('inputGovernanceReceipt'),
                'targetMechanism': target['mechanism'], 'facts': facts, 'researchEligible': False,
                'recall': recalled['recall'],
                'queryEmbeddingReceipt': query_receipt}
        if getattr(self, 'r3', None) is not None:
            view.update(r3QueryVector=query, r3QueryText=target['modelSource'])
        self.views[key] = view
        return view

    def run(self, target, strategy, mode):
        from audit_workbench import assess, final_conclusion
        target = dict(target)
        if target.get('compilerTemplate') is not None:
            from compilation_runtime import prepare_compilation
            target['compilerManifest'] = prepare_compilation(self.root, target)
        pipeline_started = monotonic()
        from r3_retrieval import STRATEGIES as R3_STRATEGIES
        if strategy in R3_STRATEGIES:
            if getattr(self, 'r3', None) is None:
                raise ValueError('R3 策略缺少版本化知识卡片，禁止静默降级')
            view = self.r3.select(self.preview(target), strategy,
                                  allow_unreviewed=getattr(self, 'r3_allow_unreviewed', False))
        else:
            view = select_strategy(self.preview(target), strategy)
        if target.get('compilerManifest') is not None:
            from compiler_facts import extract_compiler_facts, load_bound_compilation
            bundle = load_bound_compilation(target['compilerManifest'], self.root)
            if bundle['sourceHash'] != target.get('fullSourceHash'):
                raise ValueError('编译目标与批量消费源码字节不一致')
            view['compiledFacts'] = extract_compiler_facts(bundle)
        from risk_catalog import prepare_model_context
        prepare_model_context(self.root, target, view, mode)
        if view.get('discoveryCompilation') is not None:
            target['discoveryCompilation'] = view['discoveryCompilation']
        from check_templates import prepare_template_presentation
        if hasattr(self, 'snapshot'):
            prepare_template_presentation(self.root, view, self.snapshot)
        selected = view['d1'].get('selected', [])
        started = monotonic()
        model = self.model_runner(self.root, target, view, mode)
        duration = round((monotonic() - started) * 1000)
        if not isinstance(model, dict) or model.get('status') not in ('COMPLETED', 'FAILED'):
            raise ValueError('结构化模型结果无效')
        diagnostic_path = None
        if (model.get('status') == 'FAILED' or model.get('validationIssue')) and isinstance(model.get('_rawResponse'), str):
            diagnostic = self.root / 'research-artifacts/diagnostics/benchmark' / (uuid.uuid4().hex + '.txt')
            diagnostic.parent.mkdir(parents=True, exist_ok=True)
            durable_write(diagnostic, model['_rawResponse'].encode('utf-8'))
            diagnostic.chmod(0o600)
            diagnostic_path = str(diagnostic.relative_to(self.root))
        model = {key: value for key, value in model.items() if key != '_rawResponse'}
        compilation_error = None
        compilation_diagnostic = None
        if (mode == 'real' and (target.get('compilerManifest') is None or target.get('discoveryCompilation') is not None)
                and (self.root / 'config/tools.local.properties').is_file() and model.get('hypotheses')):
            from compilation_runtime import prepare_candidate_compilations
            from tool_environment import _configuration
            try:
                configuration = _configuration(self.root / 'config/tools.local.properties')
                # 编译器目录启用新版 AST 流程；显式编译清单不受此兼容开关限制。
                if configuration.get('tools.compiler.directory'):
                    target['_toolConfiguration'] = configuration
                    target['candidateContracts'] = sorted({h['contract'] for h in model['hypotheses']})
                    target['compilerManifest'] = prepare_candidate_compilations(self.root, target)
            except (ValueError, OSError) as error:
                compilation_error = 'COMPILATION_BINDING_FAILED'
                compilation_diagnostic = str(error)
        tool_started = monotonic()
        try:
            tools = getattr(self, 'tool_runner', default_tool_runner)(self.root, target, mode)
            if not isinstance(tools, list) or not tools or any(not isinstance(row, dict) for row in tools):
                raise ValueError('工具结果缺失')
        except Exception:
            tools = [{'engine': 'SLITHER', 'status': 'PROCESS_ERROR', 'issues': [],
                      'durationMs': round((monotonic() - tool_started) * 1000), 'version': None}]
        failed_tools = any(row.get('status') not in ('OK', 'SKIPPED') for row in tools)
        d2_failed = False
        try:
            if compilation_error:
                raise ValueError(compilation_error)
            d2 = assess(model, view.get('facts', {}), tools, target.get('fullSource'), target=target,
                        compilation_manifest=target.get('compilerManifest'), root=self.root)
            d2_failed = d2.get('status') == 'FAILED'
        except Exception:
            d2_failed = True
            d2 = {'schemaVersion': '2', 'verdict': 'UNKNOWN', 'assessments': [], 'errorCategory': 'D2_EXECUTION_ERROR'}
        failed = model['status'] != 'COMPLETED' or failed_tools or d2_failed
        return {'pipelineVersion': 's9-v1', 'status': model['status'],
                'pipelineStatus': 'FAILED' if failed else 'COMPLETED',
                'prediction': interpret_model(model, mode),
                'modelPrediction': interpret_model(model, mode),
                'conclusion': final_conclusion(model, d2, failed, mode),
                'tools': tools, 'd2': d2,
                'compilationManifest': target.get('compilerManifest'),
                'compilationError': compilation_error,
                'compilationDiagnostic': compilation_diagnostic,
                'retrieval': view, 'source': target.get('fullSource'),
                'poolHash': fingerprint(view['pool']),
                'queryEmbeddingReceipt': view.get('queryEmbeddingReceipt'),
                'diagnosticPath': diagnostic_path, 'requestAttempts': model.get('requestAttempts'),
                'selectedIds': [row['candidate']['chunkId'] for row in selected],
                'selectedEvidence': len(selected),
                'categoryHit': (any(row['candidate']['mechanism'] == target['mechanism'] for row in selected)
                                if strategy != 'VANILLA' and target['groundTruth']['hasVulnerability'] else None),
                'retrievalGaps': view['d1'].get('gaps', []),
                'errorCategory': model.get('errorCategory') or ('TOOLS_FAILED' if failed_tools else 'D2_EXECUTION_ERROR' if d2_failed else None),
                'inputTokens': model.get('inputTokens'), 'outputTokens': model.get('outputTokens'),
                'durationMs': duration, 'modelDurationMs': duration,
                'pipelineDurationMs': round((monotonic() - pipeline_started) * 1000), 'model': model}
