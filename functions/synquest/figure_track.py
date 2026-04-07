"""Independent figure-question track for image-backed SynQuest items."""

from __future__ import annotations

import json
import random
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Optional, Union

from .knowledge_loader import build_knowledge_base


ROOT = Path(__file__).resolve().parents[2]
LETTERS = ["A", "B", "C", "D"]
SUPPORTED_FIGURE_SUFFIXES = {".pdf", ".png", ".jpg", ".jpeg"}
GENERIC_TITLES = {"内容概要", "绪论", "引言", "小结", "总结", "overview", "contents"}
FIGURE_TRACK_ALGORITHMS = [
    "pdf_page_image_presence_filtering",
    "pdftoppm_page_screenshot_rendering",
    "neighbor_text_context_window",
    "keyword_overlap_distractor_retrieval",
    "rule_based_figure_meaning_explanation",
]


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "-", text.strip().lower())
    return slug.strip("-") or "entry"


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def informative_tokens(text: str) -> set[str]:
    cleaned = normalize_text(text)
    tokens = set()
    for token in re.findall(r"[A-Za-z][A-Za-z0-9\-/+.]{1,}", cleaned):
        tokens.add(token.lower())
    for token in re.findall(r"[\u4e00-\u9fff]{2,}", cleaned):
        tokens.add(token)
    return tokens


def _run_command(args: list[str]) -> str:
    if not shutil.which(args[0]):
        raise RuntimeError(f"Missing required command for figure track: {args[0]}")
    result = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="ignore", check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"Command failed: {' '.join(args)}")
    return result.stdout


def _load_kb_payload(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict) and "entries" in raw:
        return raw
    if isinstance(raw, list):
        return {"meta": {"sourcePath": str(path), "sourceType": "json"}, "entries": raw}
    raise ValueError("Knowledge-base JSON must be a list or contain an `entries` list.")


def _context_lines(entries: list[dict[str, Any]], index: int, window: int) -> list[str]:
    lines: list[str] = []
    start = max(0, index - window)
    end = min(len(entries), index + window + 1)
    for current in entries[start:end]:
        title = normalize_text(current.get("title", ""))
        summary = normalize_text(current.get("summary", ""))
        if title:
            lines.append(title)
        if summary and summary != title:
            lines.append(summary)
    deduped: list[str] = list(dict.fromkeys(lines))
    return deduped[:8]


def _is_explainable_candidate(entry: dict[str, Any]) -> bool:
    title = normalize_text(entry.get("title", ""))
    if not title:
        return False
    lowered = title.lower()
    if any(token in lowered for token in GENERIC_TITLES) and not normalize_text(entry.get("summary", "")):
        return False
    return True


def _meaning_sentence(entry: dict[str, Any]) -> str:
    title = normalize_text(entry.get("title", "该图示"))
    summary = normalize_text(entry.get("summary", "")) or title
    if summary != title:
        return f"该图主要用于解释\u201c{title}\u201d，重点涉及{summary}。"
    return f"该图主要用于帮助理解\u201c{title}\u201d这一知识主题。"


def _similarity(a: dict[str, Any], b: dict[str, Any]) -> float:
    score = 0.0
    if a.get("module") and a.get("module") == b.get("module"):
        score += 2.0
    score += len(set(a.get("keywords", [])) & set(b.get("keywords", [])))
    return score


def _render_pdf_page(source: Path, page: int, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    prefix = output_path.with_suffix("")
    _run_command(["pdftoppm", "-f", str(page), "-l", str(page), "-png", "-singlefile", str(source), str(prefix)])


def build_figure_track(
    source: Union[str, Path], *, knowledge_base_path: Optional[Union[str, Path]] = None,
    candidate_limit: int = 24, context_window: int = 1,
) -> dict[str, Any]:
    source_path = Path(source)
    suffix = source_path.suffix.lower()
    if suffix not in SUPPORTED_FIGURE_SUFFIXES:
        raise ValueError(f"Figure track supports: {', '.join(sorted(SUPPORTED_FIGURE_SUFFIXES))}")

    if knowledge_base_path:
        kb_payload = _load_kb_payload(Path(knowledge_base_path))
    elif suffix == ".pdf":
        kb_payload = build_knowledge_base(source_path)
    else:
        kb_payload = {"meta": {}, "entries": []}

    entries = kb_payload.get("entries", [])
    figures: list[dict[str, Any]] = []

    if suffix == ".pdf":
        for index, entry in enumerate(entries):
            image_count = int(entry.get("visualSignals", {}).get("imageCount", 0) or 0)
            source_pages = entry.get("sourcePages", [])
            if image_count <= 0 or not source_pages:
                continue
            if not _is_explainable_candidate(entry):
                continue
            context = _context_lines(entries, index, context_window)
            figures.append({
                "id": f"{slugify(source_path.stem)}-fig-{len(figures) + 1:03d}",
                "entryId": entry.get("id", f"entry-{index + 1:03d}"),
                "page": int(source_pages[0]),
                "sourcePath": str(source_path),
                "sourceType": "pdf",
                "module": entry.get("module", ""),
                "title": entry.get("title", ""),
                "summary": normalize_text(entry.get("summary", "")),
                "contextLines": context,
                "keywords": entry.get("keywords", []),
                "imageCount": image_count,
                "score": image_count * 3.0 + len(entry.get("facts", [])) * 1.2,
            })

    figures.sort(key=lambda item: item["score"], reverse=True)
    if candidate_limit > 0:
        figures = figures[:candidate_limit]

    return {
        "meta": {
            "sourcePath": str(source_path),
            "sourceType": suffix.lstrip("."),
            "candidateCount": len(figures),
            "algorithms": FIGURE_TRACK_ALGORITHMS,
        },
        "figures": figures,
    }


def load_figure_track(path: Union[str, Path]) -> dict[str, Any]:
    return _load_kb_payload(Path(path))


def synthesize_figure_questions(
    figure_track: dict[str, Any], *, count: int, seed: int, asset_dir: Union[str, Path],
) -> dict[str, Any]:
    rng = random.Random(seed)
    figures = list(figure_track.get("figures", []))
    if not figures:
        raise ValueError("No figure candidates available for synthesis.")

    selected = figures[:count]
    asset_root = Path(asset_dir)
    asset_root.mkdir(parents=True, exist_ok=True)

    questions: list[dict[str, Any]] = []
    used_meanings: set[str] = set()
    for index, figure in enumerate(selected, start=1):
        correct = _meaning_sentence(figure)
        if correct in used_meanings:
            continue

        distractors: list[str] = []
        for candidate in figures:
            if candidate["id"] == figure["id"]:
                continue
            meaning = _meaning_sentence(candidate)
            if meaning != correct and meaning not in distractors:
                distractors.append(meaning)
            if len(distractors) >= 3:
                break

        source_path = Path(figure["sourcePath"])
        image_output = asset_root / f"{figure['id']}.png"
        if figure["sourceType"] == "pdf":
            _render_pdf_page(source_path, int(figure["page"]), image_output)
        else:
            shutil.copyfile(source_path, image_output)

        answer_texts = [correct, *distractors[:3]]
        rng.shuffle(answer_texts)
        options = [{"key": LETTERS[i], "text": text} for i, text in enumerate(answer_texts[:4])]
        answer_key = next(option["key"] for option in options if option["text"] == correct)
        questions.append({
            "id": f"sqfig-{slugify(figure['title'])}-{index:03d}",
            "source": "SynQuest-Figure",
            "origin": "figure-context-generated",
            "year": None,
            "topic": slugify(figure["module"] or figure["title"]),
            "topicName": figure["title"],
            "difficulty": 2,
            "type": "single_choice",
            "prompt": "根据图示与相邻知识，下列哪项最能解释这张图的核心含义？",
            "options": options,
            "answer": answer_key,
            "analysis": f"这张图来自知识源的第 {figure.get('page', '?')} 页，对应主题\u201c{figure['title']}\u201d。",
            "knowledgeRefs": [figure["entryId"]],
            "styleRefs": [],
            "tags": sorted({"synquest", "figure-question", *(figure.get("keywords") or [])}),
            "images": {"question": str(image_output.relative_to(ROOT / "example")) if image_output.is_relative_to(ROOT / "example") else str(image_output), "note": ""},
            "pdfPage": figure.get("page"),
        })
        used_meanings.add(correct)

    if not questions:
        raise ValueError("No figure questions were generated.")

    return {
        "meta": {"title": "SynQuest Figure Questions", "count": len(questions), "seed": seed, "algorithms": FIGURE_TRACK_ALGORITHMS},
        "questions": questions,
    }
