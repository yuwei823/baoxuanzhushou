"""Resolve and hash only the distributions selected for the current platform."""

import hashlib
import subprocess
import sys
from pathlib import Path

from packaging.utils import canonicalize_name, parse_sdist_filename, parse_wheel_filename

ROOT = Path(__file__).resolve().parents[1]
resolved = ROOT / "tmp" / "requirements-resolved.txt"
wheels = ROOT / "tmp" / "lock-distributions"
wheels.mkdir(parents=True, exist_ok=True)
if "--resolved" not in sys.argv:
    subprocess.run(
        [
            sys.executable,
            "-m",
            "piptools",
            "compile",
            "--extra",
            "dev",
            "--allow-unsafe",
            "--strip-extras",
            "--output-file",
            str(resolved),
            "pyproject.toml",
            "requirements-build.in",
            "--quiet",
        ],
        cwd=ROOT,
        check=True,
    )
subprocess.run(
    [
        sys.executable,
        "-m",
        "pip",
        "download",
        "--no-deps",
        "--no-build-isolation",
        "-r",
        str(resolved),
        "-d",
        str(wheels),
    ],
    cwd=ROOT,
    check=True,
)
artifacts = {}
for path in wheels.iterdir():
    if path.suffix == ".whl":
        name, version, _, _ = parse_wheel_filename(path.name)
    else:
        name, version = parse_sdist_filename(path.name)
    artifacts[(canonicalize_name(name), str(version))] = hashlib.sha256(
        path.read_bytes()
    ).hexdigest()
lines = [
    "# Windows x64 / Python 3.11 selected distribution hashes.",
    "# Regenerate: python scripts/lock_dependencies.py",
    "# Bootstrap pip-tools first; install with --require-hashes --no-build-isolation.",
]
for line in resolved.read_text(encoding="utf-8").splitlines():
    if not line or line.startswith(("#", " ", "--")):
        continue
    name, version = line.split("==", 1)
    digest = artifacts[(canonicalize_name(name), version)]
    lines.append(f"{name}=={version} --hash=sha256:{digest}")
(ROOT / "requirements-dev.lock").write_text("\n".join(lines) + "\n", encoding="utf-8")
bootstrap = [
    line for line in lines[3:] if line.split("==")[0] in {"setuptools", "wheel", "packaging"}
]
(ROOT / "requirements-build.lock").write_text(
    "# Hashed bootstrap dependencies for source distribution builds.\n"
    + "\n".join(bootstrap)
    + "\n",
    encoding="utf-8",
)
print(f"Locked {len(lines) - 3} packages for this platform")
