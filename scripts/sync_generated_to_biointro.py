#!/usr/bin/env python3
"""Normalize SynQuest generated payloads and merge into the BioIntro example bank."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from functions.synquest.question_engine import question_passes_quality_filter  # noqa: E402

CANONICAL_TOPICS: dict[str, dict[str, str]] = {
    "genomics": {"name": "引言及基因组信息学", "knowledgeRef": "genomics-core"},
    "transcriptomics": {"name": "转录组信息学", "knowledgeRef": "transcriptomics-core"},
    "biomolecular-network": {"name": "生物分子网络", "knowledgeRef": "biomolecular-network-core"},
    "proteomics": {"name": "蛋白组信息学", "knowledgeRef": "proteomics-core"},
    "cadd": {"name": "计算机辅助药物发现", "knowledgeRef": "cadd-core"},
    "general": {"name": "综合题", "knowledgeRef": "general"},
}

TOPIC_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("genomics", ("基因组", "染色体", "碱基", "序列比对", "blast", "blosum", "genbank", "ensembl", "ucsc", "omim", "hgp", "同源")),
    ("transcriptomics", ("转录组", "rna-seq", "差异表达", "芯片", "go富集", "kegg", "geo", "单细胞", "t-sne", "pca", "tpm", "fpkm")),
    ("biomolecular-network", ("网络", "度", "聚类系数", "cytoscape", "ppi", "介数中心性", "节点")),
    ("proteomics", ("蛋白", "pdb", "swiss-prot", "三维结构", "跨膜", "tmpred", "protparam", "等电点")),
    ("cadd", ("药物", "qsar", "配体", "受体", "靶标", "adme", "高通量筛选", "网络药理学")),
]


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip().lower()


def slugify(text: str) -> str:
    value = re.sub(r"[^\w\u4e00-\u9fff]+", "-", str(text or "").strip().lower())
    value = re.sub(r"-{2,}", "-", value).strip("-")
    return value or "item"


def detect_canonical_topic(question: dict[str, Any]) -> str:
    blob = " ".join([
        question.get("topic", ""), question.get("topicName", ""),
        question.get("prompt", ""), question.get("analysis", ""),
        " ".join(question.get("tags") or []),
    ])
    normalized = normalize_text(blob)
    for topic_id, keywords in TOPIC_RULES:
        if any(keyword in normalized for keyword in keywords):
            return topic_id
    return "general"


def apply_canonical_topic(question: dict[str, Any], topic_id: str) -> None:
    topic_info = CANONICAL_TOPICS[topic_id]
    question["topic"] = topic_id
    question["topicName"] = topic_info["name"]
    question["knowledgeRefs"] = [topic_info["knowledgeRef"]]
    tags = set(question.get("tags") or [])
    tags.add(topic_id)
    question["tags"] = sorted(tags)


def next_index(existing_questions: list[dict[str, Any]], prefix: str) -> int:
    max_index = 0
    for question in existing_questions:
        if not question.get("id", "").startswith(prefix):
            continue
        match = re.search(r"-(\d{3})$", question.get("id", ""))
        if match:
            max_index = max(max_index, int(match.group(1)))
    return max_index + 1


def normalize_payload(payload: dict[str, Any], existing_questions: list[dict[str, Any]]) -> dict[str, Any]:
    normalized: list[dict[str, Any]] = []
    counter = next_index(existing_questions, "sq-")
    for question in payload.get("questions", []):
        item = json.loads(json.dumps(question, ensure_ascii=False))
        topic_id = item.get("topic")
        if topic_id not in CANONICAL_TOPICS:
            topic_id = detect_canonical_topic(item)
        apply_canonical_topic(item, topic_id)
        item["id"] = f"sq-{topic_id}-{counter:03d}"
        item["source"] = "SynQuest"
        if not question_passes_quality_filter(item):
            continue
        normalized.append(item)
        counter += 1
    payload["questions"] = normalized
    payload.setdefault("meta", {})["count"] = len(normalized)
    return payload


def refresh_bank_meta(bank: dict[str, Any]) -> None:
    questions = bank.get("questions", [])
    topic_counter = Counter(question.get("topic", "unknown") for question in questions)
    type_counter = Counter(question.get("type", "single_choice") for question in questions)
    topic_names: dict[str, str] = {}
    for question in questions:
        topic_id = question.get("topic", "unknown")
        topic_names.setdefault(topic_id, question.get("topicName") or topic_id)

    meta = bank.setdefault("meta", {})
    meta["totalQuestions"] = len(questions)
    meta["sources"] = sorted({question.get("source", "Unknown") for question in questions})
    meta["topics"] = [
        {"id": topic_id, "name": topic_names.get(topic_id, topic_id), "count": count}
        for topic_id, count in sorted(topic_counter.items())
    ]
    meta["types"] = dict(sorted(type_counter.items()))


def merge_payload(bank: dict[str, Any], incoming_questions: list[dict[str, Any]]) -> dict[str, Any]:
    existing = {question["id"]: question for question in bank.get("questions", [])}
    for question in incoming_questions:
        existing[question["id"]] = question
    bank["questions"] = list(existing.values())
    refresh_bank_meta(bank)
    return bank


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Normalize SynQuest generated payloads for BioIntro.")
    parser.add_argument("--bank", required=True, help="Path to question-bank.json")
    parser.add_argument("--incoming", required=True, help="Raw generated SynQuest payload")
    parser.add_argument("--out", help="Output bank path; defaults to overwriting --bank")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    bank_path = Path(args.bank)
    bank = load_json(bank_path)

    incoming_payload = normalize_payload(load_json(Path(args.incoming)), bank.get("questions", []))
    merged = merge_payload(bank, incoming_payload.get("questions", []))
    write_json(Path(args.out) if args.out else bank_path, merged)

    print(f"incoming questions: {len(incoming_payload.get('questions', []))}")
    print(f"merged total: {merged['meta']['totalQuestions']}")


if __name__ == "__main__":
    main()
