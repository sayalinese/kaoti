const LLM_PRESETS = {
  deepseek: {
    base_url: "https://api.deepseek.com/v1",
    model: "deepseek-flash",
    placeholder: "deepseek-flash",
    hint: 'DeepSeek 官方当前使用 <code>deepseek-flash</code>。',
  },
  siliconflow: {
    base_url: "https://api.siliconflow.cn/v1",
    model: "",
    placeholder: "从控制台复制模型 ID",
    hint: "填控制台里的完整模型 ID，区分大小写。",
  },
  custom: {
    base_url: "",
    model: "",
    placeholder: "模型 ID",
    hint: "填写接口文档中的模型 ID。",
  },
};

const state = {
  dirty: false,
  saving: false,
  llmSaved: null,
  ocrSaved: null,
};

const el = {
  llmProvider: document.getElementById("llm-provider"),
  llmBase: document.getElementById("llm-base"),
  llmModel: document.getElementById("llm-model"),
  llmModelHint: document.getElementById("llm-model-hint"),
  llmKey: document.getElementById("llm-key"),
  llmKeyState: document.getElementById("llm-key-state"),
  llmReveal: document.getElementById("llm-reveal"),
  llmClear: document.getElementById("llm-clear"),
  llmSave: document.getElementById("llm-save"),
  llmTest: document.getElementById("llm-test"),
  llmTestState: document.getElementById("llm-test-state"),
  llmResult: document.getElementById("llm-result"),

  ocrBase: document.getElementById("ocr-base"),
  ocrModel: document.getElementById("ocr-model"),
  ocrKey: document.getElementById("ocr-key"),
  ocrKeyState: document.getElementById("ocr-key-state"),
  ocrReveal: document.getElementById("ocr-reveal"),
  ocrClear: document.getElementById("ocr-clear"),
  ocrSave: document.getElementById("ocr-save"),
  ocrTest: document.getElementById("ocr-test"),
  ocrTestState: document.getElementById("ocr-test-state"),
  ocrResult: document.getElementById("ocr-result"),

  dataDir: document.getElementById("data-dir"),
  settingsPath: document.getElementById("settings-path"),
  saveState: document.getElementById("save-state"),
  save: document.getElementById("save"),
};

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });

  let data = null;
  try {
    data = await response.json();
  } catch {
    data = null;
  }

  if (!response.ok) {
    const message =
      data && data.error ? data.error : `请求失败（HTTP ${response.status}）`;
    throw new Error(message);
  }
  return data;
}

function setSaveState(text, tone = "") {
  el.saveState.textContent = text;
  el.saveState.className = "save-state";
  if (tone) el.saveState.classList.add(`is-${tone}`);
}

function markDirty() {
  state.dirty = true;
  el.save.disabled = state.saving;
  setSaveState("有未保存的更改", "dirty");
}

function markClean(text = "所有更改已保存", tone = "") {
  state.dirty = false;
  el.save.disabled = true;
  setSaveState(text, tone);
}

function updateKeyState(target, config) {
  const hasKey = Boolean(config.has_key);
  const hint = document.getElementById(`${target}-key-state`);
  const clearButton = document.getElementById(`${target}-clear`);
  hint.textContent = hasKey ? `已保存 · ${config.key_hint}` : "未保存";
  clearButton.hidden = !hasKey;
}

function updateModelUi() {
  const preset = LLM_PRESETS[el.llmProvider.value] || LLM_PRESETS.custom;
  el.llmModel.placeholder = preset.placeholder;
  el.llmModelHint.innerHTML = preset.hint;
}

function resetReveal(button, input) {
  input.type = "password";
  button.textContent = "显示";
}

function fill(data) {
  el.llmProvider.value = data.llm.provider;
  el.llmBase.value = data.llm.base_url;
  el.llmModel.value = data.llm.model;

  el.ocrBase.value = data.ocr.base_url;
  el.ocrModel.value = data.ocr.model;

  updateKeyState("llm", data.llm);
  updateKeyState("ocr", data.ocr);

  state.llmSaved = {
    provider: data.llm.provider,
    base_url: data.llm.base_url,
    model: data.llm.model,
  };
  state.ocrSaved = {
    provider: data.ocr.provider,
    base_url: data.ocr.base_url,
    model: data.ocr.model,
  };

  el.llmKey.value = "";
  el.ocrKey.value = "";
  resetReveal(el.llmReveal, el.llmKey);
  resetReveal(el.ocrReveal, el.ocrKey);

  el.dataDir.textContent = data.data_dir;
  el.settingsPath.textContent = data.settings_path;

  updateModelUi();
  disarmClear("llm");
  disarmClear("ocr");
  state.dirty = false;
  el.save.disabled = true;
}

function buildPayload() {
  const payload = {
    llm: {
      provider: el.llmProvider.value,
      base_url: el.llmBase.value.trim(),
      model: el.llmModel.value.trim(),
    },
    ocr: {
      provider: "siliconflow",
      base_url: el.ocrBase.value.trim(),
      model: el.ocrModel.value.trim(),
    },
  };

  const llmKey = el.llmKey.value.trim();
  if (llmKey) payload.llm.api_key = llmKey;

  const ocrKey = el.ocrKey.value.trim();
  if (ocrKey) payload.ocr.api_key = ocrKey;

  return payload;
}

async function save({ silent = false } = {}) {
  if (state.saving) return false;
  state.saving = true;
  el.save.disabled = true;
  el.llmSave.disabled = true;
  el.ocrSave.disabled = true;

  try {
    const data = await api("/api/settings", {
      method: "PUT",
      body: JSON.stringify(buildPayload()),
    });
    fill(data);
    setSaveState(silent ? "配置已自动保存" : "已保存到本机", "ok");
    return true;
  } catch (error) {
    setSaveState(`保存失败：${error.message}`, "error");
    return false;
  } finally {
    state.saving = false;
    el.save.disabled = !state.dirty;
    el.llmSave.disabled = false;
    el.ocrSave.disabled = false;
  }
}

function setTestState(target, text, tone = "") {
  const node = document.getElementById(`${target}-test-state`);
  node.textContent = text;
  node.className = "test-state";
  if (tone) node.classList.add(`is-${tone}`);
}

function hideResult(node) {
  node.hidden = true;
  node.textContent = "";
}

function showResult(node, text) {
  node.hidden = false;
  node.textContent = text;
}

async function runLlmTest() {
  el.llmTest.disabled = true;
  hideResult(el.llmResult);
  setTestState("llm", "正在保存配置…");

  const saved = await save({ silent: true });
  if (!saved) {
    setTestState("llm", "保存失败，未发起测试", "error");
    el.llmTest.disabled = false;
    return;
  }

  setTestState("llm", "请求中…");
  try {
    const data = await api("/api/settings/test/llm", {
      method: "POST",
      body: "{}",
    });
    const tokens =
      data.usage && data.usage.total_tokens != null
        ? ` · ${data.usage.total_tokens} tokens`
        : "";
    setTestState("llm", `连接正常 · ${data.latency_ms} ms · ${data.model}`, "ok");
    showResult(el.llmResult, `模型回复：${data.reply}${tokens}`);
  } catch (error) {
    setTestState("llm", "连接失败", "error");
    showResult(el.llmResult, error.message);
  } finally {
    el.llmTest.disabled = false;
  }
}

function buildTestImage() {
  const canvas = document.createElement("canvas");
  canvas.width = 900;
  canvas.height = 240;
  const ctx = canvas.getContext("2d");

  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = "#111111";
  ctx.font = '54px "Songti SC", "SimSun", Georgia, serif';
  ctx.fillText("题库 OCR 测试 2026", 48, 96);
  ctx.font = '32px "Segoe UI", "Microsoft YaHei", sans-serif';
  ctx.fillText("1. 下列关于细胞的说法，正确的是（ ）", 48, 168);

  return canvas.toDataURL("image/png");
}

async function runOcrTest() {
  el.ocrTest.disabled = true;
  hideResult(el.ocrResult);
  setTestState("ocr", "正在保存配置…");

  const saved = await save({ silent: true });
  if (!saved) {
    setTestState("ocr", "保存失败，未发起测试", "error");
    el.ocrTest.disabled = false;
    return;
  }

  setTestState("ocr", "请求中…");
  try {
    const data = await api("/api/settings/test/ocr", {
      method: "POST",
      body: JSON.stringify({ image: buildTestImage() }),
    });
    const text = (data.text || "").trim();
    if (!text) {
      setTestState("ocr", "接口已连通，但返回为空", "error");
      showResult(el.ocrResult, "模型没有返回识别文本，请核对模型 ID 是否支持图片输入。");
      return;
    }

    const compact = text.replace(/\s+/g, "");
    const matched = compact.includes("题库") && compact.includes("2026");
    const validation = data.validation;
    const validationText = validation && validation.ok ? validation.text : "";
    setTestState(
      "ocr",
      validationText
        ? `识别并校验正常 · ${data.latency_ms} ms`
        : matched
          ? `识别正常 · ${data.latency_ms} ms · ${data.model}`
          : `接口已连通 · ${data.latency_ms} ms · 未匹配测试字样`,
      validationText || matched ? "ok" : "warn"
    );
    const validationResult = validationText
      ? `\n\nDeepSeek 校验结果：\n${validationText}`
      : validation && !validation.ok
        ? `\n\nDeepSeek 校验未完成：${validation.error}`
        : "";
    showResult(el.ocrResult, `识别结果：\n${text}${validationResult}`);
  } catch (error) {
    setTestState("ocr", "识别失败", "error");
    showResult(el.ocrResult, error.message);
  } finally {
    el.ocrTest.disabled = false;
  }
}

function disarmClear(target) {
  const button = el[`${target}Clear`];
  button.dataset.armed = "";
  button.classList.remove("is-armed");
  button.textContent = "清除已保存密钥";
}

function armClear(target) {
  const button = el[`${target}Clear`];
  if (!button.dataset.armed) {
    button.dataset.armed = "1";
    button.classList.add("is-armed");
    button.textContent = "再次点击确认清除";
    window.setTimeout(() => disarmClear(target), 4000);
    return;
  }
  disarmClear(target);
  clearKey(target);
}

async function clearKey(target) {
  const saved = state[`${target}Saved`];
  if (!saved) return;

  const payload = {
    [target]: {
      provider: saved.provider,
      base_url: saved.base_url,
      model: saved.model,
      clear_key: true,
    },
  };

  try {
    const data = await api("/api/settings", {
      method: "PUT",
      body: JSON.stringify(payload),
    });
    fill(data);
    setSaveState("密钥已清除", "ok");
  } catch (error) {
    setSaveState(`清除失败：${error.message}`, "error");
  }
}

function bindReveal(button, input) {
  button.addEventListener("click", () => {
    const show = input.type === "password";
    input.type = show ? "text" : "password";
    button.textContent = show ? "隐藏" : "显示";
  });
}

function bindEvents() {
  el.llmProvider.addEventListener("change", () => {
    const preset = LLM_PRESETS[el.llmProvider.value] || LLM_PRESETS.custom;
    if (el.llmProvider.value !== "custom") {
      el.llmBase.value = preset.base_url;
      el.llmModel.value = preset.model;
    }
    updateModelUi();
    markDirty();
  });

  for (const node of [el.llmBase, el.llmModel, el.ocrBase, el.ocrModel]) {
    node.addEventListener("input", markDirty);
  }

  el.llmKey.addEventListener("input", markDirty);
  el.ocrKey.addEventListener("input", markDirty);

  bindReveal(el.llmReveal, el.llmKey);
  bindReveal(el.ocrReveal, el.ocrKey);

  el.llmClear.addEventListener("click", () => armClear("llm"));
  el.ocrClear.addEventListener("click", () => armClear("ocr"));

  el.llmTest.addEventListener("click", runLlmTest);
  el.ocrTest.addEventListener("click", runOcrTest);

  el.llmSave.addEventListener("click", () => save());
  el.ocrSave.addEventListener("click", () => save());
  el.save.addEventListener("click", () => save());

  window.addEventListener("beforeunload", (event) => {
    if (!state.dirty) return;
    event.preventDefault();
    event.returnValue = "";
  });
}

async function init() {
  bindEvents();
  updateModelUi();

  try {
    const data = await api("/api/settings");
    fill(data);
    markClean();
  } catch (error) {
    setSaveState(`读取设置失败：${error.message}`, "error");
  }
}

init();
