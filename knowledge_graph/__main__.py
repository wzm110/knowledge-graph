"""Knowledge Graph Builder - Main Entry Point"""

import os
import sys
import glob as glob_module
import argparse

from knowledge_graph.utils.logger import get_logger
from knowledge_graph.utils.config import load_config, load_l1_concepts
from knowledge_graph.steps.extract_l1 import run as run_extract_l1
from knowledge_graph.steps.extract import extract_entities_relations
from knowledge_graph.steps.calibrate import calibrate_data
from knowledge_graph.steps.build import build_graph

logger = get_logger(__name__)


def load_input_data(input_dir: str = "data/input"):
    """Load input CSV data."""
    processed_data = []
    chunk_id = 0

    csv_files = glob_module.glob(f"{input_dir}/*.csv")
    logger.info(f"Found {len(csv_files)} CSV files")

    for csv_file in csv_files:
        if os.path.basename(csv_file) == "目录.csv":
            continue

        logger.info(f"Reading input file: {csv_file}")
        import pandas as pd
        df = pd.read_csv(csv_file, encoding='utf-8-sig')
        logger.info(f"Successfully read {len(df)} chapters")

        for chapter_id, row in df.iterrows():
            chapter_title = row.get('title', row.get(df.columns[0], ''))
            text = row.get('text', '')
            lecture_link = row.get('lecture_link', '')
            ppt_link = row.get('ppt_link', '')
            code_link = row.get('code_link', '')
            video_link = row.get('video_link', '')

            text = text.strip()
            logger.debug(f"File {csv_file} - Chapter {chapter_id} - {chapter_title}, text length: {len(text)}")

            processed_item = {
                'chapter_id': chapter_id,
                'chapter_title': chapter_title,
                'chunk_id': chunk_id,
                'text_chunk': text,
                'lecture_link': lecture_link,
                'ppt_link': ppt_link,
                'code_link': code_link,
                'video_link': video_link
            }
            processed_data.append(processed_item)
            chunk_id += 1

    logger.info(f"Reading completed, total {len(processed_data)} text chunks")
    return processed_data


def run_full_pipeline(config: dict):
    """Run the full knowledge graph construction pipeline."""
    logger.info("=" * 60)
    logger.info("Knowledge Graph Construction Pipeline Started")
    logger.info("=" * 60)

    l1_concepts = load_l1_concepts()
    logger.info(f"Loaded {len(l1_concepts)} predefined L1 concepts")

    processed_data = load_input_data()

    logger.info("\n=== Step 2: Extract Entities and Relations ===")
    knowledge_points, resources, relationships = extract_entities_relations(
        processed_data, l1_concepts, config
    )
    logger.info("Entity and relation extraction completed")
    logger.info(f"  - Knowledge points: {len(knowledge_points)}")
    logger.info(f"  - Resources: {len(resources)}")
    logger.info(f"  - Relationships: {len(relationships)}")

    logger.info("\n=== Step 3-4: Data Calibration ===")
    calibrated_kps, calibrated_resources, calibrated_rels = calibrate_data(
        knowledge_points, resources, relationships
    )
    logger.info("Data calibration completed")
    logger.info(f"  - Calibrated knowledge points: {len(calibrated_kps)}")
    logger.info(f"  - Calibrated resources: {len(calibrated_resources)}")
    logger.info(f"  - Calibrated relationships: {len(calibrated_rels)}")

    logger.info("\n=== Step 5-6: Build Graph ===")
    build_graph(config)
    logger.info("Graph construction completed")

    logger.info("=" * 60)
    logger.info("Knowledge Graph Construction Pipeline Completed!")
    logger.info("=" * 60)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Knowledge Graph Builder")
    parser.add_argument(
        'step',
        nargs='?',
        choices=['full', 'extract_l1', 'extract', 'calibrate', 'build'],
        default='full',
        help='Which step to run: full (default), extract_l1, extract, calibrate, or build'
    )
    args = parser.parse_args()

    os.makedirs('data/output', exist_ok=True)
    os.makedirs('logs', exist_ok=True)

    config = load_config()

    if args.step == 'full':
        run_full_pipeline(config)
    elif args.step == 'extract_l1':
        run_extract_l1(config)
    elif args.step == 'extract':
        l1_concepts = load_l1_concepts()
        processed_data = load_input_data()
        knowledge_points, resources, relationships = extract_entities_relations(
            processed_data, l1_concepts, config
        )
        logger.info(f"Extraction completed: {len(knowledge_points)} KPs, {len(resources)} resources, {len(relationships)} relations")
    elif args.step == 'calibrate':
        from knowledge_graph.utils.config import load_entities_relations
        knowledge_points, resources, relationships = load_entities_relations()
        calibrated_kps, calibrated_resources, calibrated_rels = calibrate_data(
            knowledge_points, resources, relationships
        )
        logger.info(f"Calibration completed: {len(calibrated_kps)} KPs, {len(calibrated_resources)} resources, {len(calibrated_rels)} relations")
    elif args.step == 'build':
        build_graph(config)
        logger.info("Graph build completed")


if __name__ == "__main__":
    main()
