import hashlib
import io

from pypdf import PdfReader

from ..errors import InvalidInput
from .docx_parser import parse_text


def parse_pdf(data: bytes, filename: str) -> dict:
    try:
        reader = PdfReader(io.BytesIO(data))
        text = "\n".join(page.extract_text() or "" for page in reader.pages).strip()
    except Exception as exc:
        raise InvalidInput("无法读取 PDF 文件，请确认文件没有损坏") from exc

    if not text:
        raise InvalidInput("PDF 没有可提取的文字层，请将页面转为图片后使用 OCR")
    return parse_text(
        text,
        filename,
        source_hash=hashlib.sha256(data).hexdigest(),
    )
