from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

from _bootstrap import ROOT


EXCLUDED_NAMES = {
    ".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".venv", "venv",
    ".matplotlib",
    "archive_pre_optimization",
    "chrome-profile", "chrome-profile2",
    "torch-2.7.1+cpu-cp311-cp311-win_amd64.whl",
    "last_evaluate.log", "last_generate.log",
}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".zip"}


def included(path: Path) -> bool:
    relative = path.relative_to(ROOT)
    if relative.as_posix() == "submission/完整包_SHA256.json":
        return False
    return not any(part in EXCLUDED_NAMES for part in relative.parts) and path.suffix.lower() not in EXCLUDED_SUFFIXES


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_manifest() -> Path:
    output = ROOT / "submission" / "项目文件清单.txt"
    files = []
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or not included(path) or path == output:
            continue
        files.append(f"{path.relative_to(ROOT)}\t{path.stat().st_size} bytes")
    output.write_text(
        "AgentGuard source and artifact manifest\n\n" + "\n".join(files),
        encoding="utf-8",
    )
    return output


def main() -> None:
    output = ROOT / "AgentGuard_完整参赛项目.zip"
    write_manifest()
    files = [path for path in ROOT.rglob("*") if path.is_file() and included(path)]
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(files):
            archive.write(path, Path("AgentGuard") / path.relative_to(ROOT))
    checksums = {
        "archive": output.name,
        "sha256": sha256(output),
        "size_bytes": output.stat().st_size,
        "file_count": len(files),
    }
    checksum_path = ROOT / "submission" / "完整包_SHA256.json"
    checksum_path.write_text(json.dumps(checksums, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(checksums, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
