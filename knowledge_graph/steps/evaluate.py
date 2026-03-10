#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Step 7: LLM Evaluation
Evaluate knowledge graph quality using LLM
"""

import os
import json
import yaml
import pandas as pd

from knowledge_graph.utils.llm import call_llm
from knowledge_graph.utils.logger import get_logger
from knowledge_graph.utils.config import load_entities_relations

logger = get_logger(__name__)

EVALUATION_PROMPT = """你是一名专业的知识图谱评估专家，擅长评估知识图谱的质量和完整性。

请对以下知识图谱进行全面的质量评估：

## 知识图谱概览

### L1知识点列表：
{l1_list}

### 实体统计：
- 知识点总数：{kp_count}
- 资源总数：{res_count}

### 关系统计：
- 关系总数：{rel_count}
- 关系类型分布：{rel_types}

### 部分关系示例：
{rel_examples}

请从以下维度进行评估：

1. **完整性(Completeness)**: 知识点覆盖是否全面？是否有明显的知识遗漏？
2. **准确性(Accuracy)**: 知识点定义和关系是否准确？
3. **一致性(Consistency)**: 层级结构是否清晰一致？命名是否统一？
4. **可用性(Usability)**: 这个知识图谱能否有效支撑学习路径规划？

输出格式（JSON）：
{{
    "overall_score": 1-10,
    "dimensions": {{
        "completeness": {{"score": 1-10, "feedback": "具体评价"}},
        "accuracy": {{"score": 1-10, "feedback": "具体评价"}},
        "consistency": {{"score": 1-10, "feedback": "具体评价"}},
        "usability": {{"score": 1-10, "feedback": "具体评价"}}
    }},
    "strengths": ["优点1", "优点2"],
    "weaknesses": ["问题1", "问题2"],
    "improvement_suggestions": ["建议1", "建议2"],
    "learning_path_quality": {{
        "can_support_path_planning": true/false,
        "coverage": "学习路径覆盖率评估",
        "gaps": "需要补充的知识"
    }}
}}
"""


def prepare_evaluation_data():
    """Prepare data for evaluation."""
    try:
        entities_file = 'data/output/calibrated_entities.csv'
        if not os.path.exists(entities_file):
            entities_file = 'data/output/entities.csv'

        knowledge_points, resources, relationships = load_entities_relations(
            entities_file=entities_file,
            relationships_file='data/output/calibrated_relationships.csv'
        )

        l1_concepts = [kp for kp in knowledge_points if kp.get('level') == 'L1']
        l2_concepts = [kp for kp in knowledge_points if kp.get('level') == 'L2']
        l3_concepts = [kp for kp in knowledge_points if kp.get('level') == 'L3']

        rel_types = {}
        for rel in relationships:
            rel_type = rel.get('type', 'unknown')
            rel_types[rel_type] = rel_types.get(rel_type, 0) + 1

        rel_examples = relationships[:10] if relationships else []

        return {
            'l1_list': [kp['name'] for kp in l1_concepts],
            'kp_count': len(knowledge_points),
            'res_count': len(resources),
            'rel_count': len(relationships),
            'rel_types': json.dumps(rel_types, ensure_ascii=False),
            'rel_examples': json.dumps(rel_examples, ensure_ascii=False, indent=2),
            'l1_count': len(l1_concepts),
            'l2_count': len(l2_concepts),
            'l3_count': len(l3_concepts)
        }

    except Exception as e:
        logger.error(f"Failed to prepare evaluation data: {e}")
        return None


def evaluate_graph(config: dict) -> dict:
    """Evaluate knowledge graph using LLM."""
    logger.info("Evaluating knowledge graph using LLM")

    data = prepare_evaluation_data()
    if not data:
        logger.error("No data available for evaluation")
        return None

    prompt = EVALUATION_PROMPT.format(
        l1_list=json.dumps(data['l1_list'], ensure_ascii=False, indent=2),
        kp_count=data['kp_count'],
        res_count=data['res_count'],
        rel_count=data['rel_count'],
        rel_types=data['rel_types'],
        rel_examples=data['rel_examples']
    )

    try:
        response = call_llm(prompt, "", config)
        result = json.loads(response)

        logger.info(f"Evaluation completed. Overall score: {result.get('overall_score', 'N/A')}/10")

        return result

    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse evaluation response: {e}")
        return {'error': 'Failed to parse LLM response'}
    except Exception as e:
        logger.error(f"Evaluation failed: {e}")
        return {'error': str(e)}


def save_evaluation_report(evaluation: dict, output_file: str = "data/output/evaluation_report.json"):
    """Save evaluation report to file."""
    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    if evaluation:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(evaluation, f, ensure_ascii=False, indent=2)

        logger.info(f"Saved evaluation report to {output_file}")

        csv_data = [{
            '维度': '完整性',
            '评分': evaluation.get('dimensions', {}).get('completeness', {}).get('score', ''),
            '评价': evaluation.get('dimensions', {}).get('completeness', {}).get('feedback', '')
        }, {
            '维度': '准确性',
            '评分': evaluation.get('dimensions', {}).get('accuracy', {}).get('score', ''),
            '评价': evaluation.get('dimensions', {}).get('accuracy', {}).get('feedback', '')
        }, {
            '维度': '一致性',
            '评分': evaluation.get('dimensions', {}).get('consistency', {}).get('score', ''),
            '评价': evaluation.get('dimensions', {}).get('consistency', {}).get('feedback', '')
        }, {
            '维度': '可用性',
            '评分': evaluation.get('dimensions', {}).get('usability', {}).get('score', ''),
            '评价': evaluation.get('dimensions', {}).get('usability', {}).get('feedback', '')
        }, {
            '维度': '总体评分',
            '评分': evaluation.get('overall_score', ''),
            '评价': ''
        }]

        csv_df = pd.DataFrame(csv_data)
        csv_df.to_csv('data/output/evaluation_scores.csv', index=False, encoding='utf-8-sig')
        logger.info("Saved evaluation scores to CSV")

    else:
        logger.warning("No evaluation result to save")


def run(config: dict):
    """Main function for Step 7."""
    logger.info("=" * 60)
    logger.info("Step 7: LLM Evaluation")
    logger.info("=" * 60)

    evaluation = evaluate_graph(config)
    save_evaluation_report(evaluation)

    logger.info("=" * 60)
    logger.info("Step 7 completed!")
    logger.info("=" * 60)


if __name__ == "__main__":
    from knowledge_graph.utils.config import load_config

    config = load_config()
    run(config)
