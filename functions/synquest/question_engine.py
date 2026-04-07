"""Reusable question synthesis with knowledge facts plus style retrieval."""

from __future__ import annotations

import json
import random
import re
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional, Union

try:
    import jieba
except ImportError:
    jieba = None

try:
    from rank_bm25 import BM25Okapi
except ImportError:
    BM25Okapi = None

try:
    from rapidfuzz import fuzz
except ImportError:
    fuzz = None

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
except ImportError:
    TfidfVectorizer = None
    cosine_similarity = None

try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    SentenceTransformer = None


LETTERS = ["A", "B", "C", "D"]
GENERIC_PROMPT_PATTERNS = (
    re.compile(r'^关于["\u201c\u201d]?.+["\u201c\u201d]?，下列哪项'),
    re.compile(r'^下列哪项关于["\u201c\u201d]?.+["\u201c\u201d]?'),
    re.compile(r'^根据知识库内容，下列哪个'),
)
PROMPT_FOCUS_PATTERNS = (
    re.compile(r'^关于["\u201c\u201d]?(?P<focus>.+?)["\u201c\u201d]?，下列哪项表述正确[？?]?$'),
    re.compile(r'^关于["\u201c\u201d]?(?P<focus>.+?)["\u201c\u201d]?，下列哪个时间或数值是正确的[？?]?$'),
    re.compile(r'^关于["\u201c\u201d]?(?P<focus>.+?)["\u201c\u201d]?，下列哪一项术语或缩写是正确的[？?]?$'),
    re.compile(r'^关于["\u201c\u201d]?(?P<focus>.+?)["\u201c\u201d]?，下列哪项命令或参数写法是正确的[？?]?$'),
    re.compile(r'^\u201c(?P<focus>.+?)\u201d对应的内容是[？?]?$'),
)
NOISY_FOCUS_PATTERNS = (
    re.compile(r"^第\d+讲"),
    re.compile(r"^输出文档"),
    re.compile(r"^回顾"),
    re.compile(r"^拓展阅读"),
    re.compile(r"^实践练习"),
    re.compile(r"^思考题"),
    re.compile(r"^截图来自"),
    re.compile(r"^[a-zA-Z]$"),
)
NOISY_TEXT_MARKERS = (
    "输出文档", "向下翻页", "截图来自", "拓展阅读", "实践练习", "思考题", "回顾",
)
BAD_OPTION_TOKENS = {"#", "*", "-", "--", "不确定"}


def ensure_style_packages() -> None:
    missing = []
    if jieba is None:
        missing.append("jieba")
    if BM25Okapi is None:
        missing.append("rank-bm25")
    if fuzz is None:
        missing.append("rapidfuzz")
    if TfidfVectorizer is None or cosine_similarity is None:
        missing.append("scikit-learn")
    if missing:
        raise RuntimeError(f"Style retrieval requires: {', '.join(missing)}")


def ensure_semantic_packages() -> None:
    if SentenceTransformer is None:
        raise RuntimeError("Semantic retrieval requires sentence-transformers.")


@lru_cache(maxsize=2)
def load_sentence_model(model_name: str) -> Any:
    ensure_semantic_packages()
    return SentenceTransformer(model_name)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "-", text.strip().lower())
    return slug.strip("-") or "entry"


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def tokenize_text(text: str) -> list[str]:
    cleaned = normalize_text(text)
    if not cleaned:
        return []
    tokens: list[str] = []
    if jieba is not None:
        for token in jieba.lcut_for_search(cleaned):
            token = token.strip().lower()
            if len(token) >= 2:
                tokens.append(token)
    for token in re.findall(r"[A-Za-z][A-Za-z0-9\-/+.]{1,}", cleaned):
        tokens.append(token.lower())
    for token in re.findall(r"[\u4e00-\u9fff]{2,}", cleaned):
        if len(token) <= 12:
            tokens.append(token)
    deduped: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        if token not in seen:
            seen.add(token)
            deduped.append(token)
    return deduped


def informative_tokens(text: str) -> set[str]:
    return set(tokenize_text(text))


def looks_like_low_information_text(text: str) -> bool:
    lowered = normalize_text(text).lower()
    if any(marker in lowered for marker in ("email:", "wx:", "qq:", "tel", "phone", "http://", "https://", "www.")):
        return True
    if re.search(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b", lowered):
        return True
    return False


def contains_ocr_noise(text: str) -> bool:
    return bool(re.search(r"[�]", str(text or "")))


def extract_prompt_focus(prompt: str) -> str:
    normalized = normalize_text(prompt)
    for pattern in PROMPT_FOCUS_PATTERNS:
        match = pattern.match(normalized)
        if match:
            return normalize_text(match.group("focus"))
    return ""


def looks_like_noisy_focus(text: str) -> bool:
    focus = normalize_text(text)
    if not focus or len(focus) <= 1:
        return True
    if any(pattern.search(focus) for pattern in NOISY_FOCUS_PATTERNS):
        return True
    if any(marker in focus for marker in NOISY_TEXT_MARKERS):
        return True
    return False


def bad_option_text(text: str) -> bool:
    normalized = normalize_text(text)
    if not normalized or normalized in BAD_OPTION_TOKENS or len(normalized) <= 1:
        return True
    return contains_ocr_noise(normalized)


def answer_signature(text: str) -> str:
    value = normalize_text(text)
    lowered = value.lower()
    if re.fullmatch(r"\d{2,4}(?:年|月|日)?", value) or re.fullmatch(r"\d+(?:\.\d+)?\s*(?:bp|kb|mb|gb|cm|cr|%|倍|次|个)?", lowered):
        return "numeric"
    if any(marker in value for marker in ("--", ">", "|", "/", ".py", ".sh", "nohup", "conda")):
        return "command"
    if re.fullmatch(r"[A-Z][A-Za-z0-9\-/+. ]{1,24}", value):
        return "acronym"
    if re.fullmatch(r"[\u4e00-\u9fff]{2,12}", value):
        return "short_cjk"
    if len(value) <= 32:
        return "short_phrase"
    return "sentence"


def signature_compatible(correct_signature: str, candidate_signature: str) -> bool:
    if correct_signature == candidate_signature:
        return True
    compatible = {
        "short_cjk": {"short_phrase", "acronym"},
        "short_phrase": {"short_cjk", "acronym"},
        "numeric": set(),
        "acronym": {"short_phrase", "short_cjk"},
        "command": set(),
        "sentence": {"short_phrase"},
    }
    return candidate_signature in compatible.get(correct_signature, set())


def question_quality_issues(question: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    prompt = normalize_text(question.get("prompt", ""))
    analysis = normalize_text(question.get("analysis", ""))
    options = [normalize_text(option.get("text", "")) for option in question.get("options", [])]
    correct_text = next(
        (option["text"] for option in question.get("options", []) if option.get("key") == question.get("answer")),
        "",
    )
    correct_text = normalize_text(correct_text)
    focus = extract_prompt_focus(prompt)

    if not prompt or len(prompt) < 8:
        issues.append("prompt-too-short")
    if contains_ocr_noise(prompt) or contains_ocr_noise(analysis):
        issues.append("ocr-noise")
    if focus and looks_like_noisy_focus(focus):
        issues.append("noisy-focus")
    if any(bad_option_text(option) for option in options):
        issues.append("bad-option")
    if analysis and looks_like_low_information_text(analysis):
        issues.append("low-information-analysis")
    return issues


def question_passes_quality_filter(question: dict[str, Any]) -> bool:
    return not question_quality_issues(question)


def is_fact_usable(entry: dict[str, Any], fact: dict[str, Any]) -> bool:
    answer = normalize_text(fact.get("answer", ""))
    if not answer or len(answer) > 96:
        return False
    if looks_like_low_information_text(answer):
        return False
    title_terms = informative_tokens(str(entry.get("title", "")))
    answer_terms = informative_tokens(answer)
    if title_terms and answer_terms and len(title_terms & answer_terms) / max(1, len(title_terms)) >= 0.8 and len(answer_terms) <= len(title_terms) + 2:
        return False
    return True


def entry_similarity(source_entry: dict[str, Any], candidate_entry: dict[str, Any]) -> int:
    score = 0
    if source_entry.get("module") and source_entry.get("module") == candidate_entry.get("module"):
        score += 3
    source_terms = set(source_entry.get("keywords") or []) | informative_tokens(str(source_entry.get("title", "")))
    candidate_terms = set(candidate_entry.get("keywords") or []) | informative_tokens(str(candidate_entry.get("title", "")))
    score += len(source_terms & candidate_terms)
    return score


def is_generic_prompt(prompt: str, entry_title: str) -> bool:
    normalized = normalize_text(prompt)
    if not normalized:
        return True
    return any(pattern.search(normalized) for pattern in GENERIC_PROMPT_PATTERNS)


def question_to_document(question: dict[str, Any]) -> str:
    parts = [
        question.get("prompt", ""),
        question.get("analysis", ""),
        question.get("topicName", ""),
        question.get("topic", ""),
        " ".join(question.get("tags", [])),
        " ".join(option.get("text", "") for option in question.get("options", [])),
    ]
    return normalize_text(" ".join(part for part in parts if part))


def normalize_scores(values: list[float]) -> list[float]:
    if not values:
        return []
    low = min(values)
    high = max(values)
    if abs(high - low) < 1e-9:
        return [1.0 if high > 0 else 0.0 for _ in values]
    return [(value - low) / (high - low) for value in values]


@dataclass
class StyleMatch:
    question: dict[str, Any]
    score: float
    bm25: float
    tfidf: float
    fuzzy: float
    semantic: float = 0.0


class QuestionStyleIndex:
    def __init__(self, questions: list[dict[str, Any]], *, semantic_model: Optional[str] = None) -> None:
        ensure_style_packages()
        self.questions = questions
        self.documents = [question_to_document(question) for question in questions]
        self.prompts = [normalize_text(question.get("prompt", "")) for question in questions]
        self.tokens = [tokenize_text(document) for document in self.documents]
        self.bm25 = BM25Okapi(self.tokens)
        self.vectorizer = TfidfVectorizer(
            tokenizer=tokenize_text, token_pattern=None, lowercase=False, ngram_range=(1, 2),
        )
        self.tfidf_matrix = self.vectorizer.fit_transform(self.documents)
        self.semantic_model_name = semantic_model
        self.semantic_model = None
        self.semantic_matrix = None
        if semantic_model and self.documents:
            self.semantic_model = load_sentence_model(semantic_model)
            self.semantic_matrix = self.semantic_model.encode(
                self.documents, convert_to_numpy=True, normalize_embeddings=True, show_progress_bar=False,
            )

    def search(self, query_text: str, *, top_k: int = 5, desired_type: Optional[str] = None) -> list[StyleMatch]:
        if not self.questions:
            return []
        query_tokens = tokenize_text(query_text)
        if not query_tokens:
            return []

        bm25_raw = list(self.bm25.get_scores(query_tokens))
        tfidf_raw = list(cosine_similarity(self.vectorizer.transform([query_text]), self.tfidf_matrix)[0])
        fuzzy_raw = [float(fuzz.token_set_ratio(query_text, prompt)) / 100.0 for prompt in self.prompts]

        bm25_scores = normalize_scores(bm25_raw)
        tfidf_scores = normalize_scores(tfidf_raw)
        fuzzy_scores = normalize_scores(fuzzy_raw)
        semantic_scores = [0.0 for _ in self.questions]
        if self.semantic_model is not None and self.semantic_matrix is not None:
            query_embedding = self.semantic_model.encode(
                [query_text], convert_to_numpy=True, normalize_embeddings=True, show_progress_bar=False,
            )
            semantic_raw = list(cosine_similarity(query_embedding, self.semantic_matrix)[0])
            semantic_scores = normalize_scores([float(value) for value in semantic_raw])

        matches: list[StyleMatch] = []
        for index, question in enumerate(self.questions):
            type_bonus = 0.08 if desired_type and question.get("type") == desired_type else 0.0
            if self.semantic_model is not None:
                score = (
                    0.24 * bm25_scores[index] + 0.18 * tfidf_scores[index]
                    + 0.12 * fuzzy_scores[index] + 0.38 * semantic_scores[index] + type_bonus
                )
            else:
                score = 0.45 * bm25_scores[index] + 0.35 * tfidf_scores[index] + 0.20 * fuzzy_scores[index] + type_bonus
            matches.append(StyleMatch(
                question=question, score=score,
                bm25=bm25_scores[index], tfidf=tfidf_scores[index],
                fuzzy=fuzzy_scores[index], semantic=semantic_scores[index],
            ))

        matches.sort(key=lambda match: match.score, reverse=True)
        return matches[:top_k]

    def max_prompt_similarity(self, prompt: str) -> float:
        normalized = normalize_text(prompt)
        if not normalized:
            return 0.0
        return max((float(fuzz.token_set_ratio(normalized, existing)) for existing in self.prompts if existing), default=0.0)


def question_query_text(entry: dict[str, Any], fact: dict[str, Any]) -> str:
    segments = [
        entry.get("module", ""), entry.get("title", ""), entry.get("summary", ""),
        " ".join(entry.get("keywords", [])),
        fact.get("question", ""), fact.get("answer", ""), fact.get("explanation", ""),
    ]
    return normalize_text(" ".join(str(segment) for segment in segments if segment))


def prompt_from_exemplar(entry: dict[str, Any], fact: dict[str, Any], exemplar: Optional[dict[str, Any]]) -> str:
    title = normalize_text(entry.get("title", "该主题"))
    existing = normalize_text(fact.get("question", ""))
    if existing and not is_generic_prompt(existing, title):
        return existing

    answer = normalize_text(fact.get("answer", ""))
    signature = answer_signature(answer)

    if signature == "numeric":
        return f"关于\u201c{title}\u201d，下列哪个时间或数值是正确的？"
    if signature == "acronym":
        return f"关于\u201c{title}\u201d，下列哪一项术语或缩写是正确的？"
    if signature == "command":
        return f"关于\u201c{title}\u201d，下列哪项命令或参数写法是正确的？"
    return f"关于\u201c{title}\u201d，下列哪项表述正确？"


def rewrite_conflicting_prompt(entry: dict[str, Any], fact: dict[str, Any], prompt: str) -> str:
    title = normalize_text(entry.get("title", "该主题"))
    signature = answer_signature(normalize_text(fact.get("answer", "")))
    if signature == "numeric":
        return f"围绕\u201c{title}\u201d，下列哪个时间或数值最合适？"
    if signature == "acronym":
        return f"围绕\u201c{title}\u201d，下列哪个术语或缩写最合适？"
    return f"围绕\u201c{title}\u201d，下列哪项说法最合适？"


def candidate_distractors_from_bank(matches: list[StyleMatch], correct: str) -> list[str]:
    signature = answer_signature(correct)
    candidates: list[str] = []
    for match in matches:
        for option in match.question.get("options", []):
            candidate = normalize_text(option.get("text", ""))
            if not candidate or candidate == correct or len(candidate) > 96:
                continue
            if signature_compatible(signature, answer_signature(candidate)):
                candidates.append(candidate)
    return candidates


def candidate_distractors_from_entries(source_entry: dict[str, Any], entries: list[dict[str, Any]], correct: str) -> list[str]:
    signature = answer_signature(correct)
    ranked_entries = [
        (entry, entry_similarity(source_entry, entry))
        for entry in entries if entry is not source_entry
    ]
    ranked_entries.sort(key=lambda item: item[1], reverse=True)
    pool: list[str] = []
    for entry, score in ranked_entries:
        if score <= 0:
            continue
        for fact in entry.get("facts", []):
            candidate = normalize_text(fact.get("answer", ""))
            if candidate and candidate != correct and is_fact_usable(entry, fact) and signature_compatible(signature, answer_signature(candidate)):
                pool.append(candidate)
        if len(pool) >= 24:
            break
    return pool


def build_options(
    correct: str, fact_distractors: list[str], source_entry: dict[str, Any],
    entries: list[dict[str, Any]], style_matches: list[StyleMatch], rng: random.Random,
) -> list[dict[str, str]]:
    distractors = [normalize_text(item) for item in fact_distractors if normalize_text(item)]
    candidate_pool = [
        *candidate_distractors_from_bank(style_matches, correct),
        *candidate_distractors_from_entries(source_entry, entries, correct),
    ]
    for candidate in candidate_pool:
        if candidate != correct and candidate not in distractors:
            distractors.append(candidate)
        if len(distractors) >= 3:
            break
    while len(distractors) < 3:
        distractors.append(f"不正确的备选项{len(distractors) + 1}")

    options = [correct, *distractors[:3]]
    rng.shuffle(options)
    return [{"key": LETTERS[index], "text": text} for index, text in enumerate(options)]


def load_question_bank(path: Union[str, Path]) -> list[dict[str, Any]]:
    payload = load_json(Path(path))
    return payload.get("questions", []) if isinstance(payload, dict) else payload


def synthesize_questions(
    entries: list[dict[str, Any]], count: int, seed: int, *,
    style_bank_questions: Optional[list[dict[str, Any]]] = None,
    style_top_k: int = 5, semantic_model: Optional[str] = None,
) -> dict[str, Any]:
    rng = random.Random(seed)
    style_index = (
        QuestionStyleIndex(style_bank_questions or [], semantic_model=semantic_model)
        if style_bank_questions else None
    )

    candidate_records: list[dict[str, Any]] = []
    for entry in entries:
        for fact in entry.get("facts", []):
            if not is_fact_usable(entry, fact):
                continue
            matches: list[StyleMatch] = []
            style_score = 0.0
            if style_index is not None:
                matches = style_index.search(question_query_text(entry, fact), top_k=style_top_k)
                style_score = matches[0].score if matches else 0.0
            candidate_records.append({
                "entry": entry, "fact": fact, "matches": matches,
                "style_score": style_score, "tie_breaker": rng.random(),
            })

    if not candidate_records:
        raise ValueError("No usable facts found in the knowledge base.")

    if style_index is not None:
        candidate_records.sort(key=lambda item: (item["style_score"], item["tie_breaker"]), reverse=True)
    else:
        rng.shuffle(candidate_records)

    def assemble_question(entry, fact, matches, prompt, index):
        correct = normalize_text(fact.get("answer", ""))
        exemplar = matches[0].question if matches else None
        options = build_options(correct, fact.get("distractors", []), entry, entries, matches, rng)
        answer_key = next(option["key"] for option in options if option["text"] == correct)
        topic = (exemplar.get("topic") if exemplar else None) or slugify(entry.get("id") or entry.get("title", "entry"))
        topic_name = (exemplar.get("topicName") if exemplar else None) or entry.get("title", "SynQuest")
        difficulty = int(fact.get("difficulty") or (exemplar.get("difficulty") if exemplar else 2) or 2)
        return {
            "id": f"sq-{topic}-{index:03d}",
            "source": "SynQuest",
            "origin": "semantic-generated" if semantic_model else "generated",
            "year": None,
            "topic": topic,
            "topicName": topic_name,
            "difficulty": difficulty,
            "type": fact.get("type") or "single_choice",
            "prompt": prompt,
            "options": options,
            "answer": answer_key,
            "analysis": normalize_text(fact.get("explanation") or correct),
            "knowledgeRefs": [entry.get("id", topic)],
            "styleRefs": [match.question.get("id") for match in matches[:3] if match.question.get("id")],
            "tags": sorted({topic, "synquest", *(entry.get("keywords") or [])}),
            "images": {"question": "", "note": ""},
            "pdfPage": None,
        }

    selected_questions: list[dict[str, Any]] = []
    seen_prompts: set[str] = set()
    deferred_records: list[dict[str, Any]] = []
    for record in candidate_records:
        if len(selected_questions) >= count:
            break
        entry = record["entry"]
        fact = record["fact"]
        matches = record["matches"]
        exemplar = matches[0].question if matches else None
        prompt = prompt_from_exemplar(entry, fact, exemplar)
        normalized_prompt = normalize_text(prompt)
        if normalized_prompt in seen_prompts:
            continue

        style_similarity = style_index.max_prompt_similarity(prompt) if style_index is not None else 0.0
        if style_index is not None and style_similarity >= 96.0:
            deferred_records.append({
                "entry": entry, "fact": fact, "matches": matches,
                "prompt": prompt, "style_similarity": style_similarity,
            })
            continue

        candidate_question = assemble_question(entry, fact, matches, prompt, len(selected_questions) + 1)
        if not question_passes_quality_filter(candidate_question):
            continue
        selected_questions.append(candidate_question)
        seen_prompts.add(normalized_prompt)

    if len(selected_questions) < count and deferred_records:
        deferred_records.sort(key=lambda item: item["style_similarity"])
        for record in deferred_records:
            if len(selected_questions) >= count:
                break
            rewritten_prompt = rewrite_conflicting_prompt(record["entry"], record["fact"], record["prompt"])
            rewritten_normalized = normalize_text(rewritten_prompt)
            if rewritten_normalized in seen_prompts:
                continue
            rewritten_similarity = style_index.max_prompt_similarity(rewritten_prompt) if style_index is not None else 0.0
            if rewritten_similarity >= 99.5:
                continue
            candidate_question = assemble_question(
                record["entry"], record["fact"], record["matches"],
                rewritten_prompt, len(selected_questions) + 1,
            )
            if not question_passes_quality_filter(candidate_question):
                continue
            selected_questions.append(candidate_question)
            seen_prompts.add(rewritten_normalized)

    if not selected_questions:
        raise ValueError("No questions survived the style-homology and duplicate filters.")

    return {
        "meta": {
            "title": "SynQuest Generated Questions",
            "count": len(selected_questions),
            "seed": seed,
            "styleBankQuestions": len(style_bank_questions or []),
            "styleTopK": style_top_k if style_bank_questions else 0,
            "semanticModel": semantic_model or "",
            "algorithms": [
                "knowledge_fact_filtering",
                "jieba_tokenization" if jieba is not None else "regex_tokenization",
                "bm25_style_retrieval" if style_bank_questions else "knowledge_only_sampling",
                "tfidf_style_retrieval" if style_bank_questions else "none",
                "semantic_embedding_retrieval" if semantic_model else "none",
                "hybrid_style_rerank" if semantic_model else "none",
                "rapidfuzz_prompt_dedup" if style_bank_questions else "none",
                "style_guided_prompt_adaptation" if style_bank_questions else "generic_prompt_assembly",
            ],
        },
        "questions": selected_questions,
    }
