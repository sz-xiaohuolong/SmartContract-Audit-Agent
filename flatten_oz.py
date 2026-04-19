#!/usr/bin/env python3
"""
flatten_oz.py — 纯 Python Solidity 展平工具
无需 Hardhat / Node 版本兼容，直接解析 import 递归拼接

用法：
    python3 flatten_oz.py

前提：
    oz_flatten_workspace/node_modules/@openzeppelin/contracts 已存在
    （已经通过 npm install @openzeppelin/contracts 安装）

输出：
    safe_contracts/safe_01_ERC20.sol 等 50 份展平合约

样本配比说明：
    - 正样本：7 类漏洞 × 50 = 350 份
    - 负样本：50 份（与每类正样本数量对齐）
    - 总样本：400 份
"""

import os
import re
import sys
from pathlib import Path

# ─── 路径配置 ───────────────────────────────────────────────────
SCRIPT_DIR   = Path(__file__).parent.resolve()
WORK_DIR     = SCRIPT_DIR / "oz_flatten_workspace"
NODE_MODULES = WORK_DIR / "node_modules"
OUTPUT_DIR   = SCRIPT_DIR / "safe_contracts"

# 预期输出的负样本数量
EXPECTED_SAFE_CONTRACTS = 50

# ─── 待展平合约：(输出文件名, OZ包内路径) ───────────────────────
# 目标：生成 50 份安全合约作为负样本，与每类漏洞 50 份正样本对齐
CONTRACTS = [
    # === ERC20 系列 (10份) ===
    ("safe_01_ERC20.sol",              "token/ERC20/ERC20.sol"),
    ("safe_02_ERC20Burnable.sol",      "token/ERC20/extensions/ERC20Burnable.sol"),
    ("safe_03_ERC20Capped.sol",        "token/ERC20/extensions/ERC20Capped.sol"),
    ("safe_04_ERC20Pausable.sol",      "token/ERC20/extensions/ERC20Pausable.sol"),
    ("safe_05_ERC20Votes.sol",         "token/ERC20/extensions/ERC20Votes.sol"),
    ("safe_06_ERC20FlashMint.sol",     "token/ERC20/extensions/ERC20FlashMint.sol"),
    ("safe_07_ERC20Wrapper.sol",       "token/ERC20/extensions/ERC20Wrapper.sol"),
    ("safe_08_ERC4626.sol",            "token/ERC20/extensions/ERC4626.sol"),
    ("safe_09_IERC20.sol",             "token/ERC20/IERC20.sol"),
    ("safe_10_ERC20Permit.sol",        "token/ERC20/extensions/ERC20Permit.sol"),

    # === ERC721 系列 (8份) ===
    ("safe_11_ERC721.sol",             "token/ERC721/ERC721.sol"),
    ("safe_12_ERC721Burnable.sol",     "token/ERC721/extensions/ERC721Burnable.sol"),
    ("safe_13_ERC721Pausable.sol",     "token/ERC721/extensions/ERC721Pausable.sol"),
    ("safe_14_ERC721URIStorage.sol",   "token/ERC721/extensions/ERC721URIStorage.sol"),
    ("safe_15_ERC721Enumerable.sol",   "token/ERC721/extensions/ERC721Enumerable.sol"),
    ("safe_16_ERC721Royalty.sol",      "token/ERC721/extensions/ERC721Royalty.sol"),
    ("safe_17_ERC721Consecutive.sol",  "token/ERC721/extensions/ERC721Consecutive.sol"),
    ("safe_18_IERC721.sol",            "token/ERC721/IERC721.sol"),

    # === ERC1155 系列 (4份) ===
    ("safe_19_ERC1155.sol",            "token/ERC1155/ERC1155.sol"),
    ("safe_20_ERC1155Burnable.sol",    "token/ERC1155/extensions/ERC1155Burnable.sol"),
    ("safe_21_ERC1155Pausable.sol",    "token/ERC1155/extensions/ERC1155Pausable.sol"),
    ("safe_22_ERC1155Supply.sol",      "token/ERC1155/extensions/ERC1155Supply.sol"),

    # === Access Control 系列 (6份) ===
    ("safe_23_Ownable.sol",            "access/Ownable.sol"),
    ("safe_24_Ownable2Step.sol",       "access/Ownable2Step.sol"),
    ("safe_25_AccessControl.sol",      "access/AccessControl.sol"),
    ("safe_26_IAccessControl.sol",     "access/IAccessControl.sol"),
    ("safe_27_AccessControlDefaultAdminRules.sol", "access/extensions/AccessControlDefaultAdminRules.sol"),
    ("safe_28_AccessControlEnumerable.sol", "access/extensions/AccessControlEnumerable.sol"),

    # === Security Utils 系列 (8份) ===
    ("safe_29_ReentrancyGuard.sol",    "utils/ReentrancyGuard.sol"),
    ("safe_30_Pausable.sol",           "utils/Pausable.sol"),
    ("safe_31_Address.sol",            "utils/Address.sol"),
    ("safe_32_Multicall.sol",          "utils/Multicall.sol"),
    ("safe_33_Context.sol",            "utils/Context.sol"),
    ("safe_34_ShortStrings.sol",       "utils/ShortStrings.sol"),
    ("safe_35_EIP712.sol",             "utils/cryptography/EIP712.sol"),
    ("safe_36_ECDSA.sol",              "utils/cryptography/ECDSA.sol"),

    # === Governance 系列 (6份) ===
    ("safe_37_Governor.sol",           "governance/Governor.sol"),
    ("safe_38_TimelockController.sol", "governance/TimelockController.sol"),
    ("safe_39_GovernorCountingSimple.sol", "governance/extensions/GovernorCountingSimple.sol"),
    ("safe_40_GovernorVotes.sol",      "governance/extensions/GovernorVotes.sol"),
    ("safe_41_GovernorTimelockControl.sol", "governance/extensions/GovernorTimelockControl.sol"),
    ("safe_42_Votes.sol",              "governance/utils/Votes.sol"),

    # === Finance / Access Manager 系列 (4份) ===
    ("safe_43_VestingWalletCliff.sol", "finance/VestingWalletCliff.sol"),
    ("safe_44_VestingWallet.sol",      "finance/VestingWallet.sol"),
    ("safe_45_AccessManaged.sol",      "access/manager/AccessManaged.sol"),
    ("safe_46_AccessManager.sol",      "access/manager/AccessManager.sol"),

    # === Proxy 系列 (4份) ===
    ("safe_47_Erc1967Proxy.sol",       "proxy/ERC1967/ERC1967Proxy.sol"),
    ("safe_48_TransparentUpgradeableProxy.sol", "proxy/transparent/TransparentUpgradeableProxy.sol"),
    ("safe_49_ProxyAdmin.sol",         "proxy/transparent/ProxyAdmin.sol"),
    ("safe_50_UUPSUpgradeable.sol",    "proxy/utils/UUPSUpgradeable.sol"),
]

# ─── 颜色输出 ────────────────────────────────────────────────────
def green(s):  return f"\033[92m{s}\033[0m"
def red(s):    return f"\033[91m{s}\033[0m"
def yellow(s): return f"\033[93m{s}\033[0m"
def blue(s):   return f"\033[94m{s}\033[0m"

# ─── 核心展平器 ──────────────────────────────────────────────────
class Flattener:
    """
    递归解析 Solidity import，将所有依赖拼接为单一文件。
    支持格式：
        import "...";
        import '...';
        import {...} from "...";
        import * as X from "...";
    """

    # 匹配 import 语句，提取路径
    IMPORT_RE = re.compile(
        r"""^\s*import\s+(?:[^"']*?from\s+)?['"]([^'"]+)['"]\s*;""",
        re.MULTILINE
    )

    def __init__(self, node_modules: Path):
        self.node_modules = node_modules
        self.visited: set[Path] = set()   # 已处理文件，避免重复
        self.collected: list[str] = []    # 按顺序收集的代码块

    def resolve_path(self, import_str: str, current_file: Path) -> Path | None:
        """
        解析 import 路径为绝对路径。
        支持：
          - @openzeppelin/contracts/...  → node_modules 下
          - ./relative  ../relative      → 相对当前文件
        """
        if import_str.startswith("@") or not import_str.startswith("."):
            # 包路径
            resolved = self.node_modules / import_str
        else:
            # 相对路径
            resolved = (current_file.parent / import_str).resolve()

        return resolved if resolved.exists() else None

    def flatten_file(self, file_path: Path) -> None:
        """递归展平单个文件"""
        abs_path = file_path.resolve()

        # 避免重复处理
        if abs_path in self.visited:
            return
        self.visited.add(abs_path)

        try:
            source = abs_path.read_text(encoding="utf-8")
        except Exception as e:
            print(red(f"    [读取失败] {abs_path}: {e}"))
            return

        # 先递归处理所有 import
        for match in self.IMPORT_RE.finditer(source):
            import_str = match.group(1)
            resolved = self.resolve_path(import_str, abs_path)
            if resolved:
                self.flatten_file(resolved)
            else:
                print(yellow(f"    [WARN] 无法解析 import: {import_str}"))

        # 去掉本文件中的 import 行，只保留真正的代码
        lines = source.splitlines(keepends=True)
        code_lines = []
        for line in lines:
            if self.IMPORT_RE.match(line):
                continue   # 跳过 import 行（依赖已被递归拼进来了）
            code_lines.append(line)

        # 收集代码块，加上文件来源注释
        block = (
                f"\n// ====== Source: {abs_path.name} ======\n"
                + "".join(code_lines).strip()
                + "\n"
        )
        self.collected.append(block)

    def get_result(self, original_source: Path) -> str:
        """
        组合最终输出：
          - 第一行：SPDX
          - 第二行：pragma（从原始入口文件提取）
          - 后续：所有依赖代码（去重后）
        """
        # 提取入口文件的 pragma
        src = original_source.read_text(encoding="utf-8")
        pragma_match = re.search(r"^pragma solidity[^;]+;", src, re.MULTILINE)
        pragma = pragma_match.group(0) if pragma_match else "pragma solidity ^0.8.20;"

        header = (
            "// SPDX-License-Identifier: MIT\n"
            f"{pragma}\n\n"
            f"// Flattened by flatten_oz.py\n"
            f"// Source: @openzeppelin/contracts\n\n"
        )

        # 去掉各 block 里重复的 SPDX 和 pragma
        body_parts = []
        for block in self.collected:
            cleaned_lines = []
            for line in block.splitlines(keepends=True):
                s = line.strip()
                if s.startswith("// SPDX-License-Identifier"):
                    continue
                if re.match(r"^pragma solidity", s):
                    continue
                cleaned_lines.append(line)
            body_parts.append("".join(cleaned_lines))

        return header + "\n".join(body_parts)


# ─── 主流程 ─────────────────────────────────────────────────────
def main():
    print()
    print("╔══════════════════════════════════════════════════════════╗")
    print("║     OpenZeppelin 合约展平工具 (纯 Python 版)             ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print()

    # 检查 node_modules
    oz_base = NODE_MODULES / "@openzeppelin" / "contracts"
    if not oz_base.exists():
        print(red(f"[ERROR] 未找到 @openzeppelin/contracts"))
        print(f"  请先在 {WORK_DIR} 目录下执行：")
        print(f"  npm install @openzeppelin/contracts")
        sys.exit(1)

    # 读取 OZ 版本
    pkg_json = oz_base / "package.json"
    if pkg_json.exists():
        import json
        ver = json.loads(pkg_json.read_text())["version"]
        print(blue(f"[INFO]  @openzeppelin/contracts 版本: {ver}"))

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    # 清理旧的展平结果，避免历史残留样本混入当前实验
    old_outputs = list(OUTPUT_DIR.glob("*.sol"))
    for old_file in old_outputs:
        old_file.unlink()
    print(blue(f"[INFO]  输出目录: {OUTPUT_DIR}"))
    print(blue(f"[INFO]  已清理旧样本: {len(old_outputs)} 份"))
    print()

    success, fail = 0, []

    for output_name, oz_path in CONTRACTS:
        source_path = oz_base / oz_path
        output_path = OUTPUT_DIR / output_name

        label = f"@openzeppelin/contracts/{oz_path}"
        print(f"  {label:<50s} → {output_name:<35s}", end="", flush=True)

        if not source_path.exists():
            print(red("[失败: 源文件不存在]"))
            fail.append(f"{output_name} (源文件不存在)")
            continue

        try:
            flattener = Flattener(NODE_MODULES)
            flattener.flatten_file(source_path)
            result = flattener.get_result(source_path)

            output_path.write_text(result, encoding="utf-8")
            line_count = result.count("\n")
            file_count = len(flattener.visited)
            print(green(f"[OK  {line_count:4d} lines, {file_count} files merged]"))
            success += 1

        except Exception as e:
            print(red(f"[异常: {e}]"))
            fail.append(f"{output_name}: {e}")

    # ─── 汇总 ───
    print()
    print("══════════════════════════════════════════")
    print(f"  {green(f'✅ 成功: {success} 份')}")
    if fail:
        print(f"  {red(f'❌ 失败: {len(fail)} 份')}")
        for f in fail:
            print(f"     • {f}")
    print()
    print(f"  📊 实验数据集配比：")
    print(f"     • 正样本：7 类 × 50 = 350 份")
    print(f"     • 负样本：{success} 份（目标 {EXPECTED_SAFE_CONTRACTS} 份）")
    print(f"     • 总计  ：{350 + success} 份")
    print()

    if success != EXPECTED_SAFE_CONTRACTS:
        print(yellow(
            f"[WARN] 负样本数量与预期不一致：期望 {EXPECTED_SAFE_CONTRACTS}，实际 {success}。"
            " 请检查 OpenZeppelin 版本或失效的合约路径。"
        ))
        print()

    if success > 0:
        print(green(f"展平合约已保存至: {OUTPUT_DIR}/"))
        print()
        for f in sorted(OUTPUT_DIR.glob("*.sol")):
            size = f.stat().st_size // 1024
            print(f"  {f.name:<40s}  {size:4d} KB")
        print()
        print("╔══════════════════════════════════════════════════════════╗")
        print("║  下一步：复制到项目目录                                  ║")
        print("║                                                          ║")
        print(f"║  cp -r {OUTPUT_DIR}/          ")
        print("║    <project>/src/main/resources/testset/safe_contracts/  ║")
        print("╚══════════════════════════════════════════════════════════╝")


if __name__ == "__main__":
    main()
