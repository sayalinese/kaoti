(function () {
  const K = window.Kaoti;

  const state = {
    tree: null,
    paperId: null,
    subject: null,
    paper: null,
    page: 1,
    pageSize: 20,
    query: "",
    type: "",
    status: "",
    favoriteOnly: false,
    questions: [],
    total: 0,
    pages: 1,
  };

  const el = {
    treeBody: document.getElementById("tree-body"),
    treeTotal: document.getElementById("tree-total"),
    loading: document.getElementById("loading"),
    emptyLibrary: document.getElementById("empty-library"),
    paperView: document.getElementById("paper-view"),
    subjectLabel: document.getElementById("subject-label"),
    paperTitle: document.getElementById("paper-title"),
    paperMeta: document.getElementById("paper-meta"),
    startQuiz: document.getElementById("start-quiz"),
    deletePaper: document.getElementById("delete-paper"),
    search: document.getElementById("search"),
    typeFilter: document.getElementById("type-filter"),
    statusFilter: document.getElementById("status-filter"),
    favoriteFilter: document.getElementById("favorite-filter"),
    resultMeta: document.getElementById("result-meta"),
    pageStatus: document.getElementById("page-status"),
    questionList: document.getElementById("question-list"),
    pagination: document.getElementById("pagination"),
    pageInfo: document.getElementById("page-info"),
    prevPage: document.getElementById("prev-page"),
    nextPage: document.getElementById("next-page"),
  };

  let openEditor = null;
  let openQuiz = null;
  let requestSeq = 0;
  let deleteTimer = null;
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

  function findPaper(paperId) {
    if (!paperId || !state.tree) return null;
    for (const subject of state.tree.subjects) {
      const paper = subject.papers.find((item) => item.id === paperId);
      if (paper) return { subject, paper };
    }
    return null;
  }

  function firstPaper() {
    if (!state.tree) return null;
    for (const subject of state.tree.subjects) {
      if (subject.papers.length) return { subject, paper: subject.papers[0] };
    }
    return null;
  }

  function renderTree() {
    if (!state.tree) return;
    const subjects = state.tree.subjects;
    el.treeTotal.textContent = `${state.tree.totals.questions} 题`;
    if (!subjects.length) {
      el.treeBody.innerHTML =
        '<p class="tree-empty">还没有导入题库。点击下方按钮录入第一份考题。</p>';
      return;
    }

    el.treeBody.innerHTML = subjects
      .map(
        (subject) => `<div class="tree-subject">
          <h3>${K.esc(subject.name)}</h3>
          ${subject.papers
            .map(
              (paper) => `<button type="button" class="tree-paper${
                paper.id === state.paperId ? " active" : ""
              }" data-paper-id="${K.esc(paper.id)}" title="可练习 ${
                paper.ready_count
              } / ${paper.question_count} 题">
                <span class="tree-paper-name">${K.esc(paper.name)}</span>
                <span class="tree-paper-count">${paper.question_count}</span>
              </button>`
            )
            .join("")}
        </div>`
      )
      .join("");
  }

  function updateHeader() {
    if (!state.paper || !state.subject) {
      el.paperView.hidden = true;
      return;
    }
    el.paperView.hidden = false;
    el.subjectLabel.textContent = `科目 / ${state.subject.name}`;
    el.paperTitle.textContent = state.paper.name;

    const reviewCount = Math.max(
      0,
      state.paper.question_count - state.paper.ready_count
    );
    el.paperMeta.innerHTML = [
      `<span>共 ${state.paper.question_count} 题</span>`,
      `<span>可练习 ${state.paper.ready_count} 题</span>`,
      `<span>收藏 ${state.paper.favorite_count} 题</span>`,
      reviewCount
        ? `<span class="meta-warn">${reviewCount} 道待核对</span>`
        : "",
    ].join("");

    el.startQuiz.disabled = state.paper.ready_count === 0;
    el.startQuiz.textContent =
      state.paper.ready_count === 0 ? "暂无可练习题" : "开始练习";
    resetDeleteButton();
  }

  function resetDeleteButton() {
    clearTimeout(deleteTimer);
    el.deletePaper.dataset.armed = "";
    el.deletePaper.classList.remove("is-armed");
    el.deletePaper.textContent = "删除考题";
  }

  function clearFilters() {
    state.query = "";
    state.type = "";
    state.status = "";
    state.favoriteOnly = false;
    el.search.value = "";
    el.typeFilter.value = "";
    el.statusFilter.value = "";
    el.favoriteFilter.checked = false;
  }

  function renderQuestions() {
    if (!state.questions.length) {
      const hasFilter =
        state.query || state.type || state.status || state.favoriteOnly;
      el.questionList.innerHTML = `<div class="empty">
        <h2>${hasFilter ? "没有符合条件的题目" : "这份考题还没有题目"}</h2>
        <p>${
          hasFilter
            ? "换一个关键词或清除筛选试试。"
            : "可以重新导入，或在导入时核对题目是否被识别。"
        }</p>
        ${
          hasFilter
            ? '<button type="button" class="btn btn-outline btn-sm" data-action="reset">清除筛选</button>'
            : ""
        }
      </div>`;
      return;
    }
    el.questionList.innerHTML = state.questions
      .map((question) => K.questionCardHtml(question))
      .join("");
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

  async function loadQuestions() {
    if (!state.paperId) return;
    const seq = ++requestSeq;
    el.loading.hidden = false;
    el.loading.textContent = "正在载入题目…";
    el.pagination.hidden = true;

    const params = new URLSearchParams({
      paper_id: state.paperId,
      page: String(state.page),
      page_size: String(state.pageSize),
    });
    if (state.query) params.set("q", state.query);
    if (state.type) params.set("type", state.type);
    if (state.status) params.set("status", state.status);
    if (state.favoriteOnly) params.set("favorite", "1");

    try {
      const data = await K.api(`/api/questions?${params.toString()}`);
      if (seq !== requestSeq) return;
      if (
        data.pagination.total > 0 &&
        state.page > data.pagination.pages
      ) {
        state.page = data.pagination.pages;
        loadQuestions();
        return;
      }

      state.questions = data.questions;
      state.total = data.pagination.total;
      state.pages = data.pagination.pages;
      state.page = data.pagination.page;
      renderQuestions();
      renderPagination();
      el.resultMeta.textContent = `共 ${state.total} 题`;
      el.loading.hidden = true;
      el.emptyLibrary.hidden = true;
      el.paperView.hidden = false;
    } catch (error) {
      if (seq !== requestSeq) return;
      el.loading.hidden = true;
      setStatus(`载入失败：${error.message}`, "error");
    }
  }

  async function selectPaper(paperId, options = {}) {
    const found = findPaper(paperId);
    if (!found) return;
    state.paperId = found.paper.id;
    state.subject = found.subject;
    state.paper = found.paper;
    state.page = 1;
    if (options.resetFilters !== false) clearFilters();
    renderTree();
    updateHeader();
    if (options.updateUrl !== false) {
      const url = `/?paper=${encodeURIComponent(found.paper.id)}`;
      window.history.replaceState({}, "", url);
    }
    await loadQuestions();
  }

  async function refreshTree() {
    try {
      const tree = await K.api("/api/library");
      state.tree = tree;
      renderTree();
      const found = findPaper(state.paperId);
      if (found) {
        state.subject = found.subject;
        state.paper = found.paper;
        updateHeader();
      }
    } catch (error) {
      setStatus(`刷新题库失败：${error.message}`, "error");
    }
  }

  async function loadInitial(preferredPaperId) {
    el.loading.hidden = false;
    el.loading.textContent = "正在载入题库…";
    try {
      state.tree = await K.api("/api/library");
      renderTree();
      const found =
        findPaper(preferredPaperId) || findPaper(state.paperId) || firstPaper();
      if (!found) {
        el.loading.hidden = true;
        el.paperView.hidden = true;
        el.emptyLibrary.hidden = false;
        el.resultMeta.textContent = "";
        return;
      }
      await selectPaper(found.paper.id, {
        resetFilters: true,
        updateUrl: true,
      });
    } catch (error) {
      el.loading.hidden = true;
      setStatus(`载入失败：${error.message}`, "error");
    }
  }

  async function toggleFavorite(question) {
    try {
      const result = await K.api(
        `/api/questions/${encodeURIComponent(question.id)}/favorite`,
        {
          method: "POST",
          body: JSON.stringify({ favorite: !question.favorite }),
        }
      );
      question.favorite = result.favorite;
      if (state.favoriteOnly) {
        await loadQuestions();
      } else {
        renderQuestions();
      }
      await refreshTree();
    } catch (error) {
      setStatus(`收藏失败：${error.message}`, "error");
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
      if (index >= 0) state.questions[index] = { ...state.questions[index], ...saved };
      renderQuestions();
      await refreshTree();
      if (
        (state.status && saved.status !== state.status) ||
        (state.favoriteOnly && !saved.favorite)
      ) {
        await loadQuestions();
      }
      setStatus("题目已保存");
    });
  }

  async function deletePaper() {
    if (!state.paperId) return;
    if (el.deletePaper.dataset.armed !== "1") {
      el.deletePaper.dataset.armed = "1";
      el.deletePaper.classList.add("is-armed");
      el.deletePaper.textContent = "再次点击确认删除";
      clearTimeout(deleteTimer);
      deleteTimer = setTimeout(resetDeleteButton, 4000);
      return;
    }

    const paperId = state.paperId;
    resetDeleteButton();
    try {
      await K.api(`/api/papers/${encodeURIComponent(paperId)}`, {
        method: "DELETE",
      });
      state.paperId = null;
      state.paper = null;
      state.subject = null;
      state.tree = await K.api("/api/library");
      renderTree();
      const found = firstPaper();
      if (found) {
        await selectPaper(found.paper.id, { resetFilters: true });
      } else {
        window.history.replaceState({}, "", "/");
        el.paperView.hidden = true;
        el.emptyLibrary.hidden = false;
        el.loading.hidden = true;
        el.resultMeta.textContent = "";
      }
    } catch (error) {
      setStatus(`删除失败：${error.message}`, "error");
    }
  }

  function bindEvents() {
    el.treeBody.addEventListener("click", (event) => {
      const button = event.target.closest("[data-paper-id]");
      if (!button) return;
      selectPaper(button.dataset.paperId);
    });

    el.search.addEventListener(
      "input",
      K.debounce(() => {
        state.query = el.search.value.trim();
        state.page = 1;
        loadQuestions();
      }, 260)
    );

    el.typeFilter.addEventListener("change", () => {
      state.type = el.typeFilter.value;
      state.page = 1;
      loadQuestions();
    });

    el.statusFilter.addEventListener("change", () => {
      state.status = el.statusFilter.value;
      state.page = 1;
      loadQuestions();
    });

    el.favoriteFilter.addEventListener("change", () => {
      state.favoriteOnly = el.favoriteFilter.checked;
      state.page = 1;
      loadQuestions();
    });

    el.prevPage.addEventListener("click", () => {
      if (state.page <= 1) return;
      state.page -= 1;
      loadQuestions();
    });

    el.nextPage.addEventListener("click", () => {
      if (state.page >= state.pages) return;
      state.page += 1;
      loadQuestions();
    });

    el.questionList.addEventListener("click", (event) => {
      const action = event.target.closest("[data-action]");
      if (action && action.dataset.action === "reset") {
        clearFilters();
        state.page = 1;
        loadQuestions();
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

    el.startQuiz.addEventListener("click", () => {
      if (!state.paper) return;
      openQuiz({
        subtitle: `${state.subject.name} / ${state.paper.name} · 可练习 ${state.paper.ready_count} 题`,
        allowFavorites: true,
        onStart: async ({ count, types, favoritesOnly }) => {
          const result = await K.api("/api/quiz", {
            method: "POST",
            body: JSON.stringify({
              paper_id: state.paperId,
              count,
              types,
              favorites_only: favoritesOnly,
            }),
          });
          window.location.href = `quiz.html?attempt=${encodeURIComponent(
            result.id
          )}`;
        },
      });
    });

    el.deletePaper.addEventListener("click", deletePaper);
  }

  function init() {
    openEditor = K.setupQuestionEditor("#editor-host");
    openQuiz = K.setupQuizDialog("#quiz-host");
    bindEvents();
    loadInitial(K.getParam("paper"));
  }

  init();
})();
