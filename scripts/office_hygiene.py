from __future__ import annotations

import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


CORE_TAGS = (
    "{http://purl.org/dc/elements/1.1/}creator",
    "{http://schemas.openxmlformats.org/package/2006/metadata/core-properties}lastModifiedBy",
)
APP_TAGS = (
    "{http://schemas.openxmlformats.org/officeDocument/2006/extended-properties}Company",
    "{http://schemas.openxmlformats.org/officeDocument/2006/extended-properties}Manager",
)


def _blank_properties(data: bytes, tags: tuple[str, ...]) -> tuple[bytes, bool]:
    root = ET.fromstring(data)
    changed = False
    for tag in tags:
        node = root.find(tag)
        if node is not None and (node.text or ""):
            node.text = ""
            changed = True
    if not changed:
        return data, False
    return ET.tostring(root, encoding="utf-8", xml_declaration=True), True


def scrub_office_metadata(path: str | Path) -> Path:
    """事务式清空 DOCX/PPTX 中可能暴露身份的作者与组织属性。"""

    source = Path(path)
    if not source.is_file() or source.suffix.lower() not in {".docx", ".pptx"}:
        raise ValueError(f"不是可清理的 Office 文件：{source}")
    if not zipfile.is_zipfile(source):
        raise ValueError(f"Office 文件不是有效 ZIP 容器：{source}")

    temporary_handle = tempfile.NamedTemporaryFile(
        prefix=f".{source.stem}-metadata-",
        suffix=source.suffix,
        dir=source.parent,
        delete=False,
    )
    temporary = Path(temporary_handle.name)
    temporary_handle.close()
    changed = False
    try:
        with zipfile.ZipFile(source, "r") as input_zip, zipfile.ZipFile(
            temporary, "w"
        ) as output_zip:
            for info in input_zip.infolist():
                data = input_zip.read(info.filename)
                if info.filename == "docProps/core.xml":
                    data, item_changed = _blank_properties(data, CORE_TAGS)
                    changed = changed or item_changed
                elif info.filename == "docProps/app.xml":
                    data, item_changed = _blank_properties(data, APP_TAGS)
                    changed = changed or item_changed
                output_zip.writestr(info, data)
        if changed:
            temporary.replace(source)
        else:
            temporary.unlink()
        return source
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def office_authors(path: str | Path) -> tuple[str, str]:
    """返回 creator 与 lastModifiedBy，供验收器和测试使用。"""

    with zipfile.ZipFile(Path(path), "r") as archive:
        root = ET.fromstring(archive.read("docProps/core.xml"))
    values = []
    for tag in CORE_TAGS:
        node = root.find(tag)
        values.append((node.text or "").strip() if node is not None else "")
    return values[0], values[1]
