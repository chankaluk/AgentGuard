from __future__ import annotations

import importlib.util
import re
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))


def load_package_module():
    path = SCRIPTS / "package_project.py"
    spec = importlib.util.spec_from_file_location("agentguard_package_project", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载打包模块：{path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_verify_module():
    path = SCRIPTS / "verify_project.py"
    spec = importlib.util.spec_from_file_location("agentguard_verify_project", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载验收模块：{path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ProjectIntegrityTests(unittest.TestCase):
    def test_report_markdown_is_present_and_included(self):
        report_source = ROOT / "docs" / "05_作品报告正文.md"
        self.assertTrue(report_source.exists(), "作品报告 Markdown 源文件缺失")
        package_module = load_package_module()
        self.assertTrue(
            package_module.included(report_source),
            "作品报告 Markdown 被打包规则排除",
        )

    def test_package_manifest_includes_cross_platform_launchers(self):
        package_module = load_package_module()
        manifest = package_module.write_manifest().read_text(encoding="utf-8")
        for name in ("setup_env.ps1", "setup_env.sh", "run_all.ps1", "run_all.sh", "run_demo.ps1", "run_demo.sh"):
            self.assertIn(name, manifest)

    def test_run_all_uses_checked_python_and_never_installs_dependencies(self):
        script = (ROOT / "run_all.ps1").read_text(encoding="utf-8")
        self.assertIn("function Invoke-PythonChecked", script)
        self.assertIn("$PythonExecutable", script)
        self.assertIn("$LASTEXITCODE", script)
        self.assertNotIn("pip install", script)

        shell_script = (ROOT / "run_all.sh").read_text(encoding="utf-8")
        self.assertIn('"$PYTHON_BIN"', shell_script)
        self.assertNotIn("pip install", shell_script)

    def test_posix_launchers_support_python3_and_project_venv(self):
        for name in ("setup_env.sh", "run_all.sh", "run_demo.sh"):
            script = (ROOT / name).read_text(encoding="utf-8")
            self.assertTrue(script.startswith("#!/usr/bin/env bash"), name)
            self.assertIn(".venv/bin/python", script, name)
            self.assertIn("python3", script, name)

    def test_required_project_files_are_present(self):
        verify_module = load_verify_module()
        self.assertEqual(verify_module.check_required_files(ROOT), [])

    def test_json_office_and_track_checks_pass_before_final_ppt_gate(self):
        verify_module = load_verify_module()
        self.assertEqual(verify_module.check_json_files(ROOT), [])
        self.assertEqual(verify_module.check_office_containers(ROOT), [])
        self.assertEqual(verify_module.scan_track_claims(ROOT), [])

    def test_pre_optimization_archive_is_never_packaged(self):
        package_module = load_package_module()
        archived = ROOT / "archive_pre_optimization" / "答辩PPT_AgentGuard.pptx"
        self.assertFalse(package_module.included(archived))

    def test_internal_plan_notes_are_not_packaged(self):
        package_module = load_package_module()
        plan = ROOT / "docs" / "superpowers" / "plans" / "2026-07-20-agentguard-autonomous-track-optimization.md"
        self.assertIn("superpowers", package_module.EXCLUDED_NAMES)
        self.assertFalse(package_module.included(plan))

    def test_requirements_use_exact_versions(self):
        lines = [
            line.strip()
            for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        self.assertGreaterEqual(len(lines), 7)
        for line in lines:
            self.assertRegex(
                line,
                r"^[A-Za-z0-9_.-]+==[A-Za-z0-9_.+-]+$",
                f"依赖没有精确固定：{line}",
            )

    def test_model_provenance_and_new_session_handoff_are_present(self):
        model_doc = ROOT / "docs" / "09_模型权重与依赖说明.md"
        handoff = ROOT / "PROJECT_HANDOFF.md"
        self.assertTrue(model_doc.is_file(), "缺少模型权重与依赖说明")
        self.assertTrue(handoff.is_file(), "缺少新会话交接与重新部署文档")
        model_text = model_doc.read_text(encoding="utf-8")
        for phrase in ("本地训练生成", "未使用第三方预训练权重", "SHA-256"):
            self.assertIn(phrase, model_text)
        handoff_text = handoff.read_text(encoding="utf-8")
        for phrase in ("从零部署", "当前指标", "已知限制", "新聊天"):
            self.assertIn(phrase, handoff_text)


if __name__ == "__main__":
    unittest.main()
