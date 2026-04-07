#!/usr/bin/env python3
"""Extract knowledge base from PPTX slides and merge into a unified KB JSON."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
FUNCTIONS_ROOT = ROOT / "functions"
if str(FUNCTIONS_ROOT) not in sys.path:
    sys.path.insert(0, str(FUNCTIONS_ROOT))

from synquest.knowledge_loader import build_knowledge_base  # noqa: E402

SLIDES_DIR = ROOT / "slides"
OUTPUT_JSON = ROOT / "example" / "data" / "knowledge-base" / "biointro-core.json"

MODULE_MAP = {
    "基因组": "genomics-core",
    "转录组": "transcriptomics-core",
    "蛋白组": "proteomics-core",
    "生物网络": "biomolecular-network-core",
    "计算机辅助药物发现": "cadd-core",
}

MODULE_NAMES = {
    "genomics-core": "引言及基因组信息学",
    "transcriptomics-core": "转录组信息学",
    "proteomics-core": "蛋白组信息学",
    "biomolecular-network-core": "生物分子网络",
    "cadd-core": "计算机辅助药物发现",
}


def collect_pptx_files() -> list[tuple[str, Path]]:
    files: list[tuple[str, Path]] = []
    for subdir in sorted(SLIDES_DIR.iterdir()):
        if not subdir.is_dir():
            continue
        module_id = None
        for key, value in MODULE_MAP.items():
            if key in subdir.name:
                module_id = value
                break
        if module_id is None:
            continue
        for pptx_file in sorted(subdir.glob("*.pptx")):
            files.append((module_id, pptx_file))
        for ppt_file in sorted(subdir.glob("*.ppt")):
            # Skip old .ppt format (not supported by zipfile-based parser)
            print(f"  skipping .ppt file (not supported): {ppt_file.name}")
    return files


def merge_entries(all_entries: list[dict[str, Any]], module_id: str, new_entries: list[dict[str, Any]]) -> None:
    module_name = MODULE_NAMES.get(module_id, module_id)
    for entry in new_entries:
        entry["module"] = module_name
        # Ensure unique IDs
        entry["id"] = f"{module_id}-{entry['id']}"
        all_entries.append(entry)


def main() -> None:
    if not SLIDES_DIR.exists():
        print(f"Slides directory not found: {SLIDES_DIR}")
        return

    all_entries: list[dict[str, Any]] = []
    pptx_files = collect_pptx_files()

    if not pptx_files:
        print("No PPTX files found in slides directory.")
        return

    for module_id, pptx_path in pptx_files:
        print(f"Processing: {pptx_path.name} -> {module_id}")
        try:
            payload = build_knowledge_base(pptx_path)
            entries = payload.get("entries", [])
            merge_entries(all_entries, module_id, entries)
            print(f"  extracted {len(entries)} entries")
        except Exception as e:
            print(f"  ERROR: {e}")

    output = {
        "meta": {
            "title": "BioIntro Knowledge Base",
            "subtitle": "Extracted from bioinformatics introduction course slides",
            "modules": list(MODULE_NAMES.values()),
            "totalEntries": len(all_entries),
            "totalFacts": sum(len(entry.get("facts", [])) for entry in all_entries),
            "algorithms": [
                "ooxml_zip_parsing",
                "slide_title_placeholder_detection",
                "keyword_weighting_and_fact_segmentation",
                "multi_source_module_merge",
            ],
        },
        "entries": all_entries,
    }

    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nWrote {len(all_entries)} entries to {OUTPUT_JSON}")


if __name__ == "__main__":
    main()
