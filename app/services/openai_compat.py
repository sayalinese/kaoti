import requests


class ApiError(RuntimeError):
    pass


def chat_completions_url(base_url: str) -> str:
    base = base_url.strip().rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    if base.endswith("/v1"):
        return base + "/chat/completions"
    return base + "/v1/chat/completions"


def _error_message(response: requests.Response) -> str:
    try:
        data = response.json()
    except ValueError:
        return (response.text or "").strip()[:300] or "无响应内容"

    if isinstance(data, dict):
        error = data.get("error")
        if isinstance(error, dict) and error.get("message"):
            return str(error["message"])[:300]
        if data.get("message"):
            return str(data["message"])[:300]
    return str(data)[:300]


def post_chat(
    config: dict,
    messages: list,
    *,
    max_tokens: int = 16,
    temperature: float = 0,
    timeout: int = 45,
):
    api_key = config.get("api_key", "")
    if not api_key:
        raise ApiError("尚未保存 API Key")

    url = chat_completions_url(config["base_url"])
    payload = {
        "model": config["model"],
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": False,
    }

    try:
        response = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise ApiError(f"无法连接接口：{exc}") from exc

    if response.status_code >= 400:
        raise ApiError(
            f"接口返回 HTTP {response.status_code}：{_error_message(response)}"
        )

    try:
        data = response.json()
    except ValueError as exc:
        raise ApiError("接口返回内容不是 JSON") from exc

    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ApiError("接口返回格式不符合 OpenAI 兼容规范") from exc

    if isinstance(content, list):
        content = "".join(
            part.get("text", "") for part in content if isinstance(part, dict)
        )
    return (content or "").strip(), data
