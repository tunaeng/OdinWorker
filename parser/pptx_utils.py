import re
import zipfile
from pathlib import Path

_SLIDE_PATTERN = re.compile(r'ppt/slides/slide(\d+)\.xml')
_TEXT_PATTERN = re.compile(r'<a:t[^>]*>([\s\S]*?)</a:t>')
_XML_ENTITY_MAP = {
    "&amp;": "&",
    "&lt;": "<",
    "&gt;": ">",
    "&quot;": '"',
    "&apos;": "'",
}
_NUM_ENTITY_PATTERN = re.compile(r'&#(\d+);')
_HEX_ENTITY_PATTERN = re.compile(r'&#x([0-9a-fA-F]+);')


def decode_xml_entities(text: str) -> str:
    for entity, char in _XML_ENTITY_MAP.items():
        text = text.replace(entity, char)
    text = _NUM_ENTITY_PATTERN.sub(lambda m: chr(int(m.group(1))), text)
    text = _HEX_ENTITY_PATTERN.sub(lambda m: chr(int(m.group(1), 16)), text)
    return text


def extract_last_slide_text(file_path: str) -> str | None:
    """Извлечь текст с последнего слайда .pptx.

    Возвращает строку или None, если файл не является валидным .pptx
    или не содержит слайдов.
    """
    path = Path(file_path)
    if not path.exists():
        return None

    try:
        with zipfile.ZipFile(path, "r") as zf:
            slide_files = []
            for name in zf.namelist():
                match = _SLIDE_PATTERN.search(name)
                if match:
                    slide_files.append((int(match.group(1)), name))

            if not slide_files:
                return None

            slide_files.sort(key=lambda x: x[0])
            last_slide_name = slide_files[-1][1]

            xml_content = zf.read(last_slide_name).decode("utf-8")
    except (zipfile.BadZipFile, OSError):
        return None

    fragments = _TEXT_PATTERN.findall(xml_content)
    if not fragments:
        return None

    text = " ".join(fragments)
    text = decode_xml_entities(text)
    text = " ".join(text.split())
    return text.strip() if text.strip() else None
