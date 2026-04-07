#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Strip ALL `has_resource` relationships from calibrated_relationships.parquet.

This is a strict mode:
  - remove every row with type == 'has_resource'
  - keep all other relationships unchanged
"""

from __future__ import annotations

import argparse
import os
import shutil
from datetime import datetime
from pathlib import Path

import pandas as pd


def main() -> None:
    parser = argparse.ArgumentParser(description="Strip all has_resource edges")
    parser.add_argument(
        "--relationships",
        default="data/output/calibrated_relationships.parquet",
        help="Path to calibrated_relationships.parquet",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Output path. If empty, overwrite --relationships with backup.",
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Do not create backup when overwriting in-place.",
    )
    args = parser.parse_args()

    relationships_path = Path(args.relationships)
    if not relationships_path.exists():
        raise FileNotFoundError(str(relationships_path))

    df = pd.read_parquet(relationships_path)
    if "type" not in df.columns:
        raise ValueError("relationships parquet missing required column: 'type'")

    hr_rows = int((df["type"] == "has_resource").sum())
    df2 = df[df["type"] != "has_resource"].copy()
    out_path = Path(args.output) if args.output else relationships_path

    if out_path == relationships_path and not args.no_backup:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = relationships_path.with_name(
            f"{relationships_path.stem}.bak_{ts}{relationships_path.suffix}"
        )
        shutil.copy2(relationships_path, backup_path)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    df2.to_parquet(out_path, index=False, engine="pyarrow")

    print("=== strip_has_resource_relationships ===")
    print(f"input:  {relationships_path}")
    print(f"output: {out_path}")
    print(f"removed has_resource rows: {hr_rows}")
    print(f"has_resource after: {int((df2['type']=='has_resource').sum())}")


if __name__ == "__main__":
    main()

