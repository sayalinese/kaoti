(function () {
  const TYPE_LABELS = {
    single: "单选题",
    multiple: "多选题",
    tf: "判断题",
  };

  const ESCAPES = {
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  };

  function esc(value) {
    return String(value == null ? "" : value).replace(
      /[&<>"']/g,
      (character) => ESCAPES[character]
    );
  }

  async function api(path, options = {}) {
    const opts = { ...options };
    const headers = new Headers(options.headers || {});
    if (
      opts.body &&
      typeof opts.body === "string" &&
      !headers.has("Content-Type")
    ) {
      headers.set("Content-Type", "application/json");
    }
    opts.headers = headers;

    const response = await fetch(path, opts);
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

  function typeLabel(type) {
    return TYPE_LABELS[type] || type || "题目";
  }

  function answerText(keys) {
    return Array.isArray(keys) && keys.length ? keys.join("、") : "待补充";
  }

  function contextHtml(question) {
    if (!question.paper_name) return "";
    const label = `${esc(question.subject_name || "")} / ${esc(
      question.paper_name
    )}`;
    if (question.paper_id) {
      return `<a class="q-context" href="/?paper=${encodeURIComponent(
        question.paper_id
      )}">${label}</a>`;
    }
    return `<p class="q-context">${label}</p>`;
  }

  function questionCardHtml(question, options = {}) {
    const showContext = options.showContext === true;
    const showEdit = options.showEdit !== false;
    const answer = Array.isArray(question.answer) ? question.answer : [];
    const questionOptions = Array.isArray(question.options)
      ? question.options
      : [];
    const number =
      question.number == null ? "题目" : `第 ${question.number} 题`;

    const optionHtml = questionOptions
      .map((option) => {
        const isCorrect = answer.includes(option.key);
        return `<li class="q-option${isCorrect ? " is-correct" : ""}">
          <span class="opt-key">${esc(option.key)}</span>
          <span class="opt-text">${esc(option.text || "（空选项）")}</span>
          ${isCorrect ? '<span class="opt-answer">答案</span>' : ""}
        </li>`;
      })
      .join("");

    return `<article class="question-card" data-question-id="${esc(
      question.id
    )}">
      <div class="q-head">
        <span class="q-number">${esc(number)}</span>
        <span class="q-type">${esc(typeLabel(question.type))}</span>
        ${
          question.status === "needs_review"
            ? '<span class="q-status">待核对</span>'
            : ""
        }
        <span class="spacer"></span>
        <div class="q-actions">
          <button type="button" class="btn btn-quiet btn-sm fav-btn${
            question.favorite ? " is-active" : ""
          }" data-action="favorite" data-id="${esc(question.id)}">${
            question.favorite ? "已收藏" : "收藏"
          }</button>
          ${
            showEdit
              ? `<button type="button" class="link-btn" data-action="edit" data-id="${esc(
                  question.id
                )}">编辑</button>`
              : ""
          }
        </div>
      </div>
      ${showContext ? contextHtml(question) : ""}
      <p class="q-stem">${esc(question.stem)}</p>
      <ol class="q-options">${optionHtml}</ol>
      <p class="q-answer${
        question.answer_source === "llm" ? " answer-source-llm" : ""
      }">${
        question.answer_source === "llm" ? "DeepSeek 候选答案：" : "答案："
      }${esc(answerText(answer))}</p>
      ${
        question.status === "needs_review" && question.review_note
          ? `<p class="q-review">${esc(question.review_note)}</p>`
          : ""
      }
    </article>`;
  }

  function unique(list) {
    return [...new Set(list)];
  }

  function evaluateQuestion(question) {
    const stem = String(question.stem || "").trim();
    const options = (Array.isArray(question.options) ? question.options : []).map(
      (option) => ({
        key: String(option.key || "").toUpperCase(),
        text: String(option.text || "").trim(),
      })
    );
    const keys = new Set(options.map((option) => option.key));
    const answer = unique(
      (Array.isArray(question.answer) ? question.answer : [])
        .map((key) => String(key).toUpperCase())
        .filter((key) => keys.has(key))
    ).sort();

    const warnings = [];
    if (!stem) warnings.push("题干为空");
    if (options.length < 2) warnings.push("选项少于两个");
    if (options.some((option) => !option.text)) warnings.push("存在空选项");
    if (!answer.length) warnings.push("缺少答案");
    if (keys.size !== options.length) warnings.push("选项编号重复");
    if (
      (question.type === "single" || question.type === "tf") &&
      answer.length > 1
    ) {
      warnings.push("单选题答案多于一个");
    }
    if (question.type === "tf" && options.length !== 2) {
      warnings.push("判断题应为两个选项");
    }

    return {
      status: warnings.length ? "needs_review" : "ready",
      warnings,
      answer,
    };
  }

  function debounce(fn, wait = 250) {
    let timer = null;
    return function (...args) {
      clearTimeout(timer);
      timer = setTimeout(() => fn.apply(this, args), wait);
    };
  }

  function getParam(name) {
    return new URLSearchParams(window.location.search).get(name);
  }

  function nextOptionKey(options) {
    const used = new Set(options.map((option) => option.key));
    for (const key of "ABCDEFGH") {
      if (!used.has(key)) return key;
    }
    return null;
  }

  function setupQuestionEditor(hostSelector) {
    const host = document.querySelector(hostSelector);
    if (!host) return () => {};

    host.innerHTML = `
      <dialog class="dialog" id="question-editor">
        <div class="dialog-head">
          <h2>编辑题目</h2>
          <button type="button" class="dialog-close" data-close aria-label="关闭">×</button>
        </div>
        <div class="dialog-body">
          <p class="editor-note" id="editor-note" hidden></p>
          <div class="editor-row">
            <label class="field-label" for="editor-type">题型</label>
            <select id="editor-type">
              <option value="single">单选题</option>
              <option value="multiple">多选题</option>
              <option value="tf">判断题</option>
            </select>
          </div>
          <div>
            <label class="field-label" for="editor-stem">题干</label>
            <textarea id="editor-stem" rows="5"></textarea>
          </div>
          <div>
            <div class="label-row">
              <span class="field-label">选项</span>
              <span class="hint">勾选正确答案；判断题选一个</span>
            </div>
            <div class="editor-options" id="editor-options"></div>
            <button type="button" class="link-btn" id="editor-add-option">添加选项</button>
          </div>
          <div>
            <label class="field-label" for="editor-explanation">解析（可选）</label>
            <textarea id="editor-explanation" rows="3"></textarea>
          </div>
          <p class="editor-status" id="editor-status"></p>
        </div>
        <div class="dialog-foot">
          <button type="button" class="btn btn-outline" data-close>取消</button>
          <button type="button" class="btn btn-primary" id="editor-save">保存修改</button>
        </div>
      </dialog>
    `;

    const dialog = host.querySelector("#question-editor");
    const typeSelect = host.querySelector("#editor-type");
    const stemInput = host.querySelector("#editor-stem");
    const explanationInput = host.querySelector("#editor-explanation");
    const optionsHost = host.querySelector("#editor-options");
    const addButton = host.querySelector("#editor-add-option");
    const saveButton = host.querySelector("#editor-save");
    const statusNode = host.querySelector("#editor-status");
    const noteNode = host.querySelector("#editor-note");

    let currentQuestion = null;
    let optionsState = [];
    let onSaveHandler = null;

    function syncOptions() {
      const rows = optionsHost.querySelectorAll(".editor-option");
      rows.forEach((row) => {
        const key = row.dataset.key;
        const item = optionsState.find((option) => option.key === key);
        if (!item) return;
        item.text = row.querySelector("[data-opt-text]").value;
        item.correct = row.querySelector("[data-opt-correct]").checked;
      });
    }

    function renderOptions() {
      optionsState.sort((a, b) => a.key.localeCompare(b.key));
      optionsHost.innerHTML = optionsState
        .map(
          (option) => `<div class="editor-option" data-key="${option.key}">
            <span class="opt-key">${option.key}</span>
            <input type="text" data-opt-text value="${esc(
              option.text
            )}" aria-label="选项 ${option.key}">
            <label class="editor-correct">
              <input type="checkbox" data-opt-correct ${
                option.correct ? "checked" : ""
              }> 正确
            </label>
            <button type="button" class="editor-remove" data-remove="${
              option.key
            }">移除</button>
          </div>`
        )
        .join("");
    }

    function setStatus(text, tone = "") {
      statusNode.textContent = text;
      statusNode.className = "editor-status";
      if (tone) statusNode.classList.add(`is-${tone}`);
    }

    function ensureKeys(sourceOptions, sourceAnswer) {
      const answer = new Set(
        (Array.isArray(sourceAnswer) ? sourceAnswer : []).map((key) =>
          String(key).toUpperCase()
        )
      );
      const used = new Set();
      const result = [];

      (Array.isArray(sourceOptions) ? sourceOptions : []).forEach((option) => {
        let key = String(option.key || "").toUpperCase();
        if (!/^[A-H]$/.test(key) || used.has(key)) {
          key = nextOptionKey(result) || "";
        }
        if (!key) return;
        used.add(key);
        result.push({
          key,
          text: String(option.text || ""),
          correct: answer.has(key),
        });
      });

      if (result.length === 0) {
        result.push(
          { key: "A", text: "", correct: false },
          { key: "B", text: "", correct: false }
        );
      } else if (result.length === 1) {
        const key = nextOptionKey(result) || "B";
        result.push({ key, text: "", correct: false });
      }

      return result;
    }

    function open(question, onSave) {
      currentQuestion = question;
      onSaveHandler = onSave;
      optionsState = ensureKeys(question.options, question.answer);
      typeSelect.value = TYPE_LABELS[question.type] ? question.type : "single";
      stemInput.value = question.stem || "";
      explanationInput.value = question.explanation || "";
      renderOptions();
      setStatus("");

      const note =
        question.review_note ||
        (Array.isArray(question.warnings) ? question.warnings.join("；") : "");
      noteNode.hidden = !note;
      noteNode.textContent = note ? `原始提示：${note}` : "";

      if (!dialog.open) dialog.showModal();
    }

    function close() {
      if (dialog.open) dialog.close();
    }

    optionsHost.addEventListener("change", (event) => {
      if (!event.target.matches("[data-opt-correct]")) return;
      syncOptions();
      if (typeSelect.value !== "multiple" && event.target.checked) {
        optionsState.forEach((option) => {
          if (option.key !== event.target.closest(".editor-option").dataset.key) {
            option.correct = false;
          }
        });
        renderOptions();
      }
    });

    typeSelect.addEventListener("change", () => {
      syncOptions();
      if (typeSelect.value !== "multiple") {
        let seen = false;
        optionsState.forEach((option) => {
          if (option.correct && seen) option.correct = false;
          if (option.correct) seen = true;
        });
        renderOptions();
      }
    });

    addButton.addEventListener("click", () => {
      syncOptions();
      const key = nextOptionKey(optionsState);
      if (!key) {
        setStatus("最多支持 8 个选项", "error");
        return;
      }
      optionsState.push({ key, text: "", correct: false });
      renderOptions();
      const input = optionsHost.querySelector(
        `.editor-option[data-key="${key}"] [data-opt-text]`
      );
      if (input) input.focus();
    });

    optionsHost.addEventListener("click", (event) => {
      const removeButton = event.target.closest("[data-remove]");
      if (!removeButton) return;
      syncOptions();
      if (optionsState.length <= 2) {
        setStatus("至少保留两个选项", "error");
        return;
      }
      const key = removeButton.dataset.remove;
      optionsState = optionsState.filter((option) => option.key !== key);
      renderOptions();
      setStatus("");
    });

    host.querySelectorAll("[data-close]").forEach((button) => {
      button.addEventListener("click", close);
    });

    saveButton.addEventListener("click", async () => {
      if (!currentQuestion || !onSaveHandler) return;
      syncOptions();
      const stem = stemInput.value.trim();
      const explanation = explanationInput.value.trim();
      const options = optionsState
        .filter((option) => /^[A-H]$/.test(option.key))
        .sort((a, b) => a.key.localeCompare(b.key));

      if (!stem) {
        setStatus("请填写题干", "error");
        return;
      }
      if (options.length < 2) {
        setStatus("至少保留两个选项", "error");
        return;
      }
      if (options.some((option) => !option.text.trim())) {
        setStatus("选项内容不能为空", "error");
        return;
      }
      const answer = options
        .filter((option) => option.correct)
        .map((option) => option.key);
      if (!answer.length) {
        setStatus("请勾选正确答案", "error");
        return;
      }
      if (typeSelect.value !== "multiple" && answer.length > 1) {
        setStatus("单选题只能有一个正确答案", "error");
        return;
      }

      const updated = {
        ...currentQuestion,
        type: typeSelect.value,
        stem,
        explanation,
        options: options.map((option) => ({
          key: option.key,
          text: option.text.trim(),
        })),
        answer,
      };
      const evaluation = evaluateQuestion(updated);
      updated.status = evaluation.status;
      updated.warnings = evaluation.warnings;
      updated.review_note = evaluation.warnings.join("；");

      saveButton.disabled = true;
      setStatus("保存中…");
      try {
        await onSaveHandler(updated);
        close();
      } catch (error) {
        setStatus(`保存失败：${error.message}`, "error");
      } finally {
        saveButton.disabled = false;
      }
    });

    dialog.addEventListener("close", () => {
      currentQuestion = null;
      onSaveHandler = null;
      optionsState = [];
    });

    return open;
  }

  function setupQuizDialog(hostSelector) {
    const host = document.querySelector(hostSelector);
    if (!host) return () => {};

    host.innerHTML = `
      <dialog class="dialog" id="quiz-setup">
        <div class="dialog-head">
          <h2>开始练习</h2>
          <button type="button" class="dialog-close" data-close aria-label="关闭">×</button>
        </div>
        <div class="dialog-body">
          <p class="quiz-setup-title" id="quiz-setup-title"></p>
          <div class="editor-row">
            <label class="field-label" for="quiz-count">题目数量</label>
            <select id="quiz-count">
              <option value="10">10 题</option>
              <option value="20" selected>20 题</option>
              <option value="50">50 题</option>
              <option value="1000">全部可用题目</option>
            </select>
          </div>
          <div class="editor-row">
            <label class="field-label" for="quiz-type">题型</label>
            <select id="quiz-type">
              <option value="">全部题型</option>
              <option value="single">单选题</option>
              <option value="multiple">多选题</option>
              <option value="tf">判断题</option>
            </select>
          </div>
          <label class="check" id="quiz-favorite-wrap">
            <input type="checkbox" id="quiz-favorite"> 只练收藏题目
          </label>
          <p class="editor-status" id="quiz-setup-status"></p>
        </div>
        <div class="dialog-foot">
          <button type="button" class="btn btn-outline" data-close>取消</button>
          <button type="button" class="btn btn-primary" id="quiz-start">开始</button>
        </div>
      </dialog>
    `;

    const dialog = host.querySelector("#quiz-setup");
    const titleNode = host.querySelector("#quiz-setup-title");
    const countSelect = host.querySelector("#quiz-count");
    const typeSelect = host.querySelector("#quiz-type");
    const favoriteWrap = host.querySelector("#quiz-favorite-wrap");
    const favoriteInput = host.querySelector("#quiz-favorite");
    const statusNode = host.querySelector("#quiz-setup-status");
    const startButton = host.querySelector("#quiz-start");

    let startHandler = null;
    let forceFavorites = false;

    function setStatus(text, tone = "") {
      statusNode.textContent = text;
      statusNode.className = "editor-status";
      if (tone) statusNode.classList.add(`is-${tone}`);
    }

    function close() {
      if (dialog.open) dialog.close();
    }

    function open(config) {
      titleNode.textContent = config.subtitle || "";
      forceFavorites = config.forceFavorites === true;
      favoriteWrap.hidden = !config.allowFavorites;
      favoriteInput.checked = forceFavorites;
      startHandler = config.onStart;
      setStatus("");
      if (!dialog.open) dialog.showModal();
    }

    host.querySelectorAll("[data-close]").forEach((button) => {
      button.addEventListener("click", close);
    });

    startButton.addEventListener("click", async () => {
      if (!startHandler) return;
      const count = Number(countSelect.value);
      const types = typeSelect.value ? [typeSelect.value] : [];
      const favoritesOnly = forceFavorites || favoriteInput.checked;
      startButton.disabled = true;
      setStatus("正在组卷…");
      try {
        await startHandler({ count, types, favoritesOnly });
        close();
      } catch (error) {
        setStatus(`无法开始：${error.message}`, "error");
      } finally {
        startButton.disabled = false;
      }
    });

    return open;
  }

  window.Kaoti = {
    api,
    esc,
    typeLabel,
    answerText,
    questionCardHtml,
    evaluateQuestion,
    debounce,
    getParam,
    setupQuestionEditor,
    setupQuizDialog,
  };
})();
