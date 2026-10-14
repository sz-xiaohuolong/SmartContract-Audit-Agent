"""SYNAPSE 因素预注册与一次探索采集分开；不覆盖历史六臂协议。"""
from storage import fingerprint


def build_synapse_protocol(plan, code_identity, template_identity, *, admission=None):
    """固定完整分母和身份，付费授权只对应本次三策略一次采集。"""
    targets = plan.get('sampleIds', [])
    if (not targets or len(set(targets)) != len(targets)
            or set(plan.get('sourceHashes', {})) != set(targets)
            or plan.get('strategies') != ['VANILLA', 'DENSE', 'D1']):
        raise ValueError('单次三策略协议的目标或输入闭包无效')
    admission = admission or {}
    required = ['independentLabels', 'sourceAndSplitAudit', 'exactTokenFairness', 'realFixBidirectionalProof']
    missing = [key for key in required if admission.get(key) is not True]
    requests = len(targets) * 3 + 2
    factors = [
        {'id': 'RQ-A', 'arms': ['变化窗口', '模板未绑定', '模板实例化'],
         'fixed': ['同一候选池、入选pair和来源', 'FULL源码', '共同system、模型参数和最终消息预算'],
         'metrics': ['位置及理由均正确的发现率', '适用性正确率', '失败及弃权率']},
        {'id': 'RQ-B', 'arms': ['FULL', '固定焦点上下文', '按需焦点上下文'],
         'fixed': ['模板与验证器', '完整输入token上限'],
         'metrics': ['覆盖率', '未解析引用', '完整性', 'usage及成本']},
        {'id': 'RQ-C', 'arms': ['无验证', 'guard基线', '具体行基线', 'D2与独立复核'],
         'fixed': ['原候选完整分母', '独立候选真值'],
         'metrics': ['错误接受', '错误拒绝', 'UNKNOWN', '耗时']}]
    for factor in factors:
        factor.update(executionAuthorized=False, repetitions=3,
                      status='PREREGISTERED_PENDING_ADMISSION', newModelRequests=0)
    protocol = {'schemaVersion': 'synapse-protocol-1', 'historicalPlanHash': plan.get('planHash'),
        'sourceHashes': plan['sourceHashes'], 'targetIds': targets, 'snapshotId': plan['snapshotId'],
        'codeIdentity': code_identity, 'templateIdentity': template_identity, 'provider': plan.get('provider'),
        'factorExperiments': factors, 'preservesHistoricalSixArmProtocol': True,
        'authorizedCollection': {'strategies': plan['strategies'], 'repetitions': 1,
            'smokeRequests': 2, 'formalRequests': len(targets) * 3, 'maxRequests': requests,
            'retries': 0, 'kind': 'DATASET_LABEL_EXPLORATORY',
            'inputMode': 'FULL', 'd1Presentation': 'ORIGINAL_PAIRS',
            'focusAndTemplatesConsumedByModel': False, 'reviewModelRequests': 0},
        'budget': {'maxInputTokens': None, 'maxOutputTokens': requests * 16384,
            'outputTokensPerRequest': 16384, 'tokenizer': None, 'fairnessStatus': 'UNVERIFIED',
            'estimatedAmount': None, 'actualUsageRequired': True, 'missingUsage': None,
            'countingRule': '完整system、源码、上下文、目录和消息封装；不以UTF-8字节替代token'},
        'admission': {'requirements': required, 'missing': missing}, 'researchEligible': not missing,
        'evaluation': {'fullDenominator': '所有冻结目标×三策略；失败与弃权保留原分母',
            'commonEffectiveTargets': '三策略均有有效模型结果的交集另列，不替代全分母',
            'candidateTruth': '独立审核未齐时混淆矩阵及精确率保持null',
            'effectMethod': '正式实验按项目成组配对bootstrap或置换；本轮只做探索描述',
            'minimumMeaningfulEffect': None, 'errorTolerance': None,
            'rule': '数值门槛和独立标签在正式测试解盲前冻结'}, 'newModelRequests': 0}
    return {**protocol, 'protocolHash': fingerprint(protocol)}
