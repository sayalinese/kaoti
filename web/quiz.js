(function () {
  const K = window.Kaoti;
  const root = document.getElementById("quiz-app");
  const attemptId = K.getParam("attempt");

  const state = {
    attempt: null,
    index: 0,
    selected: new Set(),
    selectionQuestionId: null,
    submitting: false,
    aiExplaining: false,
    favoriteSaving: false,
    error: "",
  };

  function renderError(message) {
    root.innerHTML = `<div class="quiz-empty">
      <h1>无法打开练习</h1>
      <p>${K.esc(message)}</p>
      <a class="btn btn-outline" href="/">返回题库</a>
    </div>`;
  }

  function backTarget() {
    if (!state.attempt) return "/";
    if (state.attempt.scope === "favorites") return "favorites.html";
    if (state.attempt.paper_id) {
      return `/?paper=${encodeURIComponent(state.attempt.paper_id)}`;
    }
    return "/";
  }

  function backLabel() {
    return state.attempt && state.attempt.scope === "favorites"
      ? "返回收藏"
      : "返回题库";
  }

  function renderQuestion() {
    const attempt = state.attempt;
    const question = attempt.questions[state.index];
    if (!question) {
      renderSummary();
      return;
    }

    if (question.answered) {
      state.selected = new Set(question.chosen || []);
    } else if (state.selectionQuestionId !== question.id) {
      state.selected = new Set();
      state.selectionQuestionId = question.id;
    }

    const multiple = question.type === "multiple";
    const chosen = new Set(question.chosen || []);
    const correct = new Set(question.correct_answer || []);
    const percent = attempt.total
      ? Math.round((attempt.answered / attempt.total) * 100)
      : 0;

    const optionsHtml = question.options
      .map((option) => {
        const isChosen = state.selected.has(option.key);
        let className = "quiz-option";
        let mark = "";
        if (question.answered) {
          if (correct.has(option.key)) {
            className += " correct-choice";
            mark = chosen.has(option.key) ? "正确答案 · 你的选择" : "正确答案";
          } else if (chosen.has(option.key)) {
            className += " wrong-choice";
            mark = "你的选择";
          }
        } else if (isChosen) {
          className += " selected";
        }

        return `<label class="${className}" data-option="${K.esc(
          option.key
        )}">
          <input type="${multiple ? "checkbox" : "radio"}" name="quiz-option" value="${K.esc(
            option.key
          )}" ${question.answered ? "disabled" : ""} ${
            isChosen ? "checked" : ""
          }>
          <span class="opt-key">${K.esc(option.key)}</span>
          <span class="opt-text">${K.esc(option.text)}</span>
          ${mark ? `<span class="opt-mark">${K.esc(mark)}</span>` : ""}
        </label>`;
      })
      .join("");

    const hasRemaining = attempt.questions.some((item) => !item.answered);
    const context =
      attempt.scope === "favorites"
        ? `<p class="quiz-context">${K.esc(question.subject_name)} / ${K.esc(
            question.paper_name
          )}</p>`
        : "";

    const feedback = question.answered
      ? `<div class="quiz-feedback">
          <div class="quiz-feedback-head">
            <p class="verdict ${
              question.is_correct ? "is-correct" : "is-wrong"
            }">${question.is_correct ? "回答正确" : "回答错误"}</p>
            <button type="button" class="btn btn-outline btn-sm" id="quiz-explain" ${
              state.aiExplaining ? "disabled" : ""
            }>${state.aiExplaining ? "DeepSeek 解析中…" : "DeepSeek 解析选项"}</button>
          </div>
          <p class="answer-line">正确答案：${K.esc(
            K.answerText(question.correct_answer)
          )}${
            question.answer_source === "llm"
              ? ' <span class="answer-source answer-source-llm">· DeepSeek 候选答案</span>'
              : ""
          } · 你的答案：${K.esc(K.answerText(question.chosen))}</p>
          ${
            question.explanation
              ? `<p class="explanation">${K.esc(question.explanation)}</p>`
              : ""
          }
          ${renderAiExplanation(question)}
        </div>`
      : "";

    const actions = question.answered
      ? `<div class="quiz-actions">
          <button type="button" class="btn btn-primary" id="quiz-next">${
            hasRemaining ? "下一题" : "查看结果"
          }</button>
        </div>`
      : `<div class="quiz-actions">
          <button type="button" class="btn btn-primary" id="quiz-submit" ${
            state.selected.size === 0 || state.submitting ? "disabled" : ""
          }>${state.submitting ? "提交中…" : "提交答案"}</button>
        </div>`;

    root.innerHTML = `<div class="quiz-top">
        <p class="quiz-scope">${K.esc(attempt.scope_label)}</p>
        <span class="quiz-progress">已答 ${attempt.answered} / ${attempt.total} · 正确 ${attempt.correct}</span>
      </div>
      <div class="quiz-progress-line"><span style="width:${percent}%"></span></div>

      <div class="quiz-question">
        <div class="quiz-question-head">
          <span class="q-number">${
            question.number == null
              ? `第 ${state.index + 1} 题`
              : `第 ${question.number} 题`
          }</span>
          <span class="q-type">${K.esc(K.typeLabel(question.type))}</span>
          <button type="button" class="btn btn-quiet btn-sm quiz-favorite${
            question.favorite ? " is-active" : ""
          }" id="quiz-favorite" ${
            state.favoriteSaving ? "disabled" : ""
          }>${question.favorite ? "已收藏" : "收藏"}</button>
        </div>
        ${context}
        <p class="q-stem">${K.esc(question.stem)}</p>
        <div class="quiz-options">${optionsHtml}</div>
        ${feedback}
        ${
          state.error
            ? `<p class="editor-status is-error">${K.esc(state.error)}</p>`
            : ""
        }
        ${actions}
      </div>`;
  }

  function renderAiExplanation(question) {
    if (!Array.isArray(question.ai_explanation) || !question.ai_explanation.length) {
      return "";
    }
    const rows = question.ai_explanation
      .map((item) => `<p><strong>${K.esc(item.key)}</strong>${K.esc(item.explanation)}</p>`)
      .join("");
    return `<div class="quiz-ai-explanation"><p class="ai-label">DeepSeek 选项解析</p>${rows}</div>`;
  }

  function renderSummary() {
    const attempt = state.attempt;
    const percent = attempt.total
      ? Math.round((attempt.correct / attempt.total) * 100)
      : 0;
    const wrong = attempt.questions.filter((question) => !question.is_correct);

    const wrongHtml = wrong.length
      ? `<div class="summary-section">
          <h2>错题与未答</h2>
          ${wrong
            .map(
              (question) => `<div class="summary-row">
                <p class="summary-stem">${
                  question.number == null ? "" : `第 ${question.number} 题 · `
                }${K.esc(question.stem)}</p>
                <p class="summary-answer is-wrong">正确答案：${K.esc(
                  K.answerText(question.correct_answer)
                )} · 你的答案：${
                  question.answered
                    ? K.esc(K.answerText(question.chosen))
                    : "未作答"
                }</p>
                ${
                  question.explanation
                    ? `<p class="summary-answer">${K.esc(
                        question.explanation
                      )}</p>`
                    : ""
                }
              </div>`
            )
            .join("")}
        </div>`
      : `<div class="summary-section">
          <h2>全部答对</h2>
          <p class="summary-answer">本次练习没有错题。</p>
        </div>`;

    root.innerHTML = `<section class="quiz-summary">
      <p class="eyebrow">Result / 练习结果</p>
      <p class="quiz-score">${attempt.correct}<small> / ${attempt.total} 正确</small></p>
      <p class="quiz-summary-meta">${K.esc(
        attempt.scope_label
      )} · 正确率 ${percent}% · 已答 ${attempt.answered} 道</p>
      ${wrongHtml}
      <div class="quiz-actions">
        <a class="btn btn-primary" href="${backTarget()}">${backLabel()}</a>
      </div>
    </section>`;
  }

  async function submitAnswer() {
    if (state.submitting || state.selected.size === 0) return;
    const attempt = state.attempt;
    const question = attempt.questions[state.index];
    if (!question || question.answered) return;

    state.submitting = true;
    state.error = "";
    const button = document.getElementById("quiz-submit");
    if (button) {
      button.disabled = true;
      button.textContent = "提交中…";
    }

    try {
      const result = await K.api(
        `/api/attempts/${encodeURIComponent(attempt.id)}/answer`,
        {
          method: "POST",
          body: JSON.stringify({
            question_id: question.id,
            chosen: [...state.selected].sort(),
          }),
        }
      );
      question.chosen = [...state.selected].sort();
      question.answered = true;
      question.is_correct = result.is_correct;
      question.correct_answer = result.correct_answer;
      question.explanation = result.explanation;
      attempt.answered = result.answered;
      attempt.correct = result.correct;
      attempt.finished = result.finished;
      renderQuestion();
    } catch (error) {
      state.error = error.message;
      renderQuestion();
    } finally {
      state.submitting = false;
    }
  }

  function nextQuestion() {
    const attempt = state.attempt;
    let nextIndex = attempt.questions.findIndex(
      (question, index) => index > state.index && !question.answered
    );
    if (nextIndex < 0) {
      nextIndex = attempt.questions.findIndex((question) => !question.answered);
    }
    if (nextIndex >= 0) {
      state.index = nextIndex;
      state.selectionQuestionId = null;
      state.error = "";
      renderQuestion();
      return;
    }
    finishAttempt();
  }

  async function finishAttempt() {
    if (!state.attempt || state.submitting) return;
    state.submitting = true;
    try {
      const data = await K.api(
        `/api/attempts/${encodeURIComponent(state.attempt.id)}/finish`,
        { method: "POST" }
      );
      state.attempt = data;
      renderSummary();
    } catch (error) {
      state.error = error.message;
      renderQuestion();
    } finally {
      state.submitting = false;
    }
  }

  async function toggleFavorite() {
    const question = state.attempt && state.attempt.questions[state.index];
    if (!question || state.favoriteSaving) return;
    state.favoriteSaving = true;
    try {
      const result = await K.api(
        `/api/questions/${encodeURIComponent(question.id)}/favorite`,
        {
          method: "POST",
          body: JSON.stringify({ favorite: !question.favorite }),
        }
      );
      question.favorite = result.favorite;
    } catch (error) {
      state.error = `收藏失败：${error.message}`;
    } finally {
      state.favoriteSaving = false;
      renderQuestion();
    }
  }

  async function explainOptions() {
    const question = state.attempt && state.attempt.questions[state.index];
    if (!question || !question.answered || state.aiExplaining) return;
    state.aiExplaining = true;
    state.error = "";
    renderQuestion();
    try {
      const result = await K.api(
        `/api/questions/${encodeURIComponent(question.id)}/explain-options`,
        { method: "POST", body: "{}" }
      );
      question.ai_explanation = result.options || [];
    } catch (error) {
      state.error = `DeepSeek 解析失败:${error.message}`;
    } finally {
      state.aiExplaining = false;
      renderQuestion();
    }
  }

  async function load() {
    if (!attemptId) {
      renderError("缺少练习编号，请从题库重新开始练习。");
      return;
    }
    try {
      const data = await K.api(
        `/api/attempts/${encodeURIComponent(attemptId)}`
      );
      state.attempt = data;
      if (data.finished) {
        renderSummary();
        return;
      }
      const index = data.questions.findIndex((question) => !question.answered);
      if (index < 0) {
        finishAttempt();
        return;
      }
      state.index = index;
      state.selectionQuestionId = null;
      renderQuestion();
    } catch (error) {
      renderError(error.message);
    }
  }

  root.addEventListener("change", (event) => {
    if (!event.target.matches('input[name="quiz-option"]')) return;
    const value = event.target.value;
    const question = state.attempt.questions[state.index];
    if (question.answered) return;

    if (question.type === "multiple") {
      if (event.target.checked) state.selected.add(value);
      else state.selected.delete(value);
    } else {
      state.selected = new Set([value]);
    }

    root.querySelectorAll(".quiz-option").forEach((label) => {
      label.classList.toggle(
        "selected",
        state.selected.has(label.dataset.option)
      );
    });
    const submit = document.getElementById("quiz-submit");
    if (submit) submit.disabled = state.selected.size === 0;
  });

  root.addEventListener("click", (event) => {
    if (event.target.closest("#quiz-favorite")) {
      toggleFavorite();
    } else if (event.target.closest("#quiz-explain")) {
      explainOptions();
    } else if (event.target.closest("#quiz-submit")) {
      submitAnswer();
    } else if (event.target.closest("#quiz-next")) {
      nextQuestion();
    }
  });

  load();
})();
