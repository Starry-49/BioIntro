const READER_BANK_PATH = "./data/question-bank.json";
const READER_KB_PATH = "./data/knowledge-base/biointro-core.json";

const MODULE_DEFS = [
  { id: "genomics-core", name: "\u5f15\u8a00\u53ca\u57fa\u56e0\u7ec4\u4fe1\u606f\u5b66", ref: "genomics-core" },
  { id: "transcriptomics-core", name: "\u8f6c\u5f55\u7ec4\u4fe1\u606f\u5b66", ref: "transcriptomics-core" },
  { id: "proteomics-core", name: "\u86cb\u767d\u7ec4\u4fe1\u606f\u5b66", ref: "proteomics-core" },
  { id: "biomolecular-network-core", name: "\u751f\u7269\u5206\u5b50\u7f51\u7edc", ref: "biomolecular-network-core" },
  { id: "cadd-core", name: "\u8ba1\u7b97\u673a\u8f85\u52a9\u836f\u7269\u53d1\u73b0", ref: "cadd-core" },
];

const MODULE_LABEL_MAP = {
  "\u5f15\u8a00\u53ca\u57fa\u56e0\u7ec4\u4fe1\u606f\u5b66": "genomics-core",
  "\u8f6c\u5f55\u7ec4\u4fe1\u606f\u5b66": "transcriptomics-core",
  "\u86cb\u767d\u7ec4\u4fe1\u606f\u5b66": "proteomics-core",
  "\u751f\u7269\u5206\u5b50\u7f51\u7edc": "biomolecular-network-core",
  "\u8ba1\u7b97\u673a\u8f85\u52a9\u836f\u7269\u53d1\u73b0": "cadd-core",
};

const readerState = {
  bank: null,
  kb: null,
  activeModuleId: null,   // one of MODULE_DEFS[].id
  activeEntryId: null,     // specific KB entry within a module
  activeQuestion: null,
};

function query(name) { return new URLSearchParams(window.location.search).get(name); }
async function readJson(path) { const r = await fetch(path); if (!r.ok) throw new Error(`Failed to fetch ${path}`); return r.json(); }

function getModuleEntries(moduleId) {
  const def = MODULE_DEFS.find(m => m.id === moduleId);
  if (!def) return [];
  return (readerState.kb.entries || []).filter(e => MODULE_LABEL_MAP[e.module] === moduleId);
}

function getModuleQuestions(moduleId) {
  const def = MODULE_DEFS.find(m => m.id === moduleId);
  if (!def) return [];
  return (readerState.bank.questions || []).filter(q => (q.knowledgeRefs || []).includes(def.ref));
}

function renderModuleTree() {
  const container = document.getElementById("moduleTree");

  const html = MODULE_DEFS.map(mod => {
    const entries = getModuleEntries(mod.id);
    const questions = getModuleQuestions(mod.id);
    const isActive = mod.id === readerState.activeModuleId;
    return `
      <button class="tree-item ${isActive ? "active" : ""}" data-module-id="${mod.id}">
        <strong>${mod.name}</strong>
        <div class="muted">${entries.length} \u6761\u77e5\u8bc6 \u00b7 ${questions.length} \u9898</div>
      </button>
    `;
  }).join("");

  container.innerHTML = html;

  container.querySelectorAll("[data-module-id]").forEach(b => {
    b.addEventListener("click", () => {
      readerState.activeModuleId = b.dataset.moduleId;
      readerState.activeEntryId = null;
      readerState.activeQuestion = null;
      renderReader();
    });
  });
}

function renderQuestionTree() {
  const container = document.getElementById("questionTree");

  if (readerState.activeQuestion) {
    const q = readerState.bank.questions.find(q => q.id === readerState.activeQuestion);
    container.innerHTML = q
      ? `<button class="tree-item active" data-question="${q.id}"><strong>${q.id}</strong><div class="muted">${q.prompt.substring(0, 40)}...</div></button>`
      : "";
    container.querySelectorAll("[data-question]").forEach(b => {
      b.addEventListener("click", () => { readerState.activeQuestion = b.dataset.question; renderReader(); });
    });
    return;
  }

  const questions = getModuleQuestions(readerState.activeModuleId);

  container.innerHTML = questions.length
    ? questions.map(q => `
        <button class="tree-item" data-question="${q.id}">
          <strong>${q.id}</strong>
          <div class="muted">${q.prompt.substring(0, 40)}...</div>
        </button>
      `).join("")
    : `<div class="empty-state"><p class="muted">\u5f53\u524d\u6a21\u5757\u6682\u65e0\u9898\u76ee\u3002</p></div>`;

  container.querySelectorAll("[data-question]").forEach(b => {
    b.addEventListener("click", () => { readerState.activeQuestion = b.dataset.question; renderReader(); });
  });
}

function renderModuleOverview(moduleId) {
  const def = MODULE_DEFS.find(m => m.id === moduleId);
  const entries = getModuleEntries(moduleId);
  const questions = getModuleQuestions(moduleId);
  const totalFacts = entries.reduce((sum, e) => sum + (e.facts || []).length, 0);

  // Group entries by unique title (deduplicate near-duplicates)
  const uniqueTitles = [];
  const seen = new Set();
  for (const entry of entries) {
    const key = entry.title.substring(0, 30);
    if (!seen.has(key)) {
      seen.add(key);
      uniqueTitles.push(entry);
    }
    if (uniqueTitles.length >= 20) break;
  }

  return `
    <article class="reader-card">
      <div class="badge-row">
        <span class="tag tag-brand">${def.name}</span>
        <span class="tag tag-accent">${entries.length} \u6761\u77e5\u8bc6</span>
        <span class="tag tag-dark">${totalFacts} \u4e2a\u4e8b\u5b9e</span>
        <span class="tag tag-dark">${questions.length} \u9898</span>
      </div>
      <h3>${def.name}</h3>
      <p class="panel-subtitle">\u5171 ${entries.length} \u6761\u77e5\u8bc6\u6761\u76ee\uff0c${totalFacts} \u4e2a\u4e8b\u5b9e\u70b9\uff0c\u5173\u8054 ${questions.length} \u9053\u9898\u76ee\u3002\u70b9\u51fb\u4e0b\u65b9\u6761\u76ee\u67e5\u770b\u8be6\u60c5\u3002</p>
    </article>
    <div class="reader-list">
      ${uniqueTitles.map(entry => `
        <article class="knowledge-card" style="cursor:pointer" data-entry-id="${entry.id}">
          <h3>${entry.title}</h3>
          <p class="panel-subtitle">${entry.summary}</p>
          <div class="badge-row">
            <span class="tag tag-dark">${(entry.facts || []).length} facts</span>
            <span class="tag tag-dark">${(entry.keywords || []).slice(0, 4).join("\u3001")}</span>
          </div>
        </article>
      `).join("")}
      ${entries.length > 20 ? `<p class="muted" style="text-align:center">\u2026 \u8fd8\u6709 ${entries.length - 20} \u6761\u77e5\u8bc6\u6761\u76ee</p>` : ""}
    </div>
  `;
}

function renderEntrySummary(entry) {
  return `
    <article class="reader-card">
      <div class="badge-row">
        <span class="tag tag-brand">${entry.module}</span>
        <button class="tag tag-accent" style="cursor:pointer" id="backToModule">\u2190 \u8fd4\u56de\u6a21\u5757</button>
      </div>
      <h3>${entry.title}</h3>
      <p>${entry.summary}</p>
      <div class="reader-summary"><strong>\u6838\u5fc3\u5173\u952e\u8bcd\uff1a</strong>${(entry.keywords || []).join("\u3001") || "\u672a\u6807\u6ce8"}</div>
      <div class="reader-list">${(entry.facts || []).map(fact => `
        <article class="knowledge-card">
          <h3>${fact.question}</h3>
          <p><strong>\u7b54\u6848\uff1a</strong>${fact.answer}</p>
          <p class="muted">${fact.explanation}</p>
        </article>
      `).join("")}</div>
    </article>
  `;
}

function renderQuestionDetail(question) {
  return `
    <article class="reader-card">
      <div class="badge-row">
        <span class="tag tag-brand">${question.source}</span>
        <span class="tag tag-accent">${question.topicName}</span>
        <span class="tag tag-dark">${question.type}</span>
        <button class="tag tag-accent" style="cursor:pointer" id="backToModule">\u2190 \u8fd4\u56de\u6a21\u5757</button>
      </div>
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
  renderModuleTree();
  renderQuestionTree();

  const content = document.getElementById("readerContent");
  const titleEl = document.getElementById("readerTitle");
  const subtitleEl = document.getElementById("readerSubtitle");

  // Priority: question detail > entry detail > module overview
  if (readerState.activeQuestion) {
    const question = readerState.bank.questions.find(q => q.id === readerState.activeQuestion);
    if (question) {
      titleEl.textContent = question.prompt;
      subtitleEl.textContent = `\u9898\u76ee\u8be6\u60c5 \u00b7 ${question.id}`;
      content.innerHTML = renderQuestionDetail(question);
      bindBackButton();
      return;
    }
  }

  if (readerState.activeEntryId) {
    const entry = readerState.kb.entries.find(e => e.id === readerState.activeEntryId);
    if (entry) {
      titleEl.textContent = entry.title;
      subtitleEl.textContent = `\u77e5\u8bc6\u6761\u76ee \u00b7 ${entry.module}`;
      content.innerHTML = renderEntrySummary(entry);
      bindBackButton();
      return;
    }
  }

  const def = MODULE_DEFS.find(m => m.id === readerState.activeModuleId) || MODULE_DEFS[0];
  titleEl.textContent = def.name;
  subtitleEl.textContent = `\u77e5\u8bc6\u6a21\u5757\u6982\u89c8`;
  content.innerHTML = renderModuleOverview(def.id);

  // Bind entry card clicks
  content.querySelectorAll("[data-entry-id]").forEach(card => {
    card.addEventListener("click", () => {
      readerState.activeEntryId = card.dataset.entryId;
      readerState.activeQuestion = null;
      renderReader();
    });
  });
}

function bindBackButton() {
  const btn = document.getElementById("backToModule");
  if (btn) {
    btn.addEventListener("click", () => {
      readerState.activeEntryId = null;
      readerState.activeQuestion = null;
      renderReader();
    });
  }
}

async function initReader() {
  try {
    const [bank, kb] = await Promise.all([readJson(READER_BANK_PATH), readJson(READER_KB_PATH)]);
    readerState.bank = bank;
    readerState.kb = kb;

    // Resolve initial state from URL params
    const qModule = query("module");
    const qQuestion = query("question");

    if (qQuestion) {
      readerState.activeQuestion = qQuestion;
      const q = bank.questions.find(q => q.id === qQuestion);
      if (q && q.knowledgeRefs && q.knowledgeRefs.length) {
        // Map knowledgeRef to module id
        const ref = q.knowledgeRefs[0];
        const mod = MODULE_DEFS.find(m => m.ref === ref);
        readerState.activeModuleId = mod ? mod.id : MODULE_DEFS[0].id;
      } else {
        readerState.activeModuleId = MODULE_DEFS[0].id;
      }
    } else if (qModule) {
      // qModule could be a module id or an entry id
      const mod = MODULE_DEFS.find(m => m.id === qModule);
      if (mod) {
        readerState.activeModuleId = mod.id;
      } else {
        // It's an entry id — find which module it belongs to
        const entry = kb.entries.find(e => e.id === qModule);
        if (entry) {
          const modId = MODULE_LABEL_MAP[entry.module];
          readerState.activeModuleId = modId || MODULE_DEFS[0].id;
          readerState.activeEntryId = qModule;
        } else {
          readerState.activeModuleId = MODULE_DEFS[0].id;
        }
      }
    } else {
      readerState.activeModuleId = MODULE_DEFS[0].id;
    }

    renderReader();
  } catch (error) {
    console.error(error);
    document.getElementById("readerContent").innerHTML = `<section class="empty-state"><h3>Reader \u521d\u59cb\u5316\u5931\u8d25</h3><p class="muted">\u8bf7\u786e\u8ba4 JSON \u5df2\u751f\u6210\u3002</p></section>`;
  }
}

initReader();
