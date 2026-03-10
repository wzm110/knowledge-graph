#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Step 5: Vectorization
Vectorize entities and store in vector database
"""

import os

from knowledge_graph.utils.logger import get_logger
from knowledge_graph.utils.vector_db import VectorDBManager
from knowledge_graph.utils.config import load_entities_relations

logger = get_logger(__name__)


def vectorize_entities(config: dict, force_recreate: bool = False):
    """Vectorize all entities and store in vector database."""
    logger.info("=" * 60)
    logger.info("Step 5: Vectorization")
    logger.info("=" * 60)

    try:
        entities_file = 'data/output/calibrated_entities.csv'
        if not os.path.exists(entities_file):
            entities_file = 'data/output/entities.csv'

        logger.info(f"Loading entities from {entities_file}")
        knowledge_points, resources, _ = load_entities_relations(
            entities_file=entities_file,
            relationships_file='data/output/calibrated_relationships.csv'
        )

        all_entities = knowledge_points + resources

        logger.info(f"Loaded {len(all_entities)} entities to vectorize")

        vector_db = VectorDBManager(config, force_recreate=force_recreate)

        vector_db.add_entities(all_entities)

        logger.info(f"Successfully vectorized {len(all_entities)} entities")

    except FileNotFoundError as e:
        logger.error(f"Entity file not found: {e}")
        logger.info("Please run Step 4 first")
    except Exception as e:
        logger.error(f"Vectorization failed: {e}")
        raise


def run(config: dict, force_recreate: bool = False):
    """Main function for Step 5."""
    vectorize_entities(config, force_recreate)

    logger.info("=" * 60)
    logger.info("Step 5 completed!")
    logger.info("=" * 60)


if __name__ == "__main__":
    from knowledge_graph.utils.config import load_config
    import argparse

    parser = argparse.ArgumentParser(description="Step 5: Vectorization")
    parser.add_argument('--force', action='store_true',
                       help='Force recreate vector database')
    args = parser.parse_args()

    config = load_config()
    run(config, force_recreate=args.force)
