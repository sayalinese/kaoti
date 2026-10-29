import base64
import time

from .openai_compat import ApiError, post_chat

MAX_IMAGE_BYTES = 4 * 1024 * 1024


def _check_image(data_url: str) -> None:
    if not isinstance(data_url, str) or not data_url.startswith("data:image/"):
        raise ApiError("测试图片格式无效")
    if ";base64," not in data_url:
        raise ApiError("测试图片格式无效")
    approx_bytes = len(data_url) * 3 // 4
    if approx_bytes > MAX_IMAGE_BYTES:
        raise ApiError("测试图片过大")


def test_connection(config: dict, image_data_url: str) -> dict:
    _check_image(image_data_url)

    started = time.perf_counter()
    text, data = post_chat(
        config,
        [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": image_data_url}},
                    {"type": "text", "text": "OCR:"},
                ],
            }
        ],
        max_tokens=256,
        timeout=60,
    )
    latency_ms = int((time.perf_counter() - started) * 1000)

    return {
        "latency_ms": latency_ms,
        "model": data.get("model") or config["model"],
        "text": text[:2000],
    }


def recognize_image(config: dict, data: bytes, mime_type: str) -> dict:
    if not data or len(data) > MAX_IMAGE_BYTES:
        raise ApiError("图片为空或超过 4MB")
    if not mime_type.startswith("image/"):
        raise ApiError("图片格式无效")

    image_data_url = (
        f"data:{mime_type};base64,{base64.b64encode(data).decode('ascii')}"
    )
    started = time.perf_counter()
    text, response = post_chat(
        config,
        [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": image_data_url}},
                    {
                        "type": "text",
                        "text": "请逐行提取图片中的题目、选项、答案和解析。每个选项和答案必须单独成行，保留原有编号和换行，只输出识别到的文字。",
                    },
                ],
            }
        ],
        max_tokens=4096,
        timeout=90,
    )
    return {
        "text": text[:12000],
        "model": response.get("model") or config["model"],
        "latency_ms": int((time.perf_counter() - started) * 1000),
    }
