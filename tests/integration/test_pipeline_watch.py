import subprocess
import sys
import time

from insurance_audit.corpus.pipeline import REGISTRY, read, save


def test_watcher_process_detects_new_file_and_stops(tmp_path):
    (tmp_path / "法律法规").mkdir()
    save(tmp_path / "data/sources/catalog.json", {"sources": []})
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "insurance_audit.cli",
            "pipeline",
            "watch",
            "--root",
            str(tmp_path),
            "--interval",
            "1",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    try:
        deadline = time.monotonic() + 12
        while not (tmp_path / "data/runtime/pipeline-watcher.json").exists():
            assert time.monotonic() < deadline
            time.sleep(0.1)
        (tmp_path / "法律法规/新增.txt").write_text("第一条 测试条文。", encoding="utf-8")
        while not read(tmp_path / REGISTRY, {}).get("pipeline", {}).get("candidates"):
            assert time.monotonic() < deadline
            time.sleep(0.1)
        (tmp_path / "data/runtime/pipeline.stop").touch()
        assert process.wait(timeout=5) == 0
        assert read(tmp_path / "data/runtime/pipeline-health.json")["status"] == "stopped"
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        process.stderr.close()
