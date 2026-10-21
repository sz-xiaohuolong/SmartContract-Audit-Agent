"""为完整单文件输入生成固定 solc 收据；含依赖的输入须提供登记清单。"""
import hashlib
import json
import subprocess
import uuid
from pathlib import Path

from verirag.analysis.compiler_facts import load_bound_compilation
from verirag.analysis.program_facts import _tokens
from verirag.infrastructure.storage import atomic_json
from verirag.infrastructure.tool_environment import _configuration, resolve_environment

_CACHE = {}


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                      allow_nan=False).encode('utf-8')


def prepare_compilation(root, target):
    """按保存候选绑定合约；不下载编译器，不改变原件或知识快照。"""
    return _prepare_compilation(root, target, discovery=False)


def prepare_discovery_compilation(root, target):
    """仅从真实编译 AST 选择目录入口；不消费候选、标签、漏洞行或目标合约猜测。"""
    return _prepare_compilation(root, target, discovery=True)


def _prepare_compilation(root, target, *, discovery):
    """候选核验与发现共用原字节编译、收据和重新编译检查。"""
    root = Path(root).resolve()
    source = target.get('fullSource', target.get('source'))
    if not isinstance(source, str) or not source.strip():
        raise ValueError('编译源码缺失')
    source_hash = _sha(source.encode('utf-8'))
    if any(target.get(key, source_hash) != source_hash for key in ('sourceHash', 'fullSourceHash')):
        raise ValueError('编译源码摘要不一致')
    if target.get('discoveryCompilation') is not None:
        original = load_bound_compilation(target['discoveryCompilation'], root)
        if original['sourceHash'] != source_hash:
            raise ValueError('发现编译源码摘要不一致')
        contracts = target.get('candidateContracts', [])
        contract = target.get('contract')
        if contract is None and len(contracts) == 1:
            contract = contracts[0]
        if discovery:
            contract = original['targetContract']
        if not isinstance(contract, str) or not contract or len(set(contracts)) > 1:
            raise ValueError('候选未唯一绑定目标合约')
        # 投影只改变目标选择；输入、输出和收据身份保持原始发现字节。
        manifest = {**original['manifest'], 'targetContract': contract}
        projected = load_bound_compilation(manifest, root)
        if any(projected[key] != original[key] for key in ('sourceHash', 'receiptDigest', 'environmentHash')):
            raise ValueError('发现编译投影身份不一致')
        return manifest
    if target.get('compilerManifest') is not None:
        bundle = load_bound_compilation(target['compilerManifest'], root)
        if bundle['sourceHash'] != source_hash:
            raise ValueError('登记编译源码摘要不一致')
        return target['compilerManifest']
    tokens, _ = _tokens(source)
    template = target.get('compilerTemplate')
    if template is None and any(token[0] == 'import' for token in tokens):
        raise ValueError('输入依赖闭包缺失；请使用登记的完整编译清单')
    contracts = [] if discovery else target.get('candidateContracts', [])
    contract = None if discovery else target.get('contract')
    if contract is None and len(contracts) == 1:
        contract = contracts[0]
    if not discovery and (not isinstance(contract, str) or not contract):
        raise ValueError('候选未唯一绑定目标合约')
    if len(set(contracts)) > 1:
        raise ValueError('多个候选合约须分别绑定编译清单')
    configuration = target.get('_toolConfiguration')
    if configuration is None:
        path = root / 'config/tools.local.properties'
        configuration = _configuration(path) if path.is_file() else {}
    original_bundle = load_bound_compilation(template, root) if template is not None else None
    environment = resolve_environment(source, configuration) if original_bundle is None else None
    if environment is not None and environment.get('status') != 'OK':
        raise ValueError('固定编译器不可用：' + str(environment.get('errorCategory')))
    binary = Path(original_bundle['binding']['compiler'] if original_bundle else environment['compiler']['path']).resolve()
    binary_hash = _sha(binary.read_bytes())
    expected_binary_hash = original_bundle['binding']['compilerSha256'] if original_bundle else environment['compiler']['sha256']
    if binary_hash != expected_binary_hash:
        raise ValueError('固定编译器身份发生漂移')
    cache_key = _sha(_canonical({'sourceHash': source_hash, 'contract': contract,
        'compilerSha256': binary_hash, 'template': original_bundle['manifestDigest'] if original_bundle else None,
        'root': str(root)}))
    if cache_key in _CACHE:
        load_bound_compilation(_CACHE[cache_key], root)
        return _CACHE[cache_key]
    directory = root / 'research-artifacts/receipts/compilations' / uuid.uuid4().hex
    directory.mkdir(parents=True, exist_ok=False)
    # 固定单元名与运行目录一致，Slither 的源码映射不依赖临时文件名猜测。
    unit = original_bundle['targetSourceUnit'] if original_bundle else 'contracts/C.sol'
    settings = original_bundle['input']['settings'] if original_bundle else {'optimizer': {'enabled': False, 'runs': 200},
                'outputSelection': {'*': {'': ['ast'], '*': ['abi', 'evm.bytecode.object',
                    'evm.bytecode.sourceMap', 'evm.deployedBytecode.object',
                    'evm.deployedBytecode.sourceMap', 'evm.methodIdentifiers']}}}
    sources = {name: {'content': value['content']} for name, value in original_bundle['input']['sources'].items()} if original_bundle else {}
    sources[unit] = {'content': source}
    source_receipts, source_hashes = {}, {}
    for name, value in sources.items():
        path = (directory / name).resolve()
        if not path.is_relative_to(directory) or Path(name).is_absolute():
            raise ValueError('编译模板源码单元路径越界')
        path.parent.mkdir(parents=True, exist_ok=True)
        content = value['content'].encode('utf-8')
        path.write_bytes(content)
        source_hashes[name] = _sha(content)
        source_receipts[name] = {'path': str(path.relative_to(root)), 'resolvedPath': str(path),
                                 'sha256': source_hashes[name]}
    compiler_input = {'language': 'Solidity', 'sources': sources, 'settings': settings}
    input_bytes = _canonical(compiler_input)
    (directory / 'input.json').write_bytes(input_bytes)
    probe = subprocess.run([str(binary), '--version'], capture_output=True, timeout=5, check=False)
    if probe.returncode != 0:
        raise ValueError('固定编译器版本查询失败')
    run = subprocess.run([str(binary), '--standard-json'], input=input_bytes,
                         capture_output=True, timeout=120, check=False, cwd=directory)
    (directory / 'compiler-stderr.log').write_bytes(run.stderr)
    (directory / 'output.json').write_bytes(run.stdout)
    if _sha(binary.read_bytes()) != binary_hash:
        raise ValueError('编译期间固定二进制变化')
    if run.returncode != 0:
        diagnostic = run.stderr.decode('utf-8', errors='replace').lower()
        if '--standard-json' in diagnostic and any(word in diagnostic for word in
                ('unrecognised', 'unrecognized', 'unknown option', 'invalid option')):
            raise ValueError('固定编译器不支持 standard-json 协议；原始输出已保留，不能更换版本或改写原输入')
        raise ValueError('固定编译器执行失败，原始输出已保留')
    try:
        output = json.loads(run.stdout)
    except (ValueError, UnicodeError) as error:
        raise ValueError('固定编译器输出不是有效 JSON，原始输出已保留') from error
    if not isinstance(output, dict) or any(
            not isinstance(error, dict) or error.get('severity') == 'error' for error in output.get('errors', [])):
        raise ValueError('固定编译器执行或源码编译失败，原始输出已保留')
    if discovery:
        # 只选择可由真实 AST 与 ABI 共同绑定的主源码合约作为入口。
        # 风险目录随后枚举完整闭包；此排序不表示风险高低或标签选择。
        ast = output.get('sources', {}).get(unit, {}).get('ast', {})
        artifacts = output.get('contracts', {}).get(unit, {})
        available = sorted(node['name'] for node in ast.get('nodes', [])
            if node.get('nodeType') == 'ContractDefinition' and isinstance(node.get('name'), str)
            and isinstance(artifacts.get(node['name']), dict)
            and isinstance(artifacts[node['name']].get('abi'), list))
        if not available:
            raise ValueError('主源码没有可由编译 AST 与 ABI 绑定的合约，原始输出已保留')
        contract = available[0]
    relative = str(directory.relative_to(root))
    receipt = {'status': 'COMPILED', 'mainSource': unit, 'environment': relative,
               'sourceUnits': source_receipts,
               'compiler': str(binary), 'compilerSha256': binary_hash,
               'compilerVersion': probe.stdout.decode('utf-8').strip(),
               'command': [str(binary), '--standard-json'], 'settings': settings,
               'exitCode': run.returncode, 'errors': [], 'inputSha256': _sha(input_bytes),
               'outputSha256': _sha(run.stdout), 'sourceClosureSha256': _sha(_canonical(source_hashes))}
    atomic_json(directory / 'binding.json', receipt)
    manifest = {'schemaVersion': '1', 'provider': 'solc-standard-json',
                'bindingPath': relative + '/binding.json',
                'bindingSha256': _sha((directory / 'binding.json').read_bytes()),
                'inputPath': relative + '/input.json', 'outputPath': relative + '/output.json',
                'targetSourceUnit': unit, 'targetContract': contract, 'expectedSourceHash': source_hash}
    atomic_json(directory / 'manifest.json', manifest)
    load_bound_compilation(manifest, root)
    if len(_CACHE) >= 128:
        _CACHE.pop(next(iter(_CACHE)))
    _CACHE[cache_key] = manifest
    return manifest


def prepare_candidate_compilations(root, target):
    """多合约保存假设各自绑定，绝不改写原模型的目标合约。"""
    contracts = target.get('candidateContracts', [])
    if not contracts:
        return None
    if len(contracts) == 1:
        return prepare_compilation(root, target)
    manifests, errors = {}, {}
    for contract in contracts:
        try:
            manifests[contract] = prepare_compilation(root, {**target, 'contract': contract,
                                                            'candidateContracts': [contract]})
        except (ValueError, OSError, subprocess.TimeoutExpired) as error:
            errors[contract] = str(error)
    return {'provider': 'contract-map', 'manifests': manifests, 'errors': errors}
