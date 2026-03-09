#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Configuration utilities"""

import yaml
import os
import pandas as pd

from knowledge_graph.utils.logger import get_logger

logger = get_logger(__name__)


def load_config(config_file='config/default.yaml'):
    """Load configuration file."""
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        logger.info(f"Loaded config file: {config_file}")
        return config
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        raise


def load_l1_concepts(l1_file='data/output/l1_concepts.yaml'):
    """Load predefined L1 concepts."""
    try:
        with open(l1_file, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        l1_concepts = data.get('Concepts', [])
        logger.info(f"Loaded {len(l1_concepts)} L1 concepts")
        return l1_concepts
    except Exception as e:
        logger.error(f"Failed to load L1 concepts: {e}")
        raise


def load_entities_relations(
    entities_file='data/output/entities.csv',
    relationships_file='data/output/relationships.csv'
):
    """Load entities and relationships from CSV files."""
    try:
        entities_df = pd.read_csv(entities_file, encoding='utf-8')
        relationships_df = pd.read_csv(relationships_file, encoding='utf-8')

        knowledge_points = []
        resources = []

        for _, row in entities_df.iterrows():
            if row['type'] == 'KnowledgePoint':
                knowledge_points.append({
                    'id': row['id'],
                    'name': row['name'],
                    'level': row['level'],
                    'description': row.get('description', ''),
                    'difficulty': row.get('difficulty', ''),
                    'aliases': row.get('aliases', '').split(',') if pd.notna(row.get('aliases', '')) else []
                })
            elif row['type'] == 'Resource':
                resources.append({
                    'id': row['id'],
                    'url': row.get('url', ''),
                    'resource_type': row.get('resource_type', '')
                })

        relationships = []
        for _, row in relationships_df.iterrows():
            relationships.append({
                'type': row['type'],
                'start_id': row['start_id'],
                'end_id': row['end_id'],
                'end_type': row.get('end_type', '')
            })

        logger.info(f"Loaded {len(knowledge_points)} knowledge points, {len(resources)} resources, {len(relationships)} relationships")
        return knowledge_points, resources, relationships

    except Exception as e:
        logger.error(f"Failed to load entities/relations: {e}")
        raise


def load_calibrated_data(
    entities_file='data/output/calibrated_entities.csv',
    relationships_file='data/output/calibrated_relationships.csv'
):
    """Load calibrated entities and relationships."""
    return load_entities_relations(entities_file, relationships_file)
