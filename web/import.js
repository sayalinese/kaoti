(function () {
  const K = window.Kaoti;

  const state = {
    file: null,
    preview: null,
    questions: [],
    onlyReview: false,
    parsing: false,
    committing: false,
  };

  const el = {
    dropzone: document.getElementById("dropzone"),
    fileInput: document.getElementById("file"),
    fileLabel: document.getElementById("file-label"),
    subject: document.getElementById("subject"),
    paper: document.getElementById("paper"),
    parse: document.getElementById("parse"),
    parseStatus: document.getElementById("parse-status"),
    previewSection: document.getElementById("preview-section"),
    sourceName: document.getElementById("source-name"),
    statTotal: document.getElementById("stat-total"),
    statReady: document.getElementById("stat-ready"),
    statReview: document.getElementById("stat-review"),
    statDuplicates: document.getElementById("stat-duplicates"),
    notes: document.getElementById("import-notes"),
    selectAll: document.getElementById("select-all"),
    onlyReview: document.getElementById("only-review"),
    previewMeta: document.getElementById("preview-meta"),
    previewList: document.getElementById("preview-list"),
    commitSummary: document.getElementById("commit-summary"),
    commitStatus: document.getElementById("commit-status"),
    commit: document.getElementById("commit"),
  };

  let openEditor = null;

  function setStatus(text, tone = "") {
    el.parseStatus.textContent = text;
    el.parseStatus.className = "editor-status";
    if (tone) el.parseStatus.classList.add(`is-${tone}`);
  }

  function setCommitStatus(text, tone = "") {
    el.commitStatus.textContent = text;
    el.commitStatus.className = "editor-status commit-status";
    if (tone) el.commitStatus.classList.add(`is-${tone}`);
  }

  function setFile(file) {
    if (!file) return;
    const suffix = file.name.slice(file.name.lastIndexOf(".")).toLowerCase();
    if (![".docx", ".pdf", ".png", ".jpg", ".jpeg", ".webp"].includes(suffix)) {
      setStatus("支持 DOCX、PDF、PNG、JPG、JPEG 和 WEBP 文件", "error");
      return;
    }
    state.file = file;
    state.preview = null;
    state.questions = [];
    el.fileLabel.textContent = file.name;
    el.previewSection.hidden = true;
    setStatus("");
    setCommitStatus("");
  }

  function counts() {
    const total = state.questions.length;
    const included = state.questions.filter((question) => question.included);
    const ready = state.questions.filter(
      (question) => question.status === "ready"
    ).length;
    const review = total - ready;
    const includedReview = included.filter(
      (question) => question.status === "needs_review"
    ).length;
    return {
      total,
      included: included.length,
      ready,
      review,
      includedReview,
    };
  }

  function updateStats() {
    const stats = counts();
    el.statTotal.textContent = String(stats.total);
    el.statReady.textContent = String(stats.ready);
    el.statReview.textContent = String(stats.review);
    el.statDuplicates.textContent = String(
      state.preview ? state.preview.stats.duplicates_removed : 0
    );

    const allSelected = stats.total > 0 && stats.included === stats.total;
    el.selectAll.checked = allSelected;
    el.selectAll.indeterminate =
      stats.included > 0 && stats.included < stats.total;

    el.commit.disabled = stats.included === 0 || state.committing;
    el.commit.textContent = state.committing ? "正在导入…" : "导入到题库";
    el.commitSummary.innerHTML = `已选 <strong>${stats.included}</strong> 道${
      stats.includedReview
        ? ` · <span class="warn-text">${stats.includedReview} 道待核对</span>`
        : ""
    }`;
    el.previewMeta.textContent = `显示 ${
      state.questions.filter(
        (question) => !state.onlyReview || question.status === "needs_review"
      ).length
    } / ${stats.total} 道`;
  }

  function renderPreview() {
    const visible = state.questions.filter(
      (question) => !state.onlyReview || question.status === "needs_review"
    );

    el.previewList.innerHTML = visible.length
      ? visible
          .map((question) => {
            const warnings = Array.isArray(question.warnings)
              ? question.warnings
              : [];
            const notes = Array.isArray(question.notes) ? question.notes : [];
            const metaParts = [
              `<span>${K.esc(K.typeLabel(question.type))}</span>`,
              `<span class="${
                question.answer_source === "llm" ? "warn" : ""
              }">${
                question.answer_source === "llm" ? "DeepSeek 候选答案：" : "答案："
              }${K.esc(K.answerText(question.answer))}</span>`,
            ];
            warnings.forEach((warning) => {
              metaParts.push(`<span class="warn">${K.esc(warning)}</span>`);
            });
            notes.forEach((note) => {
              metaParts.push(`<span class="note">${K.esc(note)}</span>`);
            });

            return `<div class="preview-row${
              question.included ? "" : " is-excluded"
            }" data-client-id="${K.esc(question.client_id)}">
              <label class="preview-check">
                <input type="checkbox" data-include ${
                  question.included ? "checked" : ""
                } aria-label="导入第 ${question.number || ""} 题">
              </label>
              <span class="preview-number">${
                question.number == null ? "—" : `No.${question.number}`
              }</span>
              <div class="preview-main">
                <div class="preview-stem">${K.esc(question.stem)}</div>
                <div class="preview-meta">${metaParts.join("")}</div>
              </div>
              <div class="preview-actions">
                <button type="button" class="link-btn" data-edit>编辑</button>
              </div>
            </div>`;
          })
          .join("")
      : '<div class="empty"><h2>没有需要核对的题目</h2><p>可以直接导入，或取消“只看待核对”。</p></div>';

    updateStats();
  }

  async function parseFile() {
    if (state.parsing) return;
    if (!state.file) {
      setStatus("请先选择 Word、PDF 或图片文件", "error");
      return;
    }

    state.parsing = true;
    el.parse.disabled = true;
    setStatus("正在解析文件…");

    const formData = new FormData();
    formData.append("file", state.file, state.file.name);

    try {
      const data = await K.api("/api/import/preview", {
        method: "POST",
        body: formData,
      });
      state.preview = data;
      state.questions = data.questions.map((question) => ({
        ...question,
        included: true,
      }));
      state.onlyReview = false;
      el.onlyReview.checked = false;

      if (!el.subject.value.trim()) el.subject.value = data.suggested_subject;
      if (!el.paper.value.trim()) el.paper.value = data.suggested_paper;

      el.sourceName.textContent = data.source_file;
      const notes = [...(data.notes || [])];
      if (data.ocr) {
        notes.push(`图片 OCR：${data.ocr.model}，${data.ocr.latency_ms} ms`);
        if (data.ocr.validation && data.ocr.validation.ok) {
          notes.push(`已使用 ${data.ocr.validation.model} 做辅助校验`);
        } else if (data.ocr.validation && !data.ocr.validation.ok) {
          notes.push(`辅助校验未完成：${data.ocr.validation.error}`);
        }
      }
      el.notes.textContent = notes.join(" ");
      el.previewSection.hidden = false;
      setStatus("解析完成，请核对异常项后再导入");
      setCommitStatus("");
      renderPreview();
      updateStats();
      el.previewSection.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (error) {
      setStatus(`解析失败：${error.message}（如果刚更新过程序，请重启 start.bat）`, "error");
    } finally {
      state.parsing = false;
      el.parse.disabled = false;
    }
  }

  function editQuestion(question) {
    openEditor(question, async (updated) => {
      Object.assign(question, updated, { included: true, answer_source: "manual" });
      renderPreview();
    });
  }

  async function commit() {
    if (state.committing) return;
    const subject = el.subject.value.trim();
    const paper = el.paper.value.trim();
    if (!subject) {
      setStatus("请填写科目名称", "error");
      el.subject.focus();
      return;
    }
    if (!paper) {
      setStatus("请填写考题名称", "error");
      el.paper.focus();
      return;
    }

    const questions = state.questions
      .filter((question) => question.included)
      .map((question) => ({
        number: question.number,
        type: question.type,
        stem: question.stem,
        options: question.options,
        answer: question.answer,
        answer_source: question.answer_source || "source",
        explanation: question.explanation,
        status: question.status,
        warnings: question.warnings,
      }));
    if (!questions.length) {
      setStatus("请至少选择一道题", "error");
      return;
    }

    state.committing = true;
    el.commit.disabled = true;
    el.commit.textContent = "正在导入…";
    setStatus("正在写入题库…");
    setCommitStatus("正在写入题库…");

    try {
      const result = await K.api("/api/import/commit", {
        method: "POST",
        body: JSON.stringify({
          subject,
          paper,
          source_file: state.preview ? state.preview.source_file : "",
          source_hash: state.preview ? state.preview.source_hash : "",
          questions,
        }),
      });
      window.location.href = `/?paper=${encodeURIComponent(result.paper_id)}`;
    } catch (error) {
      state.committing = false;
      el.commit.disabled = false;
      el.commit.textContent = "导入到题库";
      setStatus(`导入失败：${error.message}`, "error");
      setCommitStatus(`导入失败：${error.message}`, "error");
      updateStats();
    }
  }

  function bindEvents() {
    el.fileInput.addEventListener("change", () => {
      setFile(el.fileInput.files[0]);
    });

    el.dropzone.addEventListener("dragover", (event) => {
      event.preventDefault();
      el.dropzone.classList.add("is-dragover");
    });
    el.dropzone.addEventListener("dragleave", () => {
      el.dropzone.classList.remove("is-dragover");
    });
    el.dropzone.addEventListener("drop", (event) => {
      event.preventDefault();
      el.dropzone.classList.remove("is-dragover");
      setFile(event.dataTransfer.files[0]);
    });

    el.parse.addEventListener("click", parseFile);
    el.commit.addEventListener("click", commit);

    el.selectAll.addEventListener("change", () => {
      state.questions.forEach((question) => {
        question.included = el.selectAll.checked;
      });
      renderPreview();
    });

    el.onlyReview.addEventListener("change", () => {
      state.onlyReview = el.onlyReview.checked;
      renderPreview();
    });

    el.previewList.addEventListener("change", (event) => {
      if (!event.target.matches("[data-include]")) return;
      const row = event.target.closest("[data-client-id]");
      if (!row) return;
      const question = state.questions.find(
        (item) => item.client_id === row.dataset.clientId
      );
      if (!question) return;
      question.included = event.target.checked;
      row.classList.toggle("is-excluded", !question.included);
      updateStats();
    });

    el.previewList.addEventListener("click", (event) => {
      if (!event.target.closest("[data-edit]")) return;
      const row = event.target.closest("[data-client-id]");
      if (!row) return;
      const question = state.questions.find(
        (item) => item.client_id === row.dataset.clientId
      );
      if (question) editQuestion(question);
    });
  }

  function init() {
    openEditor = K.setupQuestionEditor("#editor-host");
    bindEvents();
  }

  init();
})();
