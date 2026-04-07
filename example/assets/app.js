const BANK_PATH = "./data/question-bank.json";
const KB_PATH = "./data/knowledge-base/biointro-core.json";
const GENERATED_STORAGE_KEY = "biointro-generated-bank";
const ANSWER_STORAGE_KEY = "biointro-answer-records";

const SOURCE_LABELS = { SynQuest: "SynQuest", "SynQuest-Figure": "SynQuest-Figure", Previous: "Previous" };
const ORIGIN_LABELS = { "semantic-generated": "semantic", "figure-context-generated": "figure", "previous-curated": "curated", "generated-browser": "browser" };

const state = {
  bank: null, kb: null, backendGeneratedQuestions: [], generatedQuestions: [], answers: {},
  filters: { source: "all", topic: "all", type: "all", search: "", module: "all" },
  quiz: { active: false, questions: [], index: 0, answers: {}, checked: {}, score: null }
};

const $ = s => document.querySelector(s);
const getGeneratedQuestions = () => [...state.backendGeneratedQuestions, ...state.generatedQuestions];
const getEmbeddedGeneratedQuestions = () => (state.bank?.questions || []).filter(q => q.source === "SynQuest" || q.source === "SynQuest-Figure");
const getAllQuestions = () => [...(state.bank?.questions || []), ...getGeneratedQuestions()];
const slugify = t => String(t || "").trim().toLowerCase().replace(/[^\w\u4e00-\u9fff]+/g, "-").replace(/^-+|-+$/g, "") || "entry";
const normalizeText = t => String(t || "").trim().toLowerCase().replace(/\s+/g, "");
const getSourceLabel = s => SOURCE_LABELS[s] || s || "Unknown";
const getOriginLabel = o => ORIGIN_LABELS[o] || o || "";
const escapeHtml = t => String(t || "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");

function getTopicName(topicId) {
  const bt = (state.bank?.meta?.topics || []).find(t => t.id === topicId);
  if (bt) return bt.name;
  const m = (state.kb?.entries || []).find(e => slugify(e.id || e.title) === topicId);
  return m ? m.title : topicId;
}

function readQueryFilters() {
  const p = new URLSearchParams(window.location.search);
  if (p.get("source")) state.filters.source = p.get("source");
  if (p.get("topic")) state.filters.topic = p.get("topic");
  if (p.get("type")) state.filters.type = p.get("type");
  if (p.get("search")) state.filters.search = p.get("search");
  if (p.get("module")) state.filters.module = p.get("module");
}

function syncQueryFilters() {
  const p = new URLSearchParams();
  if (state.filters.source !== "all") p.set("source", state.filters.source);
  if (state.filters.topic !== "all") p.set("topic", state.filters.topic);
  if (state.filters.type !== "all") p.set("type", state.filters.type);
  if (state.filters.search) p.set("search", state.filters.search);
  if (state.filters.module !== "all") p.set("module", state.filters.module);
  window.history.replaceState({}, "", `${window.location.pathname}${p.toString() ? `?${p}` : ""}`);
}

function loadGeneratedQuestions() {
  try { state.generatedQuestions = JSON.parse(localStorage.getItem(GENERATED_STORAGE_KEY) || "[]"); } catch { state.generatedQuestions = []; }
}
function persistGeneratedQuestions() { localStorage.setItem(GENERATED_STORAGE_KEY, JSON.stringify(state.generatedQuestions)); }
function loadAnswerRecords() {
  try { state.answers = JSON.parse(localStorage.getItem(ANSWER_STORAGE_KEY) || "{}"); } catch { state.answers = {}; }
}
function persistAnswerRecords() { localStorage.setItem(ANSWER_STORAGE_KEY, JSON.stringify(state.answers)); }

async function loadJson(path) { const r = await fetch(path); if (!r.ok) throw new Error(`Failed to load ${path}`); return r.json(); }

function buildSourceFilters() {
  const container = $("#sourceFilterList");
  const counts = getAllQuestions().reduce((a, q) => { const s = q.source || "Unknown"; a[s] = (a[s] || 0) + 1; return a; }, {});
  const sources = ["all", ...Object.keys(counts)];
  container.innerHTML = sources.map(s => {
    const active = s === state.filters.source ? "active" : "";
    const label = s === "all" ? "\u5168\u90e8\u6765\u6e90" : getSourceLabel(s);
    const count = s === "all" ? getAllQuestions().length : counts[s];
    return `<button class="chip ${active}" data-source="${s}"><span>${label}</span><span class="chip-count">${count}</span></button>`;
  }).join("");
  container.querySelectorAll("[data-source]").forEach(b => b.addEventListener("click", () => { state.filters.source = b.dataset.source; render(); }));
}

function populateSelects() {
  const topicSelect = $("#topicSelect"), typeSelect = $("#typeSelect"), searchInput = $("#searchInput");
  const topics = (state.bank?.meta?.topics || []).map(t => ({ id: t.id, name: t.name }));
  const allTopics = [...topics];
  getGeneratedQuestions().forEach(q => { if (!allTopics.some(t => t.id === q.topic)) allTopics.push({ id: q.topic, name: q.topicName || q.topic }); });
  topicSelect.innerHTML = ['<option value="all">\u5168\u90e8\u4e3b\u9898</option>'].concat(allTopics.map(t => `<option value="${t.id}">${t.name}</option>`)).join("");
  topicSelect.value = state.filters.topic;
  const types = ["all", ...new Set(getAllQuestions().map(q => q.type || "single_choice"))];
  typeSelect.innerHTML = types.map(t => `<option value="${t}">${t === "all" ? "\u5168\u90e8\u9898\u578b" : t}</option>`).join("");
  typeSelect.value = state.filters.type;
  searchInput.value = state.filters.search;
}

function getFilteredQuestions() {
  const search = normalizeText(state.filters.search);
  return getAllQuestions().filter(q => {
    if (state.filters.source !== "all" && q.source !== state.filters.source) return false;
    if (state.filters.topic !== "all" && q.topic !== state.filters.topic) return false;
    if (state.filters.type !== "all" && q.type !== state.filters.type) return false;
    if (state.filters.module !== "all" && !(q.knowledgeRefs || []).includes(state.filters.module)) return false;
    if (!search) return true;
    const hay = normalizeText([q.prompt, q.answer, q.analysis, q.topicName, ...(q.tags || []), ...(q.options || []).map(o => o.text)].join(" "));
    return hay.includes(search);
  });
}

function sampleQuestions(pool, count) {
  const items = [...pool];
  for (let i = items.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [items[i], items[j]] = [items[j], items[i]]; }
  return items.slice(0, Math.min(count, items.length));
}

function updateStats(filtered) {
  $("#statQuestionCount").textContent = getAllQuestions().length;
  $("#statKnowledgeCount").textContent = state.kb?.entries?.length || 0;
  $("#statGeneratedCount").textContent = getEmbeddedGeneratedQuestions().length + getGeneratedQuestions().length;
  $("#statFilteredCount").textContent = filtered.length;
  const records = Object.values(state.answers);
  $("#statAnsweredCount").textContent = records.filter(r => r.answer).length;
  $("#statCorrectCount").textContent = records.filter(r => r.checked && r.correct).length;
}

// Deduplicate KB entries for display: group by module, show first 10 unique modules
function getDisplayModules() {
  const seen = new Map();
  (state.kb?.entries || []).forEach(entry => {
    const mod = entry.module || "Unknown";
    if (!seen.has(mod)) seen.set(mod, { module: mod, entries: [], totalFacts: 0 });
    seen.get(mod).entries.push(entry);
    seen.get(mod).totalFacts += (entry.facts || []).length;
  });
  return Array.from(seen.values());
}

function renderKnowledgeBase(filtered) {
  const container = $("#knowledgeList");
  const modules = getDisplayModules();
  container.innerHTML = modules.map(mod => {
    const entryIds = mod.entries.map(e => e.id);
    const questions = getAllQuestions().filter(q => (q.knowledgeRefs || []).some(r => entryIds.includes(r)));
    return `
      <article class="knowledge-card" data-module="${mod.module}">
        <div class="question-header"><div>
          <div class="badge-row"><span class="tag tag-brand">${mod.module}</span><span class="tag tag-accent">${mod.entries.length} \u6761\u77e5\u8bc6</span><span class="tag tag-dark">${questions.length} \u9898</span></div>
          <h3>${mod.module}</h3>
        </div></div>
        <p class="panel-subtitle">${mod.totalFacts} \u4e2a\u4e8b\u5b9e\u70b9</p>
        <div class="panel-actions">
          <button class="button button-primary" data-action="generate-module" data-module-name="${mod.module}">生成 3 题</button>
          <a class="button button-secondary" href="reader.html?module=${encodeURIComponent(mod.entries[0]?.id || '')}">Study Reader</a>
        </div>
      </article>
    `;
  }).join("");

  container.querySelectorAll("[data-action='generate-module']").forEach(b => {
    b.addEventListener("click", () => { generateQuestionsFromModule(b.dataset.moduleName, 3); });
  });
  $("#activeModuleLabel").textContent = state.filters.module === "all" ? "\u5168\u90e8\u77e5\u8bc6\u6a21\u5757" : state.filters.module;
}

function getStoredAnswerRecord(qid) { return state.answers[qid] || { answer: "", checked: false, correct: false }; }

function renderChoiceInputs(question, storedAnswer, inputName) {
  const isMultiple = question.type === "multiple_choice";
  const selectedKeys = isMultiple ? (storedAnswer ? storedAnswer.split("") : []) : [];
  return `<div class="answer-options">${(question.options || []).map(o => `
    <label class="answer-option">
      <input type="${isMultiple ? "checkbox" : "radio"}" ${isMultiple ? "" : `name="${inputName}"`} data-question-id="${question.id}" value="${o.key}"
        ${isMultiple ? (selectedKeys.includes(o.key) ? "checked" : "") : (storedAnswer === o.key ? "checked" : "")}>
      <span class="answer-option-key">${o.key || "-"}</span>
      <span class="answer-option-text">${o.text}</span>
    </label>
  `).join("")}</div>`;
}

function renderQuestionCard(question) {
  const record = getStoredAnswerRecord(question.id);
  const statusText = !record.checked ? "\u672a\u63d0\u4ea4" : record.correct ? "\u5df2\u5224\u5b9a \u00b7 \u6b63\u786e" : "\u5df2\u5224\u5b9a \u00b7 \u9519\u8bef";
  const tags = [
    `<span class="tag tag-brand">${getSourceLabel(question.source)}</span>`,
    question.origin ? `<span class="tag tag-origin">${getOriginLabel(question.origin)}</span>` : "",
    `<span class="tag tag-accent">${question.topicName || getTopicName(question.topic)}</span>`,
    `<span class="tag tag-dark">${question.type}</span>`,
  ].filter(Boolean).join("");

  const feedback = record.checked ? `<div class="practice-feedback ${record.correct ? "correct" : "wrong"}">
    <p><strong>${record.correct ? "\u56de\u7b54\u6b63\u786e" : "\u56de\u7b54\u9519\u8bef"}</strong></p>
    <p><strong>\u4f60\u7684\u7b54\u6848\uff1a</strong>${record.answer || "\u672a\u586b\u5199"}</p>
    <p><strong>\u6807\u51c6\u7b54\u6848\uff1a</strong>${question.answer || "\u672a\u8bb0\u5f55"}</p>
    <p><strong>\u89e3\u6790\uff1a</strong>${question.analysis || "\u6682\u65e0"}</p>
  </div>` : "";

  return `
    <article class="question-card">
      <div class="question-header"><div class="badge-row">${tags}</div><span class="status-pill">${question.id}</span></div>
      <h3 class="question-title">${question.prompt}</h3>
      <div class="practice-shell">
        <div class="practice-title-row"><strong>\u9009\u9879\u4e0e\u4f5c\u7b54</strong><span class="status-pill">${statusText}</span></div>
        ${renderChoiceInputs(question, record.answer || "", `answer-${question.id}`)}
      </div>
      ${feedback}
      <div class="panel-actions">
        <button class="button button-primary" data-action="submit-answer" data-id="${question.id}">\u63d0\u4ea4\u7b54\u6848</button>
        <button class="button button-secondary" data-action="reset-answer" data-id="${question.id}">\u6e05\u7a7a\u4f5c\u7b54</button>
        <button class="button button-secondary" data-action="toggle-analysis" data-id="${question.id}">\u67e5\u770b\u7b54\u6848</button>
      </div>
      <div class="analysis-box hidden" id="analysis-${question.id}">
        <p><strong>\u6807\u51c6\u7b54\u6848\uff1a</strong>${question.answer || "\u672a\u8bb0\u5f55"}</p>
        <p><strong>\u89e3\u6790\uff1a</strong>${question.analysis || "\u6682\u65e0"}</p>
      </div>
    </article>
  `;
}

function renderQuestionList(filtered) {
  const container = $("#questionList"), title = $("#resultHeadline");
  title.textContent = `\u9898\u5e93\u6d4f\u89c8 \u00b7 ${filtered.length} \u9898`;
  if (!filtered.length) { container.innerHTML = `<section class="empty-state"><h3>\u5f53\u524d\u7b5b\u9009\u6761\u4ef6\u4e0b\u6ca1\u6709\u9898\u76ee</h3></section>`; return; }
  container.innerHTML = filtered.map(renderQuestionCard).join("");
  bindQuestionListInteractions();
}

function getQuestionById(id) { return getAllQuestions().find(q => q.id === id); }
function collectCardAnswer(question) {
  if (question.type === "multiple_choice") return Array.from(document.querySelectorAll(`input[data-question-id="${question.id}"]:checked`)).map(i => i.value).sort().join("");
  const selected = document.querySelector(`input[data-question-id="${question.id}"]:checked`);
  return selected ? selected.value : "";
}
function isAnswerCorrect(question, answer) { return normalizeText(answer) === normalizeText(question.answer); }
function submitCardAnswer(qid) {
  const q = getQuestionById(qid); if (!q) return;
  const answer = collectCardAnswer(q);
  state.answers[qid] = { answer, checked: true, correct: isAnswerCorrect(q, answer), updatedAt: new Date().toISOString() };
  persistAnswerRecords(); renderQuestionList(getFilteredQuestions()); updateStats(getFilteredQuestions());
}
function resetCardAnswer(qid) { delete state.answers[qid]; persistAnswerRecords(); renderQuestionList(getFilteredQuestions()); updateStats(getFilteredQuestions()); }

function bindQuestionListInteractions() {
  const c = $("#questionList");
  c.querySelectorAll("[data-action='toggle-analysis']").forEach(b => b.addEventListener("click", () => {
    const box = document.getElementById(`analysis-${b.dataset.id}`);
    box.classList.toggle("hidden");
    b.textContent = box.classList.contains("hidden") ? "\u67e5\u770b\u7b54\u6848" : "\u6536\u8d77\u7b54\u6848";
  }));
  c.querySelectorAll("[data-action='submit-answer']").forEach(b => b.addEventListener("click", () => submitCardAnswer(b.dataset.id)));
  c.querySelectorAll("[data-action='reset-answer']").forEach(b => b.addEventListener("click", () => resetCardAnswer(b.dataset.id)));
  c.querySelectorAll("input[data-question-id]").forEach(i => i.addEventListener("change", () => {
    const q = getQuestionById(i.dataset.questionId); if (!q) return;
    const answer = collectCardAnswer(q);
    state.answers[q.id] = { ...getStoredAnswerRecord(q.id), answer, updatedAt: new Date().toISOString() };
    persistAnswerRecords(); updateStats(getFilteredQuestions());
  }));
}

// Quiz
function renderQuiz() {
  const shell = $("#quizShell");
  if (!state.quiz.active) { shell.classList.add("hidden"); return; }
  shell.classList.remove("hidden");
  const q = state.quiz.questions[state.quiz.index];
  const stored = state.quiz.answers[q.id] || "";
  const checked = state.quiz.checked[q.id];
  const total = state.quiz.questions.length;
  const progress = `${Math.round(((state.quiz.index + 1) / total) * 100)}%`;

  shell.innerHTML = `
    <div class="quiz-headline"><div><h3>\u62bd\u9898\u6d4b\u8bd5</h3><p class="muted">\u7b2c ${state.quiz.index + 1} / ${total} \u9898 \u00b7 ${q.topicName || getTopicName(q.topic)}</p></div>
      ${state.quiz.score !== null ? `<span class="score-badge">\u5f97\u5206 ${state.quiz.score} / ${total}</span>` : ""}
    </div>
    <div class="progress-bar"><div class="progress-value" style="width:${progress};"></div></div>
    <article class="reader-card">
      <div class="badge-row"><span class="tag tag-brand">${q.source}</span><span class="tag tag-dark">${q.type}</span></div>
      <h3>${q.prompt}</h3>
      ${renderChoiceInputs({ ...q, id: "quiz-option" }, stored, "quizOption")}
      ${checked ? `<div class="quiz-result"><p><strong>${checked.correct ? "\u7ed3\u679c\uff1a\u6b63\u786e" : "\u7ed3\u679c\uff1a\u9519\u8bef"}</strong></p><p><strong>\u6807\u51c6\u7b54\u6848\uff1a</strong>${q.answer}</p><p><strong>\u89e3\u6790\uff1a</strong>${q.analysis || "\u6682\u65e0"}</p></div>` : ""}
    </article>
    <div class="quiz-controls">
      <button class="button button-secondary" id="quizPrev" ${state.quiz.index === 0 ? "disabled" : ""}>\u4e0a\u4e00\u9898</button>
      <button class="button button-secondary" id="quizCheck">\u68c0\u67e5\u672c\u9898</button>
      <button class="button button-primary" id="quizNext">${state.quiz.index === total - 1 ? "\u5b8c\u6210\u6d4b\u9a8c" : "\u4e0b\u4e00\u9898"}</button>
      <button class="button button-danger" id="quizClose">\u7ed3\u675f\u6d4b\u9a8c</button>
    </div>
  `;

  const collectQuizAnswer = () => {
    if (q.type === "multiple_choice") return Array.from(document.querySelectorAll(".answer-option input:checked")).map(i => i.value).sort().join("");
    const sel = document.querySelector(".answer-option input:checked"); return sel ? sel.value : "";
  };
  const saveQuizAnswer = () => { state.quiz.answers[q.id] = collectQuizAnswer(); };

  $("#quizPrev").addEventListener("click", () => { saveQuizAnswer(); state.quiz.index--; renderQuiz(); });
  $("#quizCheck").addEventListener("click", () => {
    saveQuizAnswer(); const a = state.quiz.answers[q.id] || "";
    state.quiz.checked[q.id] = { answer: a, correct: isAnswerCorrect(q, a) }; renderQuiz();
  });
  $("#quizNext").addEventListener("click", () => {
    saveQuizAnswer();
    if (state.quiz.index === total - 1) {
      let score = 0;
      state.quiz.questions.forEach(qq => { const a = state.quiz.answers[qq.id] || ""; const c = isAnswerCorrect(qq, a); state.quiz.checked[qq.id] = { answer: a, correct: c }; if (c) score++; });
      state.quiz.score = score; renderQuiz(); return;
    }
    state.quiz.index++; renderQuiz();
  });
  $("#quizClose").addEventListener("click", () => { state.quiz = { active: false, questions: [], index: 0, answers: {}, checked: {}, score: null }; renderQuiz(); });
}

function startQuiz() {
  const pool = getFilteredQuestions();
  const count = Math.max(1, Number($("#quizCount").value || 10));
  const selected = sampleQuestions(pool, count);
  if (!selected.length) { alert("\u5f53\u524d\u7b5b\u9009\u7ed3\u679c\u4e3a\u7a7a"); return; }
  state.quiz = { active: true, questions: selected, index: 0, answers: {}, checked: {}, score: null };
  renderQuiz(); $("#quizShell").scrollIntoView({ behavior: "smooth", block: "start" });
}

function generateQuestionsFromModule(moduleName, count) {
  const entries = moduleName === "all" ? (state.kb?.entries || []) : (state.kb?.entries || []).filter(e => e.module === moduleName);
  const generated = window.SynQuestBrowser.generateQuestions({
    entries, count, seed: Date.now(), existingIds: getAllQuestions().map(q => q.id)
  });
  state.generatedQuestions = [...generated, ...state.generatedQuestions];
  persistGeneratedQuestions(); render();
}

function exportGeneratedQuestions() {
  const payload = { meta: { title: "BioIntro Browser Export", exportedAt: new Date().toISOString(), count: state.generatedQuestions.length }, questions: state.generatedQuestions };
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a"); link.href = url; link.download = "biointro-generated.json"; link.click();
  URL.revokeObjectURL(url);
}

function clearGeneratedQuestions() {
  if (!state.generatedQuestions.length) return;
  if (!confirm("\u786e\u8ba4\u6e05\u7a7a\u751f\u6210\u9898\uff1f")) return;
  state.generatedQuestions = []; persistGeneratedQuestions(); render();
}

function clearAnswerRecords() {
  if (!Object.keys(state.answers).length) return;
  if (!confirm("\u786e\u8ba4\u6e05\u7a7a\u7b54\u9898\u8bb0\u5f55\uff1f")) return;
  state.answers = {}; persistAnswerRecords(); render();
}

function bindStaticEvents() {
  $("#searchInput").addEventListener("input", e => { state.filters.search = e.target.value; render(); });
  $("#topicSelect").addEventListener("change", e => { state.filters.topic = e.target.value; render(); });
  $("#typeSelect").addEventListener("change", e => { state.filters.type = e.target.value; render(); });
  $("#startQuizButton").addEventListener("click", startQuiz);
  $("#randomBrowseButton").addEventListener("click", () => {
    const sampled = sampleQuestions(getFilteredQuestions(), Number($("#quizCount").value || 10));
    $("#resultHeadline").textContent = `\u968f\u673a\u9884\u89c8 \u00b7 ${sampled.length} \u9898`;
    $("#questionList").innerHTML = sampled.map(renderQuestionCard).join("");
    bindQuestionListInteractions();
  });
  $("#generateButton").addEventListener("click", () => {
    const moduleId = $("#generatorModule").value;
    const count = Number($("#generatorCount").value || 4);
    generateQuestionsFromModule(moduleId, count);
  });
  $("#exportButton").addEventListener("click", exportGeneratedQuestions);
  $("#clearGeneratedButton").addEventListener("click", clearGeneratedQuestions);
  $("#clearAnswerButton").addEventListener("click", clearAnswerRecords);
}

function renderGeneratorModuleOptions() {
  const select = $("#generatorModule");
  const modules = getDisplayModules();
  select.innerHTML = ['<option value="all">\u4ece\u5168\u90e8\u77e5\u8bc6\u6a21\u5757\u751f\u6210</option>']
    .concat(modules.map(m => `<option value="${m.module}">${m.module}</option>`)).join("");
}

function render() {
  syncQueryFilters(); buildSourceFilters(); populateSelects(); renderGeneratorModuleOptions();
  const filtered = getFilteredQuestions();
  updateStats(filtered); renderKnowledgeBase(filtered); renderQuestionList(filtered); renderQuiz();
}

async function init() {
  try {
    const [bank, kb] = await Promise.all([loadJson(BANK_PATH), loadJson(KB_PATH)]);
    state.bank = bank; state.kb = kb;
    state.backendGeneratedQuestions = [];
    loadGeneratedQuestions(); loadAnswerRecords(); readQueryFilters(); bindStaticEvents(); render();
  } catch (error) {
    console.error(error);
    $("#questionList").innerHTML = `<section class="empty-state"><h3>\u9875\u9762\u521d\u59cb\u5316\u5931\u8d25</h3><p class="muted">\u8bf7\u786e\u8ba4 JSON \u6587\u4ef6\u5df2\u751f\u6210\u3002</p></section>`;
  }
}

init();
