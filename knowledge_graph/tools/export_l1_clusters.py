#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Export L1 clusters to hierarchical JSON files.

Each L1 topic is exported as one JSON file named by L1 name.
Cluster JSON format is nested only: L1 -> L2 -> L3.
Also exports one JSON file for prerequisite relations among L1 topics.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd


INVALID_FILENAME_CHARS = r'[<>:"/\\|?*]'


def safe_filename(name: str, fallback: str) -> str:
    cleaned = re.sub(INVALID_FILENAME_CHARS, "_", (name or "").strip())
    cleaned = cleaned.rstrip(". ")
    if not cleaned:
        cleaned = fallback
    return cleaned


def load_data(entities_path: Path, relationships_path: Path) -> Tuple[List[dict], List[dict]]:
    entities = pd.read_parquet(entities_path).to_dict("records")
    relationships = pd.read_parquet(relationships_path).to_dict("records")
    return entities, relationships


def to_jsonable(obj):
    if isinstance(obj, dict):
        return {k: to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [to_jsonable(v) for v in obj]
    if isinstance(obj, tuple):
        return [to_jsonable(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return [to_jsonable(v) for v in obj.tolist()]
    if isinstance(obj, np.generic):
        return obj.item()
    if pd.isna(obj):
        return None
    return obj


def index_entities(entities: List[dict]) -> Dict[str, dict]:
    return {e.get("id", ""): e for e in entities if e.get("id")}


def build_l1_cluster_payload(
    l1_node: dict,
    id_to_entity: Dict[str, dict],
    relationships: List[dict],
) -> dict:
    l1_id = l1_node.get("id", "")

    l1_to_l2_rels = [
        r for r in relationships
        if r.get("type") == "contains"
        and r.get("start_id") == l1_id
        and id_to_entity.get(r.get("end_id", ""), {}).get("level") == "L2"
    ]
    l2_ids = [r.get("end_id", "") for r in l1_to_l2_rels if r.get("end_id")]
    l2_nodes = [id_to_entity[l2_id] for l2_id in l2_ids if l2_id in id_to_entity]

    l2_to_l3_rels = [
        r for r in relationships
        if r.get("type") == "contains"
        and r.get("start_id") in set(l2_ids)
        and id_to_entity.get(r.get("end_id", ""), {}).get("level") == "L3"
    ]

    def pick_basic_fields(node: dict) -> dict:
        return {
            "id": node.get("id", ""),
            "name": node.get("name", ""),
            "definition": node.get("definition", ""),
        }

    l2_items = []
    for l2 in l2_nodes:
        l2_id = l2.get("id", "")
        rels = [r for r in l2_to_l3_rels if r.get("start_id") == l2_id]
        sub_l3_ids = [r.get("end_id", "") for r in rels if r.get("end_id")]
        sub_l3_nodes = [id_to_entity[sid] for sid in sub_l3_ids if sid in id_to_entity]
        l2_payload = pick_basic_fields(l2)
        l2_payload["L3"] = [pick_basic_fields(l3) for l3 in sub_l3_nodes]
        l2_items.append(l2_payload)

    l1_payload = pick_basic_fields(l1_node)
    l1_payload["L2"] = l2_items

    payload = {"L1": l1_payload}
    return payload


def build_l1_prerequisites_payload(
    l1_nodes: List[dict],
    id_to_entity: Dict[str, dict],
    relationships: List[dict],
) -> dict:
    l1_ids = {n.get("id", "") for n in l1_nodes if n.get("id")}
    prereq = []
    for rel in relationships:
        if rel.get("type") != "prerequisite":
            continue
        sid = rel.get("start_id", "")
        eid = rel.get("end_id", "")
        if sid in l1_ids and eid in l1_ids:
            prereq.append(
                {
                    "start_name": id_to_entity.get(sid, {}).get("name", ""),
                    "end_name": id_to_entity.get(eid, {}).get("name", ""),
                    "relation": "prerequisite",
                }
            )
    return {"l1_prerequisites": prereq}


def main() -> None:
    parser = argparse.ArgumentParser(description="Export L1 clusters to JSON files")
    parser.add_argument(
        "--entities",
        default="data/output/calibrated_entities.parquet",
        help="Path to calibrated entities parquet",
    )
    parser.add_argument(
        "--relationships",
        default="data/output/calibrated_relationships.parquet",
        help="Path to calibrated relationships parquet",
    )
    parser.add_argument(
        "--output-dir",
        default="data/output/l1_clusters_json",
        help="Output directory for exported JSON files",
    )
    args = parser.parse_args()

    entities_path = Path(args.entities)
    relationships_path = Path(args.relationships)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    entities, relationships = load_data(entities_path, relationships_path)
    id_to_entity = index_entities(entities)
    l1_nodes = [e for e in entities if e.get("level") == "L1"]
    l1_nodes = sorted(l1_nodes, key=lambda x: x.get("name", ""))

    # remove old cluster json files to avoid stale files
    for p in output_dir.glob("*.json"):
        p.unlink()

    used_names = set()
    for l1 in l1_nodes:
        l1_id = l1.get("id", "")
        l1_name = l1.get("name", "")
        fname = safe_filename(l1_name, l1_id or "l1")
        base = fname
        idx = 2
        while fname in used_names:
            fname = f"{base}_{idx}"
            idx += 1
        used_names.add(fname)

        payload = build_l1_cluster_payload(l1, id_to_entity, relationships)
        out_path = output_dir / f"{fname}.json"
        out_path.write_text(
            json.dumps(to_jsonable(payload), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    prereq_payload = build_l1_prerequisites_payload(l1_nodes, id_to_entity, relationships)
    prereq_path = output_dir / "L1_前置关系.json"
    prereq_path.write_text(
        json.dumps(to_jsonable(prereq_payload), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"Exported {len(l1_nodes)} L1 cluster files to: {output_dir}")
    print(f"L1 prerequisite file: {prereq_path}")


if __name__ == "__main__":
    main()

