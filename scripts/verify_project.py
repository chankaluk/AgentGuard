from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path

from _bootstrap import ROOT
from office_hygiene import office_authors


REQUIRED_FILES = (
    "README.md",
    "requirements.txt",
    "setup_env.ps1",
    "setup_env.sh",
    "run_all.ps1",
    "run_all.sh",
    "run_demo.ps1",
    "run_demo.sh",
    "configs/default.json",
    "src/agentguard/baselines.py",
    "src/agentguard/data.py",
    "src/agentguard/engine.py",
    "src/agentguard/model.py",
    "src/agentguard/schema.py",
    "src/agentguard/synthetic.py",
    "scripts/build_report_from_template.py",
    "scripts/generate_demo_data.py",
    "scripts/collect_local_normal.py",
    "scripts/generate_controlled_security_logs.py",
    "scripts/convert_loghub_hdfs.py",
    "scripts/summarize_supplemental_inputs.py",
    "scripts/train.py",
    "scripts/evaluate.py",
    "scripts/evaluate_baselines.py",
    "scripts/generate_submission_docs.py",
    "scripts/office_hygiene.py",
    "scripts/package_project.py",
    "docs/01_比赛要求逐条剖析.md",
    "docs/02_系统设计说明书.md",
    "docs/03_数据接入与真实验证指南.md",
    "docs/05_作品报告正文.md",
    "docs/09_模型权重与依赖说明.md",
    "docs/10_前沿方案对照与补强路线.md",
    "docs/11_评委通俗讲解稿.md",
    "docs/12_三类真实补充数据输入输出说明.md",
    "configs/otel_span_mapping.example.json",
    "configs/osquery_process_mapping.example.json",
    "configs/wazuh_alert_mapping.example.json",
    "PROJECT_HANDOFF.md",
    "tests/test_core.py",
    "tests/test_project_integrity.py",
    "tests/test_submission_quality.py",
    "web/index.html",
)

DELIVERABLE_FILES = (
    "submission/作品报告_AgentGuard_自主命题模板版.docx",
    "submission/系统使用说明_AgentGuard.docx",
    "submission/作品原创性声明_待签字盖章.docx",
    "submission/最终提交清单.md",
)

JSON_FILES = (
    "configs/default.json",
    "configs/otel_span_mapping.example.json",
    "configs/osquery_process_mapping.example.json",
    "configs/wazuh_alert_mapping.example.json",
    "data/demo/metadata.json",
    "artifacts/training_result.json",
    "artifacts/evaluation/metrics.json",
    "artifacts/evaluation/baselines.json",
    "submission/材料生成说明.json",
)

BANNED_CLAIMS = (
    "本项目对应官方定向式",
    "定向式专项命题（题目3）",
    "组委会正式数据指标",
    "官方数据到手后",
    "为官方 20% 上限",
)

EXACT_REQUIREMENTS = {
    "numpy": "2.5.1",
    "torch": "2.13.0",
    "python-docx": "1.2.0",
    "python-pptx": "1.0.2",
    "matplotlib": "3.11.1",
    "psutil": "7.2.2",
    "requests": "2.34.2",
}


def check_required_files(root: Path, *, include_deliverables: bool = False) -> list[str]:
    """返回缺失的项目相对路径。"""

    required = REQUIRED_FILES + (DELIVERABLE_FILES if include_deliverables else ())
    return [relative for relative in required if not (root / relative).is_file()]


def check_json_files(root: Path) -> list[str]:
    errors = []
    for relative in JSON_FILES:
        path = root / relative
        if not path.is_file():
            errors.append(f"JSON 缺失：{relative}")
            continue
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            errors.append(f"JSON 无法解析：{relative}（{exc}）")
    return errors


def check_office_containers(root: Path) -> list[str]:
    errors = []
    for relative in DELIVERABLE_FILES:
        path = root / relative
        if path.suffix.lower() not in {".docx", ".pptx"} or not path.exists():
            continue
        if not zipfile.is_zipfile(path):
            errors.append(f"Office 文件不是有效 ZIP 容器：{relative}")
            continue
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
        required_part = "word/document.xml" if path.suffix.lower() == ".docx" else "ppt/presentation.xml"
        if required_part not in names:
            errors.append(f"Office 文件缺少核心部件 {required_part}：{relative}")
    return errors


def check_exact_requirements(root: Path) -> list[str]:
    path = root / "requirements.txt"
    actual = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "==" in line:
            name, version = line.split("==", 1)
            actual[name] = version
    return [
        f"依赖版本未精确固定：{name}=={version}"
        for name, version in EXACT_REQUIREMENTS.items()
        if actual.get(name) != version
    ]


def check_submission_quality(root: Path) -> list[str]:
    errors = []
    office_paths = (
        root / "submission" / "作品报告_AgentGuard_自主命题模板版.docx",
        root / "submission" / "系统使用说明_AgentGuard.docx",
        root / "submission" / "作品原创性声明_待签字盖章.docx",
        root / "submission" / "答辩PPT_AgentGuard_自主命题最终版.pptx",
    )
    for path in office_paths:
        if path.is_file() and office_authors(path) != ("", ""):
            errors.append(f"Office 作者元数据未清空：{path.relative_to(root)}")

    report = office_paths[0]
    if report.is_file() and zipfile.is_zipfile(report):
        with zipfile.ZipFile(report) as archive:
            document_xml = archive.read("word/document.xml").decode("utf-8")
            footer_xml = "".join(
                archive.read(name).decode("utf-8")
                for name in archive.namelist()
                if name.startswith("word/footer") and name.endswith(".xml")
            )
        if "填写说明" in document_xml:
            errors.append("作品报告仍包含填写说明页")
        if "共 7页" in footer_xml or "共7页" in footer_xml:
            errors.append("作品报告页脚仍含固定总页数 7")
        if "PAGE" not in footer_xml or "NUMPAGES" not in footer_xml:
            errors.append("作品报告页脚缺少 PAGE/NUMPAGES 动态域")

    guide = office_paths[1]
    if guide.is_file() and zipfile.is_zipfile(guide):
        with zipfile.ZipFile(guide) as archive:
            media = [name for name in archive.namelist() if name.startswith("word/media/")]
            guide_xml = archive.read("word/document.xml").decode("utf-8")
        if len(media) < 4:
            errors.append(f"系统使用说明界面证据不足：仅 {len(media)} 幅图片")
        for phrase in ("系统启动与主界面", "日志输入示例", "告警结果页面", "模型分、规则分与证据链"):
            if phrase not in guide_xml:
                errors.append(f"系统使用说明缺少章节：{phrase}")
    return errors


def scan_track_claims(root: Path) -> list[str]:
    errors = []
    paths = [root / "README.md", *sorted((root / "docs").glob("0[1-8]_*.md"))]
    for path in paths:
        text = path.read_text(encoding="utf-8")
        for phrase in BANNED_CLAIMS:
            if phrase in text:
                errors.append(f"错误赛道口径：{path.relative_to(root)} -> {phrase}")
    return errors


def check_sensitive_filenames(root: Path) -> list[str]:
    risky = []
    name_pattern = re.compile(r"^(?:\.env(?:\..+)?|.*\.(?:pem|key|p12|pfx)|cookies?\.txt)$", re.I)
    for path in root.rglob("*"):
        if path.is_file() and ".venv" not in path.parts and name_pattern.match(path.name):
            risky.append(f"疑似敏感文件：{path.relative_to(root)}")
    return risky


def verify(root: Path, *, include_deliverables: bool = True) -> dict:
    missing = check_required_files(root, include_deliverables=include_deliverables)
    errors = [f"文件缺失：{relative}" for relative in missing]
    errors.extend(check_json_files(root))
    errors.extend(check_office_containers(root))
    errors.extend(check_exact_requirements(root))
    errors.extend(check_submission_quality(root))
    errors.extend(scan_track_claims(root))
    errors.extend(check_sensitive_filenames(root))
    return {
        "status": "pass" if not errors else "fail",
        "required_file_count": len(REQUIRED_FILES)
        + (len(DELIVERABLE_FILES) if include_deliverables else 0),
        "errors": errors,
    }


def main() -> None:
    result = verify(ROOT, include_deliverables=True)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
