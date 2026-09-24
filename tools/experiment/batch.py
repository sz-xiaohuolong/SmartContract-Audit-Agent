"""追加式实验日志：逐条落盘、保守恢复与只读重放。"""
import os
from pathlib import Path

from isolation import nonempty, sha256_value, validate_manifest
from offline import digest, evaluate
from snapshots import verify_snapshot
from storage import decode, encode, exclusive_lock, fingerprint, sync_directory


def validate_plan(plan, execution):
    if not isinstance(plan, dict) or set(plan) != {"schema_version", "manifest", "sample_ids", "type_mapping", "mode", "kb_snapshot"}:
        raise ValueError("实验计划字段无效")
    if plan["schema_version"] != "1" or plan["mode"] != "Vanilla":
        raise ValueError("当前执行器只支持 S0 Vanilla 审计")
    indexed = validate_manifest(plan["manifest"])
    ids = plan["sample_ids"]
    if (not isinstance(ids, list) or not ids or any(not isinstance(i, str) for i in ids)
            or len(set(ids)) != len(ids) or any(i not in indexed or indexed[i]["split"] == "knowledge" for i in ids)):
        raise ValueError("计划样本为空、重复、未知或来自知识划分")
    mapping = plan["type_mapping"]
    if not isinstance(mapping, dict): raise ValueError("类型映射无效")
    for key, values in mapping.items():
        if not nonempty(key) or not isinstance(values, list) or not values:
            raise ValueError("阳性类型必须映射到非空的规范类型集合")
        evaluate(plan["manifest"]["categories"], [{"id": "mapping", "types": values}], [])
    if plan["kb_snapshot"] is not None and not sha256_value(plan["kb_snapshot"]):
        raise ValueError("知识快照 ID 无效")
    if (not isinstance(execution, dict) or set(execution) != {"config_hash", "artifact_hash", "provider", "timeout_seconds"}
            or not sha256_value(execution["config_hash"]) or not sha256_value(execution["artifact_hash"])
            or not nonempty(execution["provider"]) or type(execution["timeout_seconds"]) not in (int, float)
            or not 0 < execution["timeout_seconds"] <= 86400):
        raise ValueError("执行配置绑定无效")
    return indexed


def _failure(category, status="FAILED"):
    return {"status": status, "types": [], "input_tokens": None, "output_tokens": None,
            "error_category": category, "raw": None}


def normalize_result(raw, row, plan, execution):
    """精确映射 S0 输出；未知类型、绑定不符或非法结果一律失败。"""
    fields = {"schemaVersion", "sourceHash", "status", "conclusion", "vulnerabilityType", "reason",
              "provider", "model", "inputTokens", "outputTokens", "durationMs", "errorCategory"}
    try:
        if not isinstance(raw, dict) or set(raw) != fields: raise ValueError()
        if (raw["schemaVersion"] != "1" or raw["sourceHash"] != row["source_hash"]
                or raw["provider"] != execution["provider"]): raise ValueError()
        for key in ("inputTokens", "outputTokens"):
            if raw[key] is not None and (type(raw[key]) is not int or raw[key] < 0): raise ValueError()
        if type(raw["durationMs"]) is not int or raw["durationMs"] < 0: raise ValueError()
        if raw["model"] is not None and not nonempty(raw["model"]): raise ValueError()
        types = []
        if raw["status"] == "FAILED":
            if raw["conclusion"] != "UNRESOLVED" or not nonempty(raw["errorCategory"]): raise ValueError()
            if raw["vulnerabilityType"] is not None or raw["reason"] is not None: raise ValueError()
        elif raw["status"] == "COMPLETED":
            if raw["errorCategory"] is not None or not nonempty(raw["reason"]) or not isinstance(raw["vulnerabilityType"], str):
                raise ValueError()
            if raw["conclusion"] == "VULNERABILITY_REPORTED":
                if raw["vulnerabilityType"] not in plan["type_mapping"]:
                    return dict(_failure("TYPE_UNMAPPED"), input_tokens=raw["inputTokens"],
                                output_tokens=raw["outputTokens"], raw=decode(encode(raw)))
                types = plan["type_mapping"][raw["vulnerabilityType"]]
            elif raw["conclusion"] != "NO_CONFIRMED_FINDINGS": raise ValueError()
        else: raise ValueError()
        return {"status": raw["status"], "types": sorted(set(types)),
                "input_tokens": raw["inputTokens"], "output_tokens": raw["outputTokens"],
                "error_category": raw["errorCategory"], "raw": decode(encode(raw))}
    except (ValueError, TypeError, KeyError):
        return _failure("RESULT_INVALID")


def _read_journal(path):
    data = Path(path).read_bytes()
    end = data.rfind(b"\n") + 1
    incomplete = end != len(data)
    events, previous = [], None
    for line in data[:end].splitlines():
        event = decode(line)
        if not isinstance(event, dict) or set(event) != {"seq", "previous", "payload", "hash"}:
            raise ValueError("日志事件字段无效")
        signed = {key: event[key] for key in ("seq", "previous", "payload")}
        if (type(event["seq"]) is not int or event["seq"] != len(events)
                or event["previous"] != previous or fingerprint(signed) != event["hash"]):
            raise ValueError("日志校验链损坏或事件重复")
        events.append(event)
        previous = event["hash"]
    return events, end, incomplete


def _append(output, events, payload):
    signed = {"seq": len(events), "previous": events[-1]["hash"] if events else None, "payload": payload}
    event = dict(signed, hash=fingerprint(signed))
    output.write(encode(event) + b"\n")
    output.flush()
    os.fsync(output.fileno())
    events.append(event)


def _state(events):
    if not events: raise ValueError("日志没有完整实验头")
    header = events[0]["payload"]
    if not isinstance(header, dict) or set(header) != {"kind", "plan", "execution"} or header["kind"] != "RUN":
        raise ValueError("实验头无效")
    plan, execution = header["plan"], header["execution"]
    indexed = validate_plan(plan, execution)
    states = {}
    for event in events[1:]:
        payload = event["payload"]
        if not isinstance(payload, dict): raise ValueError("日志载荷无效")
        identifier = payload.get("id")
        if identifier not in plan["sample_ids"]: raise ValueError("日志出现计划外样本")
        old = states.get(identifier)
        attempt = payload.get("attempt")
        if type(attempt) is not int or attempt < 1: raise ValueError("尝试编号无效")
        if payload.get("kind") == "START":
            if set(payload) != {"kind", "id", "attempt", "retry"} or type(payload["retry"]) is not bool:
                raise ValueError("开始事件无效")
            if old is None:
                if attempt != 1 or payload["retry"]: raise ValueError("首次调用事件无效")
            elif old["result"] is None or old["result"]["status"] == "COMPLETED" or attempt != old["attempt"] + 1 or not payload["retry"]:
                raise ValueError("重复调用或未授权重试")
            states[identifier] = {"attempt": attempt, "result": None}
        elif payload.get("kind") == "RESULT":
            if set(payload) != {"kind", "id", "attempt", "result"} or old is None or old["result"] is not None or attempt != old["attempt"]:
                raise ValueError("结果事件顺序无效")
            result = payload["result"]
            if not isinstance(result, dict): raise ValueError("规范结果无效")
            if result.get("raw") is None:
                allowed = [_failure("ADAPTER_ERROR"), _failure("RESULT_INVALID"), _failure("CALL_INTERRUPTED", "UNRESOLVED")]
                if result not in allowed: raise ValueError("合成失败结果无效")
            elif result != normalize_result(result["raw"], indexed[identifier], plan, execution):
                raise ValueError("规范结果与原始结果不一致")
            states[identifier]["result"] = result
        else: raise ValueError("未知阶段事件")
    return header, states


def _report(events, incomplete):
    header, states = _state(events)
    plan = header["plan"]
    indexed = {r["id"]: r for r in plan["manifest"]["samples"]}
    results = []
    for identifier in plan["sample_ids"]:
        if identifier in states:
            state = states[identifier]
            result = state["result"] or _failure("CALL_INTERRUPTED", "UNRESOLVED")
            results.append(dict(result, id=identifier, attempt=state["attempt"]))
    predictions = [{key: row[key] for key in ("id", "status", "types")} for row in results]
    truth = [{"id": i, "types": indexed[i]["types"]} for i in plan["sample_ids"]]
    return {"run_id": events[0]["hash"], "incomplete_tail": incomplete, "results": results,
            "metrics": evaluate(plan["manifest"]["categories"], truth, predictions)}


def replay(journal):
    events, _, incomplete = _read_journal(journal)
    return _report(events, incomplete)


def run_batch(plan, root, journal, executor, execution, retry_ids=(), snapshot_root=None):
    # 复制输入，阻止执行器在运行中改变已绑定的实验计划。
    plan, execution = decode(encode(plan)), decode(encode(execution))
    indexed = validate_plan(plan, execution)
    root, journal = Path(root).resolve(strict=True), Path(journal)
    sources = {}
    for identifier in plan["sample_ids"]:
        row = indexed[identifier]
        path = root / row["path"]
        if path.is_symlink() or root not in path.resolve(strict=True).parents:
            raise ValueError("源码链接或路径越界")
        with path.open("rb") as source: content = source.read(1_048_577)
        if len(content) > 1_048_576 or not content.decode("utf-8").strip() or digest(content) != row["source_hash"]:
            raise ValueError("源码无效或摘要漂移")
        sources[identifier] = content
    if plan["kb_snapshot"] is not None:
        if snapshot_root is None: raise ValueError("需提供所绑定知识快照的目录")
        snapshot = verify_snapshot(snapshot_root, plan["kb_snapshot"])
        if snapshot["manifest"] != plan["manifest"]: raise ValueError("知识快照与实验隔离清单不一致")
    retry_ids = list(retry_ids)
    if any(not isinstance(i, str) for i in retry_ids) or len(set(retry_ids)) != len(retry_ids):
        raise ValueError("重试样本无效或重复")
    expected_header = {"kind": "RUN", "plan": plan, "execution": execution}
    with exclusive_lock(str(journal) + ".lock"):
        events, end, incomplete = _read_journal(journal) if journal.exists() else ([], 0, False)
        if events:
            header, states = _state(events)
            if header != expected_header: raise ValueError("恢复绑定不符，拒绝混用计划、配置或执行产物")
        else:
            if incomplete: raise ValueError("实验头不完整；确认未执行调用后另建日志")
            states = {}
        for identifier in retry_ids:
            state = states.get(identifier)
            if state is None or (state["result"] is not None and state["result"]["status"] == "COMPLETED"):
                raise ValueError("只允许显式重试已失败或不确定的计划样本")
        with journal.open("r+b" if journal.exists() else "w+b") as output:
            if incomplete:
                output.truncate(end)
                output.flush()
                os.fsync(output.fileno())
            output.seek(0, os.SEEK_END)
            if not events:
                _append(output, events, expected_header)
                sync_directory(journal.parent)
            for identifier, state in states.items():
                if state["result"] is None:
                    result = _failure("CALL_INTERRUPTED", "UNRESOLVED")
                    _append(output, events, {"kind": "RESULT", "id": identifier, "attempt": state["attempt"], "result": result})
                    state["result"] = result
            for identifier in plan["sample_ids"]:
                if identifier in states and identifier not in retry_ids: continue
                attempt = states[identifier]["attempt"] + 1 if identifier in states else 1
                _append(output, events, {"kind": "START", "id": identifier, "attempt": attempt, "retry": identifier in retry_ids})
                try:
                    raw = executor(decode(encode(indexed[identifier])), sources[identifier])
                except Exception:
                    result = _failure("ADAPTER_ERROR")
                else:
                    result = normalize_result(raw, indexed[identifier], plan, execution)
                _append(output, events, {"kind": "RESULT", "id": identifier, "attempt": attempt, "result": result})
    return _report(events, False)
