"""Run the EXE from a relocated Unicode path, with no developer tools in PATH."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


def check_packaged_app(executable, report_path):
    executable, report_path = Path(executable).resolve(), Path(report_path).resolve()
    report_path.unlink(missing_ok=True)
    with tempfile.TemporaryDirectory(prefix="aura_portable_") as temporary:
        root = Path(temporary)
        app_dir = root / "Перенесённое приложение с пробелами"
        if (executable.parent / "build-manifest.json").is_file() or executable.parent.name == "AuraDownloader":
            shutil.copytree(executable.parent, app_dir)
        else:
            app_dir.mkdir()
            shutil.copy2(executable, app_dir / executable.name)
        environment = os.environ.copy()
        environment["PATH"] = str(Path(os.environ["SystemRoot"]) / "System32")
        for name in ("PYTHONPATH", "PYTHONHOME", "QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH", "VIRTUAL_ENV"):
            environment.pop(name, None)
        result = subprocess.run([str(app_dir / executable.name), "--smoke-test", str(report_path)],
                                cwd=root, env=environment, timeout=180, creationflags=0x08000000)
        if result.returncode or not report_path.is_file():
            details = report_path.read_text(encoding="utf-8") if report_path.is_file() else "No diagnostic report produced."
            raise RuntimeError(f"Packaged application check failed ({result.returncode}): {details}")
        report = json.loads(report_path.read_text(encoding="utf-8"))
        if not report.get("ok") or not report.get("frozen"):
            raise RuntimeError("Smoke report did not confirm a working frozen application.")
        print(f"Packaged EXE passed {len(report['checks'])} checks with isolated PATH/profile.")
        return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("executable", type=Path)
    parser.add_argument("--report", type=Path, default=Path("dist/smoke-report.json"))
    args = parser.parse_args()
    check_packaged_app(args.executable, args.report)
