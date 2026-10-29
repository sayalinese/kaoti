import re

TYPES = ("single", "multiple", "tf")
TYPE_LABELS = {
    "single": "单选题",
    "multiple": "多选题",
    "tf": "判断题",
}


def clean_text(value, limit: int | None = None) -> str:
    if value is None:
        return ""
    text = str(value).replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\xa0", " ").strip()
    if limit is not None:
        text = text[:limit]
    return text


def normalize_options(raw) -> list[dict]:
    options = []
    used = set()
    if not isinstance(raw, list):
        return options

    for index, item in enumerate(raw[:8]):
        if isinstance(item, dict):
            key = str(item.get("key", "")).strip().upper()
            text = clean_text(item.get("text"))
        else:
            key = chr(ord("A") + index)
            text = clean_text(item)

        if not text and not key:
            continue
        if not re.fullmatch(r"[A-H]", key or ""):
            key = chr(ord("A") + index)
        if key in used:
            continue
        used.add(key)
        options.append({"key": key, "text": text})

    options.sort(key=lambda item: item["key"])
    return options


def normalize_answer(raw, option_keys) -> tuple[list[str], list[str]]:
    letters = []
    if isinstance(raw, str):
        text = raw.upper()
        if "正确" in text or "对" in text:
            letters.append("A")
        if "错误" in text or "错" in text:
            letters.append("B")
        letters.extend(re.findall(r"[A-H]", text))
    elif isinstance(raw, list):
        for item in raw:
            letters.extend(re.findall(r"[A-H]", str(item).upper()))
    else:
        return [], []

    unique = []
    for letter in letters:
        if letter not in unique:
            unique.append(letter)

    valid = sorted(letter for letter in unique if letter in option_keys)
    invalid = sorted(letter for letter in unique if letter not in option_keys)
    return valid, invalid


def infer_type(options: list[dict], raw_answer, section_label: str | None = None) -> str:
    texts = [clean_text(item.get("text")) for item in options]
    if len(texts) == 2 and set(texts) == {"正确", "错误"}:
        return "tf"

    option_keys = {item["key"] for item in options}
    valid, _ = normalize_answer(raw_answer, option_keys)
    if len(valid) > 1:
        return "multiple"
    if not valid and section_label == "多选题":
        return "multiple"
    return "single"


def validate_question(payload: dict) -> tuple[dict, list[str]]:
    type_ = str(payload.get("type") or "single").strip()
    if type_ not in TYPES:
        type_ = "single"

    stem = clean_text(payload.get("stem"), 5000)
    options = normalize_options(payload.get("options"))
    option_keys = {item["key"] for item in options}
    answer, invalid = normalize_answer(payload.get("answer"), option_keys)
    explanation = clean_text(payload.get("explanation"), 5000)

    warnings = []
    if not stem:
        warnings.append("题干为空")
    if len(options) < 2:
        warnings.append("选项少于两个")
    if option_keys:
        expected_keys = [
            chr(code) for code in range(ord("A"), max(map(ord, option_keys)) + 1)
        ]
        missing_keys = sorted(set(expected_keys) - option_keys)
        if missing_keys:
            warnings.append("选项编号不连续：缺少 " + "、".join(missing_keys))
    if any(not item["text"] for item in options):
        warnings.append("存在空选项")
    if invalid:
        warnings.append("答案字母不在选项中：" + "、".join(invalid))
    if not answer and not invalid:
        warnings.append("缺少答案")
    elif not answer and invalid:
        warnings.append("没有有效答案")
    if type_ in ("single", "tf") and len(answer) > 1:
        warnings.append("单选题答案多于一个")
    if type_ == "tf" and len(options) != 2:
        warnings.append("判断题应为两个选项")

    data = {
        "type": type_,
        "stem": stem,
        "options": options,
        "answer": answer,
        "explanation": explanation,
    }
    return data, warnings
