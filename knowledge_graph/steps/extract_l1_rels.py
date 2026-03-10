#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Step 3: Extract L1 Prerequisite Relationships
Extract learning prerequisite relationships between L1 concepts using LLM
"""

import os
import json
import yaml
import pandas as pd

from knowledge_graph.utils.llm import call_llm
from knowledge_graph.utils.logger import get_logger

logger = get_logger(__name__)

PREREQUISITE_EXTRACTION_PROMPT = """你是一名专业的课程体系设计专家，擅长分析知识点之间的学习依赖关系。

给定以下L1知识点列表，请分析它们之间的学习前置关系。

L1知识点列表：
{l1_list}

请分析哪些知识点是其他知识点的前置条件。学习前置关系是指：学习某个知识点之前需要先掌握另一个知识点。

输出格式（JSON）：
{{
    "prerequisites": [
        {{
            "from_l1": "前置知识点名称",
            "to_l1": "后续知识点名称",
            "reason": "为什么需要先学习这个前置知识点"
        }}
    ],
    "reasoning": "整体推理过程说明"
}}

注意：
1. 只输出确实存在明确前置关系的知识点对
2. 如果两个知识点没有明显的依赖关系，不要添加到列表中
3. 考虑学习顺序的合理性
"""


def extract_prerequisite_pair(l1_list: list, config: dict) -> list:
    """Extract prerequisite relationships for a pair of L1 concepts."""
    l1_names = [kp['name'] for kp in l1_list]

    prompt = PREREQUISITE_EXTRACTION_PROMPT.format(
        l1_list=json.dumps(l1_names, ensure_ascii=False, indent=2)
    )

    try:
        response = call_llm(prompt, "", config)
        result = json.loads(response)

        prerequisites = result.get('prerequisites', [])
        logger.info(f"Extracted {len(prerequisites)} prerequisite relationships")

        return prerequisites

    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse LLM response: {e}")
        return []
    except Exception as e:
        logger.error(f"Error extracting prerequisites: {e}")
        return []


def convert_to_relationships(prerequisites: list, l1_concepts: list) -> list:
    """Convert prerequisite extractions to relationship format."""
    l1_id_map = {kp['name']: kp['id'] for kp in l1_concepts}

    relationships = []
    for prereq in prerequisites:
        from_name = prereq.get('from_l1', '')
        to_name = prereq.get('to_l1', '')

        from_id = l1_id_map.get(from_name)
        to_id = l1_id_map.get(to_name)

        if from_id and to_id:
            relationships.append({
                'type': 'prerequisite',
                'start_id': from_id,
                'end_id': to_id,
                'end_type': 'L1',
                'reason': prereq.get('reason', '')
            })

    return relationships


def extract_l1_prerequisite_relationships(l1_concepts: list, config: dict) -> list:
    """Extract all L1 prerequisite relationships using LLM."""
    logger.info("Extracting L1 prerequisite relationships using LLM")

    prerequisites = extract_prerequisite_pair(l1_concepts, config)

    relationships = convert_to_relationships(prerequisites, l1_concepts)

    logger.info(f"Extracted {len(relationships)} L1 prerequisite relationships")

    return relationships


def save_l1_prerequisites(relationships: list, output_file: str = "data/output/l1_prerequisites.csv"):
    """Save L1 prerequisite relationships to CSV."""
    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    if relationships:
        df = pd.DataFrame(relationships)
        df.to_csv(output_file, index=False, encoding='utf-8-sig')
        logger.info(f"Saved {len(relationships)} L1 prerequisite relationships to {output_file}")
    else:
        logger.warning("No prerequisite relationships to save")


def run(config: dict):
    """Main function for Step 3."""
    logger.info("=" * 60)
    logger.info("Step 3: Extract L1 Prerequisite Relationships")
    logger.info("=" * 60)

    input_file = "data/output/l1_concepts_validated.yaml"
    if not os.path.exists(input_file):
        input_file = "data/output/l1_concepts.yaml"

    output_file = "data/output/l1_prerequisites.csv"

    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)

        if 'Concepts' in data:
            l1_concepts = data['Concepts']
        elif isinstance(data, list):
            l1_concepts = data
        else:
            l1_concepts = data.get('Concepts', [])

        l1_concepts = [c for c in l1_concepts
                      if not c.get('validation', {}).get('is_valid', True) == False]

    except Exception as e:
        logger.error(f"Failed to load L1 concepts from {input_file}: {e}")
        logger.info("Please run Step 1 and Step 2 first")
        return

    relationships = extract_l1_prerequisite_relationships(l1_concepts, config)
    save_l1_prerequisites(relationships, output_file)

    logger.info("=" * 60)
    logger.info("Step 3 completed!")
    logger.info("=" * 60)


if __name__ == "__main__":
    from knowledge_graph.utils.config import load_config

    config = load_config()
    run(config)
