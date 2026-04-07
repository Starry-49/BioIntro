const READER_BANK_PATH = "./data/question-bank.json";
const READER_KB_PATH = "./data/knowledge-base/biointro-core.json";

const readerState = { bank: null, kb: null, activeModule: null, activeQuestion: null };

function query(name) { return new URLSearchParams(window.location.search).get(name); }

async function readJson(path) { const r = await fetch(path); if (!r.ok) throw new Error(`Failed to fetch ${path}`); return r.json(); }

function renderModuleTree() {
  const container = document.getElementById("moduleTree");
  const entries = readerState.kb.entries.slice(0, 50);
  container.innerHTML = entries.map(entry => `
    <button class="tree-item ${entry.id === readerState.activeModule ? "active" : ""}" data-module="${entry.id}">
      <strong>${entry.title}</strong>
      <div class="muted">${entry.module}</div>
    </button>
  `).join("");
  container.querySelectorAll("[data-module]").forEach(b => b.addEventListener("click", () => {
    readerState.activeModule = b.dataset.module; readerState.activeQuestion = null; renderReader();
  }));
}

function renderQuestionTree() {
  const container = document.getElementById("questionTree");
  const related = readerState.bank.questions.filter(q => {
    if (readerState.activeQuestion) return q.id === readerState.activeQuestion;
    return (q.knowledgeRefs || []).includes(readerState.activeModule);
  });
  container.innerHTML = related.length
    ? related.map(q => `<button class="tree-item ${q.id === readerState.activeQuestion ? "active" : ""}" data-question="${q.id}"><strong>${q.id}</strong><div class="muted">${q.prompt.substring(0, 40)}...</div></button>`).join("")
    : `<div class="empty-state"><p class="muted">\u5f53\u524d\u6a21\u5757\u6682\u65e0\u7ed1\u5b9a\u9898\u76ee\u3002</p></div>`;
  container.querySelectorAll("[data-question]").forEach(b => b.addEventListener("click", () => {
    readerState.activeQuestion = b.dataset.question; renderReader();
  }));
}

function renderModuleSummary(entry) {
  const related = readerState.bank.questions.filter(q => (q.knowledgeRefs || []).includes(entry.id));
  return `
    <article class="reader-card">
      <div class="badge-row"><span class="tag tag-brand">${entry.module}</span><span class="tag tag-accent">${related.length} \u9053\u5173\u8054\u9898</span></div>
      <h3>${entry.title}</h3>
      <p>${entry.summary}</p>
      <div class="reader-summary"><strong>\u6838\u5fc3\u5173\u952e\u8bcd\uff1a</strong>${(entry.keywords || []).join("\u3001") || "\u672a\u6807\u6ce8"}</div>
      <div class="reader-list">${(entry.facts || []).map(fact => `
        <article class="knowledge-card"><h3>${fact.question}</h3><p><strong>\u7b54\u6848\uff1a</strong>${fact.answer}</p><p class="muted">${fact.explanation}</p></article>
      `).join("")}</div>
    </article>
  `;
}

function renderQuestionDetail(question) {
  return `
    <article class="reader-card">
      <div class="badge-row"><span class="tag tag-brand">${question.source}</span><span class="tag tag-accent">${question.topicName}</span><span class="tag tag-dark">${question.type}</span></div>
      <span class="status-pill">${question.id}</span>
      <h3>${question.prompt}</h3>
      ${(question.options || []).length ? `<div class="question-options">${question.options.map(o => `<div class="option"><strong>${o.key || "-"}</strong> \u00b7 ${o.text}</div>`).join("")}</div>` : ""}
      <div class="analysis-box">
        <p><strong>\u7b54\u6848\uff1a</strong>${question.answer || "\u672a\u8bb0\u5f55"}</p>
        <p><strong>\u89e3\u6790\uff1a</strong>${question.analysis || "\u6682\u65e0"}</p>
      </div>
    </article>
  `;
}

function renderReader() {
  renderModuleTree(); renderQuestionTree();
  const module = readerState.kb.entries.find(e => e.id === readerState.activeModule) || readerState.kb.entries[0];
  const question = readerState.bank.questions.find(q => q.id === readerState.activeQuestion);
  document.getElementById("readerTitle").textContent = question ? question.prompt : module.title;
  document.getElementById("readerSubtitle").textContent = question ? `\u9898\u76ee\u8be6\u60c5 \u00b7 ${question.id}` : `\u77e5\u8bc6\u6a21\u5757 \u00b7 ${module.module}`;
  document.getElementById("readerContent").innerHTML = question ? renderQuestionDetail(question) : renderModuleSummary(module);
}

async function initReader() {
  try {
    const [bank, kb] = await Promise.all([readJson(READER_BANK_PATH), readJson(READER_KB_PATH)]);
    readerState.bank = bank; readerState.kb = kb;
    readerState.activeModule = query("module") || kb.entries[0].id;
    readerState.activeQuestion = query("question");
    if (readerState.activeQuestion) {
      const q = bank.questions.find(q => q.id === readerState.activeQuestion);
      if (q && q.knowledgeRefs && q.knowledgeRefs.length) readerState.activeModule = q.knowledgeRefs[0];
    }
    renderReader();
  } catch (error) {
    console.error(error);
    document.getElementById("readerContent").innerHTML = `<section class="empty-state"><h3>Reader \u521d\u59cb\u5316\u5931\u8d25</h3><p class="muted">\u8bf7\u786e\u8ba4 JSON \u5df2\u751f\u6210\u3002</p></section>`;
  }
}

initReader();
