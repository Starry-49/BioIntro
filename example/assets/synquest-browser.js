(function () {
  const LETTERS = ["A", "B", "C", "D"];

  function slugify(text) {
    return String(text || "").trim().toLowerCase()
      .replace(/[^\w\u4e00-\u9fff]+/g, "-").replace(/^-+|-+$/g, "") || "entry";
  }

  function shuffle(array, rng) {
    const items = [...array];
    for (let i = items.length - 1; i > 0; i--) {
      const j = Math.floor(rng() * (i + 1));
      [items[i], items[j]] = [items[j], items[i]];
    }
    return items;
  }

  function makeSeededRandom(seed) {
    let v = seed % 2147483647;
    if (v <= 0) v += 2147483646;
    return function () { v = (v * 16807) % 2147483647; return (v - 1) / 2147483646; };
  }

  function collectFallbackDistractors(entries, correct) {
    const pool = [];
    entries.forEach(e => {
      (e.distractors || []).forEach(c => { if (c && c !== correct) pool.push(c); });
      (e.facts || []).forEach(f => { if (f.answer && f.answer !== correct) pool.push(f.answer); });
    });
    return pool;
  }

  function buildOptions(correct, fact, entries, rng) {
    const distractors = [...(fact.distractors || [])].filter(Boolean);
    const fallback = collectFallbackDistractors(entries, correct);
    shuffle(fallback, rng).forEach(c => {
      if (c !== correct && !distractors.includes(c) && distractors.length < 3) distractors.push(c);
    });
    while (distractors.length < 3) distractors.push(`\u4e0d\u6b63\u786e\u7684\u5907\u9009\u9879${distractors.length + 1}`);
    const options = shuffle([correct, ...distractors.slice(0, 3)], rng);
    return options.map((text, i) => ({ key: LETTERS[i], text }));
  }

  function generateQuestions({ entries, count = 6, seed = Date.now(), existingIds = [] }) {
    const rng = makeSeededRandom(seed);
    const facts = [];
    entries.forEach(entry => { (entry.facts || []).forEach(fact => facts.push({ entry, fact })); });
    const selected = shuffle(facts, rng).slice(0, Math.min(count, facts.length));
    const existing = new Set(existingIds);
    const questions = [];

    selected.forEach(({ entry, fact }, index) => {
      const correct = fact.answer;
      const options = buildOptions(correct, fact, entries, rng);
      const answerOption = options.find(o => o.text === correct);
      const baseId = `sq-${slugify(entry.id || entry.title)}-${String(index + 1).padStart(3, "0")}`;
      let finalId = baseId;
      let serial = 1;
      while (existing.has(finalId)) { serial++; finalId = `${baseId}-${serial}`; }
      existing.add(finalId);

      questions.push({
        id: finalId, year: null, source: "SynQuest",
        prompt: fact.question || `\u4e0b\u5217\u54ea\u9879\u5173\u4e8e\u201c${entry.title}\u201d\u7684\u8bf4\u6cd5\u662f\u6b63\u786e\u7684\uff1f`,
        type: fact.type || "single_choice",
        topic: slugify(entry.id || entry.title),
        topicName: entry.title,
        difficulty: Number(fact.difficulty || 2),
        options, answer: answerOption ? answerOption.key : "A",
        analysis: fact.explanation || correct,
        images: { question: "", note: "" }, pdfPage: null,
        knowledgeRefs: [entry.id || slugify(entry.title)],
        tags: Array.from(new Set([slugify(entry.id || entry.title), "synquest", ...(entry.keywords || [])])),
        origin: "generated-browser"
      });
    });
    return questions;
  }

  window.SynQuestBrowser = { generateQuestions };
})();
