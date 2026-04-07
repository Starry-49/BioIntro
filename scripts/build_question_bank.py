#!/usr/bin/env python3
"""Parse previous.docx into structured question-bank.json for BioIntro."""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PREVIOUS_DOCX = ROOT / "previous.docx"
OUTPUT_JSON = ROOT / "example" / "data" / "question-bank.json"

TOPIC_RULES: dict[str, list[str]] = {
    "genomics": [
        "基因组", "HGP", "COSMIC", "ENCODE", "Genbank", "GenBank", "UCSC",
        "Ensembl", "BLAST", "BLOSUM", "PAM", "PubMed", "碱基", "染色体",
        "序列比对", "OMIM", "同源", "基因组计划", "PCGP", "TCGA", "HapMap",
        "DNA调控", "基因调控网络",
    ],
    "transcriptomics": [
        "转录组", "RNA-seq", "RNA", "差异表达", "芯片", "探针", "TPM", "FPKM",
        "DESeq2", "聚类", "GO", "KEGG", "富集", "GEO", "scRNA", "单细胞",
        "t-SNE", "PCA", "基因表达", "clusterProfiler", "火山图",
        "归一化", "方差分析", "CEL", "荧光强度",
    ],
    "biomolecular-network": [
        "生物分子网络", "网络", "度", "Degree", "聚类系数", "Cytoscape",
        "介数中心性", "PPI", "蛋白质-蛋白质", "信号转导", "代谢网络",
        "节点", "边的权重",
    ],
    "proteomics": [
        "蛋白", "Proteomics", "PDB", "Swiss-Prot", "三维结构", "跨膜",
        "TMpred", "ProtParam", "等电点", "X-射线", "晶体衍射",
        "Pymol", "RasMol", "Chimera", "VMD", "同源建模",
    ],
    "cadd": [
        "药物", "QSAR", "配体", "受体", "靶标", "药物设计", "临床",
        "ADME", "毒性", "天然产物", "高通量筛选", "组合化学",
        "网络药理学", "阿司匹林", "计算机辅助",
    ],
}

TOPIC_META: dict[str, dict[str, str]] = {
    "genomics": {"name": "引言及基因组信息学", "knowledgeRef": "genomics-core"},
    "transcriptomics": {"name": "转录组信息学", "knowledgeRef": "transcriptomics-core"},
    "biomolecular-network": {"name": "生物分子网络", "knowledgeRef": "biomolecular-network-core"},
    "proteomics": {"name": "蛋白组信息学", "knowledgeRef": "proteomics-core"},
    "cadd": {"name": "计算机辅助药物发现", "knowledgeRef": "cadd-core"},
    "general": {"name": "综合题", "knowledgeRef": "general"},
}


def extract_text_from_docx() -> str:
    from markitdown import MarkItDown
    md = MarkItDown()
    result = md.convert(str(PREVIOUS_DOCX))
    return result.text_content


def infer_topic(text: str) -> str:
    for topic_id, keywords in TOPIC_RULES.items():
        if any(keyword in text for keyword in keywords):
            return topic_id
    return "general"


def parse_questions(text: str) -> list[dict[str, Any]]:
    questions: list[dict[str, Any]] = []
    current_section = "general"
    current_type = "single_choice"

    section_map = {
        "引言及基因组信息学": "genomics",
        "转录组信息学": "transcriptomics",
        "生物分子网络": "biomolecular-network",
        "蛋白组信息学": "proteomics",
        "计算机辅助药物发现": "cadd",
    }

    lines = text.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # Detect section headers
        for section_name, section_id in section_map.items():
            if section_name in line and line.startswith("#"):
                current_section = section_id
                break

        # Detect question type
        if "单选题" in line:
            current_type = "single_choice"
            i += 1
            continue
        elif "多选题" in line:
            current_type = "multiple_choice"
            i += 1
            continue

        # Skip non-question lines
        if line.startswith("#") or line.startswith("[") or line.startswith("注：") or not line:
            i += 1
            continue

        # Try to detect a question: line that does NOT start with A-E followed by options
        if not re.match(r"^[A-E][\.\．]", line) and len(line) > 6 and not line.startswith("!["):
            prompt = line
            options: list[dict[str, str]] = []

            # Collect options
            j = i + 1
            while j < len(lines):
                opt_line = lines[j].strip()
                if not opt_line:
                    j += 1
                    continue
                opt_match = re.match(r"^([A-E])[\.\．]\s*(.*)", opt_line)
                if opt_match:
                    options.append({"key": opt_match.group(1), "text": opt_match.group(2).strip()})
                    j += 1
                else:
                    break

            if options:
                # Determine topic: use section default, but refine with keyword matching
                combined_text = prompt + " " + " ".join(opt.get("text", "") for opt in options)
                topic = infer_topic(combined_text)
                if topic == "general":
                    topic = current_section

                question_id = f"prev_{len(questions) + 1:03d}"
                questions.append({
                    "id": question_id,
                    "year": None,
                    "source": "Previous",
                    "prompt": prompt,
                    "type": current_type,
                    "topic": topic,
                    "topicName": TOPIC_META.get(topic, TOPIC_META["general"])["name"],
                    "difficulty": 3 if current_type == "multiple_choice" else 2,
                    "options": options,
                    "answer": "",
                    "analysis": "",
                    "images": {"question": "", "note": ""},
                    "pdfPage": None,
                    "knowledgeRefs": [TOPIC_META.get(topic, TOPIC_META["general"])["knowledgeRef"]],
                    "tags": sorted({topic, current_type}),
                    "origin": "previous-curated",
                })
                i = j
                continue

        i += 1

    return questions


def build_payload(questions: list[dict[str, Any]]) -> dict[str, Any]:
    topic_counter = Counter(q["topic"] for q in questions)
    type_counter = Counter(q["type"] for q in questions)

    return {
        "meta": {
            "title": "BioIntro Question Bank",
            "subtitle": "Structured archive from bioinformatics introduction course",
            "generatedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "totalQuestions": len(questions),
            "sources": sorted({q["source"] for q in questions}),
            "topics": [
                {"id": topic_id, "name": TOPIC_META.get(topic_id, TOPIC_META["general"])["name"], "count": count}
                for topic_id, count in sorted(topic_counter.items())
            ],
            "types": dict(sorted(type_counter.items())),
            "imageQuestionCount": sum(1 for q in questions if q["images"]["question"]),
            "noteImageCount": 0,
        },
        "questions": questions,
    }


def main() -> None:
    text = extract_text_from_docx()
    questions = parse_questions(text)
    payload = build_payload(questions)
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(questions)} questions to {OUTPUT_JSON}")


if __name__ == "__main__":
    main()
