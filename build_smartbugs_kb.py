#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def as_list(x: Any) -> List[Any]:
    if x is None:
        return []
    if isinstance(x, list):
        return x
    return [x]


def safe_fence(code: str) -> str:
    # 防止源码里出现 ``` 导致 Markdown fence 提前结束
    max_run = 0
    for m in re.finditer(r"`+", code):
        max_run = max(max_run, len(m.group(0)))
    return "`" * max(3, max_run + 1)


def slug_filename(s: str) -> str:
    s = s.replace("\\", "/").replace("/", "_")
    s = re.sub(r"[^0-9A-Za-z._-]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s or "unknown"


def iter_entries(data: Any) -> List[Dict[str, Any]]:
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        for k in ["contracts", "data", "items", "entries"]:
            if k in data and isinstance(data[k], list):
                return [x for x in data[k] if isinstance(x, dict)]
    raise ValueError("Unrecognized JSON structure: expected list or dict-with-list.")


def extract_entry(entry: Dict[str, Any]) -> Tuple[str, str, str, str, List[int]]:
    """
    返回:
      name, rel_path, pragma, source, vuln_lines(去重排序)
    你的 JSON 结构里这些字段都存在。
    """
    name = str(entry.get("name", "")).strip()
    rel_path = str(entry.get("path", "")).strip()
    pragma = str(entry.get("pragma", "")).strip()
    source = str(entry.get("source", "")).strip()

    if not rel_path:
        raise KeyError("Missing key: path")

    vuln_lines: List[int] = []
    for v in as_list(entry.get("vulnerabilities")):
        if isinstance(v, dict) and "lines" in v:
            for ln in as_list(v.get("lines")):
                if isinstance(ln, int) and ln > 0:
                    vuln_lines.append(ln)

    vuln_lines = sorted(set(vuln_lines))
    return name, rel_path, pragma, source, vuln_lines


def extract_categories(entry: Dict[str, Any]) -> List[str]:
    cats: List[str] = []
    for v in as_list(entry.get("vulnerabilities")):
        if isinstance(v, dict) and v.get("category"):
            cats.append(str(v["category"]).strip())
    return sorted(set([c for c in cats if c]))


def build_md(dataset_name: str,
             name: str,
             rel_path: str,
             pragma: str,
             source: str,
             categories: List[str],
             vuln_lines: List[int],
             code: str) -> str:
    fence = safe_fence(code)
    primary_cat = categories[0] if categories else "Unknown"

    fm = [
        "---",
        f"Dataset: {dataset_name}",
        f"Name: {name or 'N/A'}",
        f"Category: {', '.join(categories) if categories else 'Unknown'}",
        f"Pragma: {pragma or 'N/A'}",
        f"Origin-Path: {rel_path}",
        f"Source: {source or 'N/A'}",
        f"Vulnerable-Lines: {', '.join(map(str, vuln_lines)) if vuln_lines else 'N/A'}",
        "---",
        "",
        f"# Vulnerability Reference Case: {primary_cat}",
        "",
        "## Source Code",
        f"{fence}solidity",
        code.rstrip(),
        fence,
        "",
    ]
    return "\n".join(fm)


def main():
    parser = argparse.ArgumentParser(description="Build SmartBugs Curated Markdown KB from vulnerabilities.json")
    parser.add_argument("--repo-dir", required=True, help="smartbugs-curated 仓库根目录（包含 dataset/ 的那个目录）")
    parser.add_argument("--json", required=True, help="vulnerabilities.json 的路径（相对 repo-dir 或绝对路径）")
    parser.add_argument("--out", required=True, help="输出目录，例如 ./src/main/resources/document/smartbugs_kb")
    parser.add_argument("--dataset-name", default="smartbugs-curated")
    parser.add_argument("--limit", type=int, default=0, help="只处理前 N 条（0=全量）")
    parser.add_argument("--dry-run", action="store_true", help="只打印不写文件")
    args = parser.parse_args()

    repo_dir = Path(args.repo_dir).resolve()
    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    json_path = Path(args.json)
    if not json_path.is_absolute():
        json_path = (repo_dir / json_path).resolve()

    print(f"[INFO] repo_dir = {repo_dir}")
    print(f"[INFO] json_path = {json_path}")
    print(f"[INFO] out_dir  = {out_dir}")
    print(f"[INFO] dry_run  = {args.dry_run}")
    print(f"[INFO] limit    = {args.limit if args.limit > 0 else 'no limit'}")

    if not repo_dir.exists():
        print(f"[ERRO] repo_dir not exists: {repo_dir}", file=sys.stderr)
        sys.exit(1)
    if not json_path.exists():
        print(f"[ERRO] json_path not exists: {json_path}", file=sys.stderr)
        sys.exit(1)

    # 关键检查：repo_dir 下必须有 dataset/
    if not (repo_dir / "dataset").exists():
        print(f"[WARN] repo_dir 下找不到 dataset/：{repo_dir / 'dataset'}")
        print("[WARN] 你很可能把 --repo-dir 指到了错误目录（应指向 smartbugs-curated 仓库根目录）")

    data = json.loads(json_path.read_text(encoding="utf-8"))
    entries = iter_entries(data)
    total = len(entries)
    print(f"[INFO] loaded entries = {total}")

    success = 0
    skipped = 0
    missing_sources: List[str] = []

    for idx, entry in enumerate(entries, start=1):
        if args.limit > 0 and idx > args.limit:
            break

        print(f"\n[INFO] ===== [{idx}/{total}] =====")

        try:
            name, rel_path, pragma, source, vuln_lines = extract_entry(entry)
            categories = extract_categories(entry)
        except Exception as e:
            skipped += 1
            print(f"[SKIP] metadata parse failed: {e}")
            continue

        sol_path = (repo_dir / rel_path).resolve()
        print(f"[INFO] rel_path  = {rel_path}")
        print(f"[INFO] sol_path  = {sol_path}")
        print(f"[INFO] category  = {categories if categories else ['Unknown']}")
        print(f"[INFO] lines     = {vuln_lines if vuln_lines else ['N/A']}")

        if not sol_path.exists():
            skipped += 1
            missing_sources.append(rel_path)
            print(f"[SKIP] source not found: {sol_path}")
            continue

        code = sol_path.read_text(encoding="utf-8", errors="ignore")

        h = hashlib.sha1(rel_path.encode("utf-8")).hexdigest()[:10]
        prefix = slug_filename(categories[0]) if categories else "Unknown"
        base = slug_filename(rel_path.replace(".sol", ""))
        out_file = out_dir / f"{prefix}__{base}__{h}.md"

        md = build_md(args.dataset_name, name, rel_path, pragma, source, categories, vuln_lines, code)

        print(f"[INFO] out_file  = {out_file}")

        if args.dry_run:
            print("[OK  ] dry-run: not writing.")
            success += 1
        else:
            out_file.write_text(md, encoding="utf-8")
            print(f"[OK  ] written bytes = {out_file.stat().st_size}")
            success += 1

    print("\n========== SUMMARY ==========")
    print(f"[INFO] success = {success}")
    print(f"[INFO] skipped = {skipped}")
    print(f"[INFO] out_dir = {out_dir}")

    if missing_sources:
        print("\n[WARN] source not found (showing up to 20):")
        for p in missing_sources[:20]:
            print(f"  - {p}")


if __name__ == "__main__":
    main()
