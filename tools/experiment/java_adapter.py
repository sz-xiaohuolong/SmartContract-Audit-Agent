"""冻结配置和 JAR 后显式调用 S0 CLI；测试可注入本地可执行夹具。"""
import os
import shutil
import signal
import subprocess
import tempfile
from pathlib import Path
from offline import digest
from storage import decode, durable_write, fingerprint


class JavaExecutor:
    def __init__(self, jar, config, provider, timeout=660, java="java"):
        executable = shutil.which(java)
        if executable is None: raise ValueError("找不到 Java 可执行文件")
        self.java = str(Path(executable).resolve(strict=True))
        self.jar = Path(jar).read_bytes()
        self.config = Path(config).read_bytes()
        self.provider, self.timeout = provider, timeout
        # 同时绑定批处理规范化代码与 Java CLI，升级任一侧都不能混入旧运行。
        here = Path(__file__).parent
        implementation = {p.name: digest(p.read_bytes()) for p in sorted(here.glob("*.py"))}
        self.execution = {"config_hash": digest(self.config), "artifact_hash": fingerprint({
            "jar": digest(self.jar), "java": digest(Path(self.java).read_bytes()), "runner": implementation}),
            "provider": provider, "timeout_seconds": timeout}

    def __call__(self, row, source):
        with tempfile.TemporaryDirectory(prefix="s1b-call-") as directory:
            root = Path(directory)
            for name, content in [("audit.jar", self.jar), ("providers.properties", self.config), ("source.sol", source)]:
                durable_write(root / name, content)
            with (root / "stdout.json").open("w+b") as output:
                process = subprocess.Popen([self.java, "-jar", str(root / "audit.jar"),
                                            "--source", str(root / "source.sol"),
                                            "--config", str(root / "providers.properties"), "--provider", self.provider],
                                           stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.DEVNULL,
                                           start_new_session=True)
                try: returncode = process.wait(timeout=self.timeout)
                except BaseException:
                    try: os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError: pass
                    process.wait()
                    raise
                if returncode not in (0, 1): raise ValueError("审计进程未生成结果")
                output.seek(0)
                data = output.read(1_048_577)
                if len(data) > 1_048_576: raise ValueError("审计输出超出上限")
                result = decode(data)
                if not isinstance(result, dict) or result.get("status") != ("COMPLETED" if returncode == 0 else "FAILED"):
                    raise ValueError("审计退出码与状态不一致")
                return result
