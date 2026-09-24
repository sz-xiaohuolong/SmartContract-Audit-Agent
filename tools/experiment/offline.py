"""离线清单与类型级评估；不调用模型，不从目录推断真值。"""
import argparse
import hashlib
import json
from pathlib import Path


def digest(data):
    return hashlib.sha256(data).hexdigest()


def inventory(root):
    root = Path(root).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("数据根路径必须是目录")
    samples, groups = [], {}
    for path in sorted(root.rglob("*.sol")):
        if path.is_symlink() or root not in path.resolve().parents:
            raise ValueError("清单不接受链接或越界源码")
        relative = path.relative_to(root).as_posix()
        source_hash = digest(path.read_bytes())
        sample_id = digest((relative + "\0" + source_hash).encode())
        groups.setdefault(source_hash, []).append(sample_id)
        samples.append({"id": sample_id, "path": relative, "source_hash": source_hash,
                        "exact_group": source_hash, "project_group": None,
                        "types": None, "split": None, "review_status": "UNREVIEWED"})
    return {"schema_version": "1", "count": len(samples), "samples": samples,
            "duplicate_groups": {k: v for k, v in groups.items() if len(v) > 1},
            "limitations": ["仅字节去重，未完成项目谱系和近似克隆审计", "标签和划分待审核"]}


def ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def scores(tp, fp, fn):
    return {"tp": tp, "fp": fp, "fn": fn, "precision": ratio(tp, tp + fp),
            "recall": ratio(tp, tp + fn), "f1": ratio(2 * tp, 2 * tp + fp + fn)}


def _rows(rows, categories, prediction=False):
    if not isinstance(rows, list):
        raise ValueError("样本必须是列表")
    indexed = {}
    for row in rows:
        expected = {"id", "types", "status"} if prediction else {"id", "types"}
        if not isinstance(row, dict) or set(row) != expected:
            raise ValueError("样本字段无效")
        identifier, types = row["id"], row["types"]
        if not isinstance(identifier, str) or not identifier.strip() or identifier in indexed:
            raise ValueError("样本 ID 为空或重复")
        if not isinstance(types, list) or any(not isinstance(t, str) or t not in categories for t in types):
            raise ValueError("漏洞类型缺失或不属于预定义类别")
        if prediction:
            if row["status"] not in ("COMPLETED", "FAILED", "UNRESOLVED"):
                raise ValueError("运行状态无效")
            if row["status"] != "COMPLETED" and types:
                raise ValueError("未完成结果不能携带已确认类型")
        indexed[identifier] = row
    return indexed


def evaluate(categories, truth, predictions):
    if (not isinstance(categories, list) or not categories
            or any(not isinstance(c, str) or not c.strip() for c in categories)
            or len(set(categories)) != len(categories)):
        raise ValueError("需提供无重复的预定义类别")
    actual = _rows(truth, categories)
    predicted = _rows(predictions, categories, prediction=True)
    if set(predicted) - set(actual):
        raise ValueError("预测包含计划外样本")
    counts = {c: [0, 0, 0] for c in categories}
    completed = failed = missing = unresolved = correct = negative = false_positive_negative = unresolved_negative = 0
    for identifier, row in actual.items():
        expected = set(row["types"])
        prediction = predicted.get(identifier)
        done = prediction is not None and prediction["status"] == "COMPLETED"
        observed = set(prediction["types"]) if done else set()
        if prediction is None:
            missing += 1
        elif prediction["status"] == "FAILED":
            failed += 1
        elif prediction["status"] == "UNRESOLVED":
            unresolved += 1
        else:
            completed += 1
            correct += int(observed == expected)
        if not expected:
            negative += 1
            false_positive_negative += int(bool(observed))
            unresolved_negative += int(not done)
        for category in categories:
            counts[category][0] += int(category in expected and category in observed)
            counts[category][1] += int(category not in expected and category in observed)
            counts[category][2] += int(category in expected and category not in observed)
    per_type = {c: scores(*values) for c, values in counts.items()}
    defined = [s["f1"] for s in per_type.values() if s["f1"] is not None]
    total = len(actual)
    return {"schema_version": "1", "planned": total, "completed": completed,
            "failed": failed, "missing": missing, "unresolved": unresolved,
            "completion_rate": ratio(completed, total), "failure_rate": ratio(failed, total),
            "missing_rate": ratio(missing, total), "unresolved_rate": ratio(unresolved, total),
            "correct_completed": correct, "correct_completed_rate": ratio(correct, total),
            "negative_samples": negative, "false_positive_negative": false_positive_negative,
            "unresolved_negative": unresolved_negative,
            "negative_false_positive_rate": ratio(false_positive_negative, negative),
            "per_type": per_type, "micro": scores(*(sum(v[i] for v in counts.values()) for i in range(3))),
            "macro_f1": ratio(sum(defined), len(categories)) if len(defined) == len(categories) else None,
            "macro_f1_defined_only": ratio(sum(defined), len(defined)),
            "macro_defined_categories": [c for c in categories if per_type[c]["f1"] is not None],
            "macro_undefined_categories": [c for c in categories if per_type[c]["f1"] is None]}


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("JSON 键重复")
        result[key] = value
    return result


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=_unique_object)


def main():
    parser = argparse.ArgumentParser(description="离线实验基础工具，不调用模型")
    commands = parser.add_subparsers(dest="command", required=True)
    scan = commands.add_parser("inventory", help="生成待审核的只读源码清单")
    scan.add_argument("--root", required=True)
    scan.add_argument("--output", required=True)
    score = commands.add_parser("evaluate", help="从已保存结果重算类型指标")
    score.add_argument("--labels", required=True, help="包含 categories 和 samples 的 JSON")
    score.add_argument("--predictions", required=True, help="预测列表 JSON")
    score.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        if args.command == "inventory":
            result = inventory(args.root)
        else:
            labels = read_json(args.labels)
            if not isinstance(labels, dict) or set(labels) != {"categories", "samples"}:
                raise ValueError("标签文件字段无效")
            result = evaluate(labels["categories"], labels["samples"], read_json(args.predictions))
        payload = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        # 先完成计算；独占创建，防止覆盖已有实验产物。
        with Path(args.output).open("x", encoding="utf-8") as output:
            output.write(payload)
    except (ValueError, OSError, TypeError, KeyError):
        parser.exit(2, "输入或输出无效：检查 JSON 契约、路径及输出文件是否已存在。\n")


if __name__ == "__main__":
    main()
