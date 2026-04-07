#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Clean orphan `has_resource` relationships in calibrated_relationships.parquet.

Rule:
  - Keep all non-`has_resource` relationships unchanged.
  - For `type == 'has_resource'`, keep the row only if `end_id` exists in the given resources parquet.

By default:
  - relationships: data/output/calibrated_relationships.parquet
  - resources:     data/output/stage3_resources.parquet
  - output:        overwrite relationships file (with backup)
"""

from __future__ import annotations

import argparse
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Set

import pandas as pd


def load_parquet_to_df(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(str(path))
    return pd.read_parquet(path)


def get_resource_ids(df_resources: pd.DataFrame) -> Set[str]:
    if "id" not in df_resources.columns:
        raise ValueError("resources parquet missing required column: 'id'")
    ids = df_resources["id"].dropna().astype(str).tolist()
    return set(ids)


def clean_has_resource(
    df_relationships: pd.DataFrame,
    resource_ids: Set[str],
) -> tuple[pd.DataFrame, int, int, int]:
    if "type" not in df_relationships.columns:
        raise ValueError("relationships parquet missing required column: 'type'")
    if "end_id" not in df_relationships.columns:
        raise ValueError("relationships parquet missing required column: 'end_id'")

    hr_mask = df_relationships["type"] == "has_resource"
    hr_rows = int(hr_mask.sum())

    # end_id might be numeric/string; normalize to str for membership check
    end_ids = df_relationships.loc[hr_mask, "end_id"].dropna().astype(str)
    orphan_count = int((~end_ids.isin(resource_ids)).sum())

    keep_mask = (~hr_mask) | (df_relationships["end_id"].fillna("").astype(str).isin(resource_ids))
    df_filtered = df_relationships.loc[keep_mask].copy()

    hr_after = int((df_filtered["type"] == "has_resource").sum())
    return df_filtered, hr_rows, orphan_count, hr_after


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean orphan has_resource edges")
    parser.add_argument(
        "--relationships",
        default="data/output/calibrated_relationships.parquet",
        help="Path to calibrated_relationships.parquet",
    )
    parser.add_argument(
        "--resources",
        default="data/output/stage3_resources.parquet",
        help="Path to resources parquet. Orphans are detected by missing end_id in this file.",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Output path. If empty, overwrite --relationships in-place.",
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Do not create a backup file when overwriting in-place.",
    )
    args = parser.parse_args()

    relationships_path = Path(args.relationships)
    resources_path = Path(args.resources)
    output_path = Path(args.output) if args.output else relationships_path

    df_rels = load_parquet_to_df(relationships_path)
    df_res = load_parquet_to_df(resources_path)
    resource_ids = get_resource_ids(df_res)

    cleaned_df, hr_rows, orphan_count, hr_after = clean_has_resource(df_rels, resource_ids)

    if output_path == relationships_path and not args.no_backup:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = relationships_path.with_name(f"{relationships_path.stem}.bak_{ts}{relationships_path.suffix}")
        shutil.copy2(relationships_path, backup_path)

    os.makedirs(output_path.parent, exist_ok=True)
    cleaned_df.to_parquet(output_path, index=False, engine="pyarrow")

    print("=== has_resource cleaning summary ===")
    print(f"relationships_path: {relationships_path}")
    print(f"resources_path:     {resources_path}")
    print(f"original has_resource rows: {hr_rows}")
    print(f"orphan has_resource end_id: {orphan_count}")
    print(f"after has_resource rows:    {hr_after}")
    print(f"output_path: {output_path}")


if __name__ == "__main__":
    main()

