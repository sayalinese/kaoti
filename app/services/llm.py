import json
import re
import time

from .openai_compat import ApiError, post_chat


def _json_content(content: str) -> dict:
    content = content.strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content, flags=re.IGNORECASE)
    try:
        value = json.loads(content)
    except (TypeError, ValueError) as exc:
        raise ApiError("DeepSeek 返回的内容不是有效 JSON") from exc
    if not isinstance(value, dict):
        raise ApiError("DeepSeek 返回格式无效")
    return value


def _option_keys(question: dict) -> set[str]:
    return {
        str(option.get("key", "")).upper()
        for option in question.get("options", [])
        if isinstance(option, dict)
    }


def suggest_question_answer(config: dict, question: dict) -> dict:
    """Suggest a missing answer without treating it as human-confirmed."""
    options = question.get("options") or []
    if not question.get("stem") or len(options) < 2:
        raise ApiError("题目信息不足，无法生成候选答案")
    started = time.perf_counter()
    raw, data = post_chat(
        config,
        [
            {
                "role": "system",
                "content": (
                    "你是题库答案校验助手。根据题干和选项推断最可能的正确答案。"
                    "只返回 JSON，不要 Markdown：{\"answer\":[\"A\"],\"explanation\":\"简短理由\"}。"
                    "如果无法确定，answer 返回空数组。"
                ),
            },
            {"role": "user", "content": json.dumps(question, ensure_ascii=False)},
        ],
        max_tokens=512,
        timeout=60,
    )
    payload = _json_content(raw)
    answer = payload.get("answer", [])
    if isinstance(answer, str):
        answer = re.findall(r"[A-H]", answer.upper())
    if not isinstance(answer, list):
        answer = []
    keys = _option_keys(question)
    answer = sorted({str(item).upper() for item in answer if str(item).upper() in keys})
    explanation = str(payload.get("explanation") or "").strip()[:2000]
    if not answer:
        raise ApiError("DeepSeek 无法确定候选答案")
    return {
        "answer": answer,
        "explanation": explanation,
        "model": data.get("model") or config["model"],
        "latency_ms": int((time.perf_counter() - started) * 1000),
    }


def explain_question_options(config: dict, question: dict) -> dict:
    """Generate short explanations for every option after an answer is shown."""
    started = time.perf_counter()
    raw, data = post_chat(
        config,
        [
            {
                "role": "system",
                "content": (
                    "你是题库讲解助手。请逐项解释每个选项为什么正确或错误。"
                    "只返回 JSON，不要 Markdown：{\"options\":[{\"key\":\"A\",\"explanation\":\"...\"}]}。"
                    "每项解释不超过 80 个字，不要添加题目中没有的事实。"
                ),
            },
            {"role": "user", "content": json.dumps(question, ensure_ascii=False)},
        ],
        max_tokens=1024,
        timeout=60,
    )
    payload = _json_content(raw)
    items = payload.get("options")
    if not isinstance(items, list):
        raise ApiError("DeepSeek 返回的选项解析格式无效")
    keys = _option_keys(question)
    explanations = []
    for item in items:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key", "")).upper()
        explanation = str(item.get("explanation") or "").strip()
        if key in keys and explanation:
            explanations.append({"key": key, "explanation": explanation[:300]})
    if not explanations:
        raise ApiError("DeepSeek 没有返回选项解析")
    return {
        "options": explanations,
        "model": data.get("model") or config["model"],
        "latency_ms": int((time.perf_counter() - started) * 1000),
    }


def validate_ocr_text(config: dict, text: str) -> dict:
    """Correct only obvious OCR errors while preserving the source content."""
    text = str(text or "").strip()
    if not text:
        raise ApiError("OCR 没有返回可校验的文字")

    started = time.perf_counter()
    corrected, data = post_chat(
        config,
        [
            {
                "role": "system",
                "content": (
                    "你是题库 OCR 校验助手。只修正明显的 OCR 错字、乱码、断行和选项编号，"
                    "不要补写原文没有的信息。保留题干、选项、答案和解析的含义。"
                    "如果多个选项出现在同一行，请按 A、B、C 等编号拆成独立行。"
                    "只输出校验后的文本，不要解释修改过程。"
                ),
            },
            {"role": "user", "content": text[:12000]},
        ],
        max_tokens=1024,
        timeout=60,
    )
    if not corrected:
        raise ApiError("DeepSeek 没有返回校验文本")
    return {
        "latency_ms": int((time.perf_counter() - started) * 1000),
        "model": data.get("model") or config["model"],
        "text": corrected[:12000],
    }


def structure_ocr_text(config: dict, text: str) -> dict:
    """Reformat OCR text into the line structure expected by the rule parser."""
    if not str(text or "").strip():
        raise ApiError("OCR 没有返回可整理的文字")
    started = time.perf_counter()
    normalized, data = post_chat(
        config,
        [
            {
                "role": "system",
                "content": (
                    "你是题库截图提取助手。OCR 文本可能包含手机状态栏、导航栏、按钮、颜色说明、笔记区等界面噪声。"
                    "只提取题目本身：题号、题干、A-H 选项、截图中明确显示的正确答案和答案解析。"
                    "忽略状态栏、返回、收藏、确认选项、用户选择、时间、头像、点赞和笔记区。"
                    "每道题必须从数字题号开始；每个选项单独一行，格式为 A. 内容；答案单独一行，格式为答案：A。"
                    "如果截图没有明确答案，输出答案：，不要猜答案。不要输出 Markdown 或说明文字。"
                ),
            },
            {"role": "user", "content": str(text)[:12000]},
        ],
        max_tokens=4096,
        timeout=60,
    )
    if not normalized:
        raise ApiError("DeepSeek 没有返回整理后的文字")
    return {
        "text": normalized[:12000],
        "model": data.get("model") or config["model"],
        "latency_ms": int((time.perf_counter() - started) * 1000),
    }


def test_connection(config: dict) -> dict:
    started = time.perf_counter()
    reply, data = post_chat(
        config,
        [{"role": "user", "content": "只回复两个字母：OK"}],
        max_tokens=256,
        timeout=45,
    )
    latency_ms = int((time.perf_counter() - started) * 1000)

    if not reply:
        reasoning = ""
        try:
            reasoning = str(
                data["choices"][0]["message"].get("reasoning_content") or ""
            ).strip()
        except (KeyError, IndexError, TypeError):
            pass
        if reasoning:
            raise ApiError(
                "模型只返回了推理内容，正文为空；请确认模型 ID 是对话模型，或改用非推理模型"
            )
        raise ApiError("接口已连通，但模型没有返回文本")

    usage = data.get("usage") if isinstance(data, dict) else None
    return {
        "latency_ms": latency_ms,
        "model": data.get("model") or config["model"],
        "reply": reply[:120],
        "usage": usage if isinstance(usage, dict) else None,
    }
