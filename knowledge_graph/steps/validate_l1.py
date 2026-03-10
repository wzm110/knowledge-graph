#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Step 1.5: Validate L1 Concepts
Validate L1 concepts using LLM and provide quality scores
"""

import os
import json
import yaml
import pandas as pd

from knowledge_graph.utils.llm import LLMClient
from knowledge_graph.utils.logger import get_logger

logger = get_logger(__name__)

VALIDATION_PROMPT = """你是一名专业的课程体系设计专家，擅长评估知识点的质量和完整性。

请对以下L1知识点进行质量评估：

知识点名称：{name}
定义：{definition}
别名：{aliases}

请从以下维度进行打分（1-10分）：

1. **完整性(Completeness)**: 该知识点是否涵盖了主题的核心内容？
2. **准确性(Accuracy)**: 该定义是否准确反映该主题的内容和范围？
3. **区分度(Distinctiveness)**: 该知识点与其他知识点是否有清晰的边界？
4. **教学适用性(Teachability)**: 该知识点是否适合作为教学单元？

输出格式（JSON）：
{{
    "name": "{name}",
    "completeness_score": 1-10,
    "accuracy_score": 1-10,
    "distinctiveness_score": 1-10,
    "teachability_score": 1-10,
    "total_score": 1-10,
    "feedback": "改进建议（如果有）",
    "is_valid": true/false
}}
"""


def validate_l1_concept(concept: dict, llm_client: LLMClient) -> dict:
    """Validate a single L1 concept using LLM."""
    name = concept.get('name', '')
    definition = concept.get('definition', '')
    aliases = concept.get('aliases', [])
    aliases_str = ', '.join(aliases) if aliases else '无'

    prompt = VALIDATION_PROMPT.format(
        name=name,
        definition=definition or '无',
        aliases=aliases_str
    )

    try:
        response = llm_client.chat(prompt)
        result = json.loads(response)

        validated_concept = {
            **concept,
            'validation': {
                'completeness_score': result.get('completeness_score', 0),
                'accuracy_score': result.get('accuracy_score', 0),
                'distinctiveness_score': result.get('distinctiveness_score', 0),
                'teachability_score': result.get('teachability_score', 0),
                'total_score': result.get('total_score', 0),
                'feedback': result.get('feedback', ''),
                'is_valid': result.get('is_valid', True)
            }
        }

        logger.info(f"  Validated: {name}, Score: {result.get('total_score', 0)}/10")
        return validated_concept

    except json.JSONDecodeError as e:
        logger.warning(f"  Failed to parse LLM response for {name}: {e}")
        return {
            **concept,
            'validation': {
                'error': 'Failed to parse LLM response',
                'is_valid': True
            }
        }
    except Exception as e:
        logger.error(f"  Error validating {name}: {e}")
        return {
            **concept,
            'validation': {
                'error': str(e),
                'is_valid': True
            }
        }


def validate_l1_concepts(l1_concepts: list, config: dict) -> list:
    """Validate all L1 concepts using LLM."""
    logger.info("Validating L1 concepts using LLM")

    llm_client = LLMClient(config)
    validated_concepts = []

    for i, concept in enumerate(l1_concepts, 1):
        logger.info(f"Validating concept {i}/{len(l1_concepts)}")
        validated = validate_l1_concept(concept, llm_client)
        validated_concepts.append(validated)

    valid_count = sum(1 for c in validated_concepts
                     if c.get('validation', {}).get('is_valid', True))
    avg_score = sum(c.get('validation', {}).get('total_score', 0)
                   for c in validated_concepts) / len(validated_concepts)

    logger.info(f"Validation completed: {valid_count}/{len(validated_concepts)} valid concepts")
    logger.info(f"Average score: {avg_score:.2f}/10")

    return validated_concepts


def save_validated_l1(validated_concepts: list, output_file: str = "data/output/l1_concepts_validated.yaml"):
    """Save validated L1 concepts to YAML file."""
    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    valid_concepts = [c for c in validated_concepts
                     if c.get('validation', {}).get('is_valid', True)]
    invalid_concepts = [c for c in validated_concepts
                       if not c.get('validation', {}).get('is_valid', True)]

    data = {
        'Concepts': validated_concepts,
        'summary': {
            'total': len(validated_concepts),
            'valid': len(valid_concepts),
            'invalid': len(invalid_concepts),
            'average_score': sum(c.get('validation', {}).get('total_score', 0)
                               for c in validated_concepts) / len(validated_concepts) if validated_concepts else 0
        }
    }

    with open(output_file, 'w', encoding='utf-8') as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False)

    logger.info(f"Saved {len(validated_concepts)} validated concepts to {output_file}")


def save_validation_report(validated_concepts: list, output_file: str = "data/output/l1_validation_report.csv"):
    """Save validation report as CSV."""
    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    report_data = []
    for concept in validated_concepts:
        validation = concept.get('validation', {})
        report_data.append({
            'id': concept.get('id', ''),
            'name': concept.get('name', ''),
            'completeness_score': validation.get('completeness_score', ''),
            'accuracy_score': validation.get('accuracy_score', ''),
            'distinctiveness_score': validation.get('distinctiveness_score', ''),
            'teachability_score': validation.get('teachability_score', ''),
            'total_score': validation.get('total_score', ''),
            'is_valid': validation.get('is_valid', True),
            'feedback': validation.get('feedback', '')
        })

    df = pd.DataFrame(report_data)
    df.to_csv(output_file, index=False, encoding='utf-8-sig')

    logger.info(f"Saved validation report to {output_file}")


def run(config: dict):
    """Main function for Step 1.5."""
    logger.info("=" * 60)
    logger.info("Step 1.5: Validate L1 Concepts")
    logger.info("=" * 60)

    input_file = "data/output/l1_concepts.yaml"
    output_file = "data/output/l1_concepts_validated.yaml"
    report_file = "data/output/l1_validation_report.csv"

    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        l1_concepts = data.get('Concepts', [])
    except Exception as e:
        logger.error(f"Failed to load L1 concepts from {input_file}: {e}")
        logger.info("Please run Step 1 first to extract L1 concepts")
        return

    validated_concepts = validate_l1_concepts(l1_concepts, config)
    save_validated_l1(validated_concepts, output_file)
    save_validation_report(validated_concepts, report_file)

    logger.info("=" * 60)
    logger.info("Step 1.5 completed!")
    logger.info("=" * 60)


if __name__ == "__main__":
    from knowledge_graph.utils.config import load_config

    config = load_config()
    run(config)
