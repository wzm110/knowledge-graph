"""Step 1: Extract L1 Concepts from Table of Contents"""

import os
import re
import yaml
import json
import pandas as pd

from knowledge_graph.utils.llm import LLMClient
from knowledge_graph.utils.logger import get_logger

logger = get_logger(__name__)


def load_toc_data(toc_file: str = "data/input/目录.csv") -> str:
    """Load table of contents data."""
    logger.info(f"Loading TOC data from {toc_file}")
    df = pd.read_csv(toc_file, encoding='utf-8-sig')
    text = df.iloc[0]['text']
    logger.info(f"TOC text length: {len(text)} characters")
    return text


def extract_l1_concepts(toc_text: str, config: dict) -> list:
    """Extract L1 concepts from TOC using LLM."""
    logger.info("Extracting L1 concepts from TOC")

    prompt_path = "prompts/L1_Extraction_Prompt.txt"
    with open(prompt_path, 'r', encoding='utf-8') as f:
        prompt_template = f.read()

    lines = toc_text.strip().split('\n')
    chapter_pattern = re.compile(r'^\s*(\d+(?:\.\d+)*)\s*\.?\s*(.+)$')

    chapters = []
    for line in lines:
        match = chapter_pattern.match(line.strip())
        if match:
            number = match.group(1)
            title = match.group(2).strip()
            if number.count('.') == 0 or (number.count('.') == 1 and not title.lower().startswith('chap')):
                chapters.append(title)

    logger.info(f"Found {len(chapters)} potential chapter titles")

    llm_client = LLMClient(config)
    l1_concepts = []

    for i, chapter in enumerate(chapters, 1):
        logger.info(f"Processing chapter {i}/{len(chapters)}: {chapter}")

        prompt = prompt_template.replace("{{topic_name}}", chapter)
        prompt = prompt.replace("{{aliases}}", "[]")

        response = llm_client.chat(prompt)
        try:
            data = json.loads(response)
            concept = {
                'id': f"l1-{i}",
                'name': data.get('name', chapter),
                'aliases': data.get('aliases', []),
                'definition': data.get('definition', ''),
                'level': 'L1'
            }
            l1_concepts.append(concept)
            logger.info(f"  Extracted: {concept['name']}")
        except json.JSONDecodeError:
            concept = {
                'id': f"l1-{i}",
                'name': chapter,
                'aliases': [],
                'definition': '',
                'level': 'L1'
            }
            l1_concepts.append(concept)
            logger.warning(f"  Failed to parse LLM response, using chapter title: {chapter}")

    return l1_concepts


def save_l1_concepts(l1_concepts: list, output_file: str = "data/output/l1_concepts.yaml"):
    """Save L1 concepts to YAML file."""
    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    data = {'Concepts': l1_concepts}
    with open(output_file, 'w', encoding='utf-8') as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False)

    logger.info(f"Saved {len(l1_concepts)} L1 concepts to {output_file}")


def run(config: dict):
    """Main function for Step 1."""
    logger.info("=" * 60)
    logger.info("Step 1: Extract L1 Concepts from Table of Contents")
    logger.info("=" * 60)

    toc_file = "data/input/目录.csv"
    output_file = "data/output/l1_concepts.yaml"

    toc_text = load_toc_data(toc_file)
    l1_concepts = extract_l1_concepts(toc_text, config)
    save_l1_concepts(l1_concepts, output_file)

    logger.info("=" * 60)
    logger.info("Step 1 completed!")
    logger.info("=" * 60)


if __name__ == "__main__":
    from knowledge_graph.utils.config import load_config

    config = load_config()
    run(config)
