(function () {
  const K = window.Kaoti;

  const state = {
    page: 1,
    pageSize: 20,
    query: "",
    type: "",
    questions: [],
    total: 0,
    pages: 1,
    allFavorites: 0,
  };

  const el = {
    meta: document.getElementById("favorites-meta"),
    quizButton: document.getElementById("quiz-favorites"),
    search: document.getElementById("search"),
    typeFilter: document.getElementById("type-filter"),
    resultMeta: document.getElementById("result-meta"),
    pageStatus: document.getElementById("page-status"),
    loading: document.getElementById("loading"),
    empty: document.getElementById("empty-favorites"),
    list: document.getElementById("question-list"),
    pagination: document.getElementById("pagination"),
    pageInfo: document.getElementById("page-info"),
    prevPage: document.getElementById("prev-page"),
    nextPage: document.getElementById("next-page"),
  };

  let openEditor = null;
  let openQuiz = null;
  let requestSeq = 0;
  let statusTimer = null;

  function setStatus(text, tone = "") {
    clearTimeout(statusTimer);
    el.pageStatus.textContent = text;
    el.pageStatus.className = "editor-status";
    if (tone) el.pageStatus.classList.add(`is-${tone}`);
    if (text && tone !== "error") {
      statusTimer = setTimeout(() => {
        el.pageStatus.textContent = "";
        el.pageStatus.className = "editor-status";
      }, 4000);
    }
  }

  function renderPagination() {
    if (state.pages <= 1) {
      el.pagination.hidden = true;
      return;
    }
    el.pagination.hidden = false;
    el.pageInfo.textContent = `第 ${state.page} / ${state.pages} 页`;
    el.prevPage.disabled = state.page <= 1;
    el.nextPage.disabled = state.page >= state.pages;
  }

  function renderQuestions() {
    if (!state.questions.length) {
      const hasFilter = state.query || state.type;
      el.list.innerHTML = `<div class="empty">
        <h2>${hasFilter ? "没有符合条件的收藏" : "还没有收藏"}</h2>
        <p>${
          hasFilter
            ? "换一个关键词或清除筛选试试。"
            : "在题库里点击题目右上角的“收藏”，就会出现在这里。"
        }</p>
        ${
          hasFilter
            ? '<button type="button" class="btn btn-outline btn-sm" data-action="reset">清除筛选</button>'
            : '<a class="btn btn-outline" href="/">去题库看看</a>'
        }
      </div>`;
      return;
    }
    el.list.innerHTML = state.questions
      .map((question) =>
        K.questionCardHtml(question, {
          showContext: true,
          showEdit: true,
        })
      )
      .join("");
  }

  async function load() {
    const seq = ++requestSeq;
    el.loading.hidden = false;
    el.loading.textContent = "正在载入收藏…";
    el.pagination.hidden = true;

    const params = new URLSearchParams({
      favorite: "1",
      page: String(state.page),
      page_size: String(state.pageSize),
    });
    if (state.query) params.set("q", state.query);
    if (state.type) params.set("type", state.type);

    try {
      const data = await K.api(`/api/questions?${params.toString()}`);
      if (seq !== requestSeq) return;
      if (data.pagination.total > 0 && state.page > data.pagination.pages) {
        state.page = data.pagination.pages;
        load();
        return;
      }

      state.questions = data.questions;
      state.total = data.pagination.total;
      state.pages = data.pagination.pages;
      state.page = data.pagination.page;
      el.loading.hidden = true;
      el.resultMeta.textContent = `共 ${state.total} 道`;
      el.meta.textContent = state.query || state.type
        ? `筛选出 ${state.total} 道收藏`
        : `共 ${state.total} 道收藏`;
      renderQuestions();
      renderPagination();
    } catch (error) {
      if (seq !== requestSeq) return;
      el.loading.hidden = true;
      setStatus(`载入失败：${error.message}`, "error");
    }
  }

  async function refreshTotals() {
    try {
      const data = await K.api("/api/library");
      state.allFavorites = data.totals.favorites;
      el.quizButton.disabled = state.allFavorites === 0;
    } catch (error) {
      setStatus(`读取收藏数量失败：${error.message}`, "error");
    }
  }

  async function toggleFavorite(question) {
    try {
      await K.api(
        `/api/questions/${encodeURIComponent(question.id)}/favorite`,
        {
          method: "POST",
          body: JSON.stringify({ favorite: false }),
        }
      );
      await load();
      await refreshTotals();
    } catch (error) {
      setStatus(`取消收藏失败：${error.message}`, "error");
    }
  }

  function editQuestion(question) {
    openEditor(question, async (updated) => {
      const saved = await K.api(
        `/api/questions/${encodeURIComponent(question.id)}`,
        {
          method: "PUT",
          body: JSON.stringify({
            type: updated.type,
            stem: updated.stem,
            options: updated.options,
            answer: updated.answer,
            explanation: updated.explanation,
          }),
        }
      );
      const index = state.questions.findIndex(
        (item) => item.id === question.id
      );
      if (index >= 0) {
        state.questions[index] = { ...state.questions[index], ...saved };
      }
      renderQuestions();
      setStatus("题目已保存");
    });
  }

  function bindEvents() {
    el.search.addEventListener(
      "input",
      K.debounce(() => {
        state.query = el.search.value.trim();
        state.page = 1;
        load();
      }, 260)
    );

    el.typeFilter.addEventListener("change", () => {
      state.type = el.typeFilter.value;
      state.page = 1;
      load();
    });

    el.prevPage.addEventListener("click", () => {
      if (state.page <= 1) return;
      state.page -= 1;
      load();
    });

    el.nextPage.addEventListener("click", () => {
      if (state.page >= state.pages) return;
      state.page += 1;
      load();
    });

    el.list.addEventListener("click", (event) => {
      const reset = event.target.closest('[data-action="reset"]');
      if (reset) {
        state.query = "";
        state.type = "";
        el.search.value = "";
        el.typeFilter.value = "";
        state.page = 1;
        load();
        return;
      }
      const button = event.target.closest("[data-id]");
      if (!button) return;
      const question = state.questions.find(
        (item) => item.id === button.dataset.id
      );
      if (!question) return;
      if (button.dataset.action === "favorite") {
        toggleFavorite(question);
      } else if (button.dataset.action === "edit") {
        editQuestion(question);
      }
    });

    el.quizButton.addEventListener("click", () => {
      if (state.allFavorites === 0) return;
      openQuiz({
        subtitle: `全部收藏题目 · ${state.allFavorites} 道`,
        allowFavorites: false,
        forceFavorites: true,
        onStart: async ({ count, types }) => {
          const result = await K.api("/api/quiz", {
            method: "POST",
            body: JSON.stringify({
              count,
              types,
              favorites_only: true,
            }),
          });
          window.location.href = `quiz.html?attempt=${encodeURIComponent(
            result.id
          )}`;
        },
      });
    });
  }

  function init() {
    openEditor = K.setupQuestionEditor("#editor-host");
    openQuiz = K.setupQuizDialog("#quiz-host");
    bindEvents();
    load();
    refreshTotals();
  }

  init();
})();
