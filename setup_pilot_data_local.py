import os
import shutil
import random

# ================= 路径配置 (请根据你的实际情况修改) =================
# 1. 你刚刚 clone 下来的 SolidiFI 仓库路径
SOURCE_ROOT = "./SolidiFI-benchmark/buggy_contracts"

# 2. 你的 Java 项目测试资源目录 (请修改为你的实际绝对路径或相对路径)
# 假设你的 Java 项目文件夹叫 SmartContract-Audit-Agent
TARGET_DIR = "./src/main/resources/testset/pilot_set"
# ===================================================================

def setup_data():
    if not os.path.exists(SOURCE_ROOT):
        print(f"❌ 错误: 找不到 SolidiFI 目录: {SOURCE_ROOT}")
        return

    # 清理并重建目标目录
    if os.path.exists(TARGET_DIR):
        shutil.rmtree(TARGET_DIR)
    os.makedirs(TARGET_DIR)

    # 想要覆盖的漏洞类型 (SolidiFI 的文件夹名称)
    VULN_TYPES = [
        "Re-entrancy",
        "Overflow-Underflow",
        "Timestamp-Dependency",
        "Unhandled-Exceptions",
        "Unchecked-Send",
        "TOD",
        "tx.origin",
    ]

    print(f"🚀 开始构建 Pilot 数据集...")
    print(f"源目录: {SOURCE_ROOT}")
    print(f"目标目录: {TARGET_DIR}")

    total_count = 0
    for v_type in VULN_TYPES:
        src_folder = os.path.join(SOURCE_ROOT, v_type)
        if not os.path.exists(src_folder):
            print(f"⚠️ 跳过: 找不到分类文件夹 {v_type}")
            continue

        # 获取该分类下所有 .sol 文件
        files = [f for f in os.listdir(src_folder) if f.endswith(".sol")]

        # 每个分类随机取 2 个
        selected = random.sample(files, min(len(files), 2))

        for f in selected:
            src_file = os.path.join(src_folder, f)
            # 重命名文件，带上漏洞类型前缀，方便我们在 Java 实验中统计
            new_name = f"{v_type}_{f}"
            dst_file = os.path.join(TARGET_DIR, new_name)

            shutil.copy(src_file, dst_file)
            print(f"✅ 已复制: {new_name}")
            total_count += 1

    print(f"\n🎉 成功！共准备了 {total_count} 个测试合约。")
    print("现在你可以运行 Java 的 PilotExperimentTest 了。")

if __name__ == "__main__":
    setup_data()