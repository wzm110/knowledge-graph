#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
使用 LangGraph 的主管道
通过验证循环实现八步知识图谱构建
"""

import os
from typing import TypedDict, List, Dict

from knowledge_graph.utils.config import load_config
from knowledge_graph.utils.logger import get_logger
from knowledge_graph.agents.l1_extractor import create_l1_extractor
from knowledge_graph.agents.l1_validator import create_l1_validator

logger = get_logger(__name__)

MAX_VALIDATION_LOOPS = 3


class PipelineState(TypedDict):
    """统一状态表示知识图谱管道的状态。"""
    config: dict
    current_step: str
    iteration: int
    errors: List[str]
    
    # Input
    toc_files: List[dict]
    textbook_data: List[dict]
    
    # Step 1: L1 Extraction
    l1_concepts: List[dict]
    l1_extraction_prompt: str
    
    # Step 2: L1 Validation
    validated_l1_concepts: List[dict]
    validation_summary: dict
    validation_errors: List[dict]
    
    # Step 3: L1 Prerequisites
    l1_prerequisites: List[dict]
    
    # Step 4: Entity/Relation Extraction
    knowledge_points: List[dict]
    resources: List[dict]
    relationships: List[dict]
    
    # Step 5: Vectorization
    vector_db_updated: bool
    
    # Step 6: Calibration
    calibrated_kps: List[dict]
    calibrated_resources: List[dict]
    calibrated_relationships: List[dict]
    
    # Step 7: Evaluation
    evaluation_report: dict
    
    # Step 8: Graph Build
    neo4j_imported: bool


def extract_l1(state: PipelineState) -> PipelineState:
    """Node 1: Extract L1 knowledge points with optional feedback."""
    logger.info("=" * 60)
    logger.info("Step 1: Extract L1 Knowledge Points")
    logger.info("=" * 60)
    
    extractor = create_l1_extractor(state['config'])
    
    validation_errors = state.get('validation_errors', [])
    if validation_errors:
        feedback = "\n".join([
            f"- {err['name']}: {err['feedback']}"
            for err in validation_errors
        ])
        state['l1_extraction_feedback'] = feedback
        extractor.set_feedback(feedback)
        logger.info(f"Extracting with feedback from {len(validation_errors)} failed concepts")
    
    state = extractor.execute(state)
    
    if state.get('errors'):
        logger.error(f"Extraction failed: {state['errors']}")
    
    return state


def validate_l1(state: PipelineState) -> PipelineState:
    """Node 2: Validate L1 knowledge points."""
    logger.info("=" * 60)
    logger.info("Step 2: Validate L1 Knowledge Points")
    logger.info("=" * 60)
    
    validator = create_l1_validator(state['config'])
    state = validator.execute(state)
    
    if state.get('errors'):
        logger.error(f"Validation failed: {state['errors']}")
    
    return state


def should_rerun_extraction(state: PipelineState) -> str:
    """Decide whether to rerun extraction based on validation results.
    
    Returns:
        "extract_l1" to rerun extraction
        "extract_prerequisites" to proceed to next step
    """
    iteration = state.get('iteration', 1)
    validation_errors = state.get('validation_errors', [])
    
    if validation_errors and iteration < MAX_VALIDATION_LOOPS:
        logger.info(f"Validation found {len(validation_errors)} errors, will rerun extraction (iteration {iteration + 1})")
        return "extract_l1"
    elif validation_errors and iteration >= MAX_VALIDATION_LOOPS:
        logger.warning(f"Max validation loops ({MAX_VALIDATION_LOOPS}) reached, proceeding anyway")
        return "extract_prerequisites"
    else:
        logger.info("Validation passed, proceeding to next step")
        return "extract_prerequisites"


def build_full_pipeline():
    """Build the full LangGraph pipeline."""
    from langgraph.graph import StateGraph
    
    graph = StateGraph(PipelineState)
    
    graph.add_node("extract_l1", extract_l1)
    graph.add_node("validate_l1", validate_l1)
    
    graph.set_entry_point("extract_l1")
    graph.add_edge("extract_l1", "validate_l1")
    
    graph.add_conditional_edges(
        "validate_l1",
        should_rerun_extraction,
        {
            "extract_l1": "extract_l1",
            "extract_prerequisites": END
        }
    )
    
    return graph.compile()


def run_pipeline(config: dict, max_loops: int = MAX_VALIDATION_LOOPS):
    """Run the complete pipeline with validation loop.
    
    This implements the logic:
    1. Extract L1 → Validate L1
    2. If validation fails → Loop back to Extract (up to max_loops times)
    3. If validation passes → Continue to next steps
    """
    global MAX_VALIDATION_LOOPS
    MAX_VALIDATION_LOOPS = max_loops
    
    logger.info("=" * 60)
    logger.info("Starting Knowledge Graph Construction Pipeline")
    logger.info("=" * 60)
    
    state: PipelineState = {
        'config': config,
        'current_step': 'init',
        'iteration': 1,
        'errors': [],
        'toc_files': [],
        'textbook_data': [],
        'l1_concepts': [],
        'l1_extraction_prompt': '',
        'validated_l1_concepts': [],
        'validation_summary': {},
        'validation_errors': [],
        'l1_prerequisites': [],
        'knowledge_points': [],
        'resources': [],
        'relationships': [],
        'vector_db_updated': False,
        'calibrated_kps': [],
        'calibrated_resources': [],
        'calibrated_relationships': [],
        'evaluation_report': {},
        'neo4j_imported': False
    }
    
    iteration = 1
    
    while iteration <= MAX_VALIDATION_LOOPS:
        state['iteration'] = iteration
        
        logger.info(f"\n{'='*60}")
        logger.info(f"Iteration {iteration}/{MAX_VALIDATION_LOOPS}")
        logger.info(f"{'='*60}")
        
        state = extract_l1(state)
        
        if state.get('errors'):
            logger.error(f"Extraction failed: {state['errors']}")
            break
        
        state = validate_l1(state)
        
        if state.get('errors'):
            logger.error(f"Validation failed: {state['errors']}")
            break
        
        validation_errors = state.get('validation_errors', [])
        
        if not validation_errors:
            logger.info(f"✓ Validation passed in iteration {iteration}")
            break
        else:
            logger.warning(f"✗ Validation failed with {len(validation_errors)} errors")
            for error in validation_errors:
                logger.warning(f"  - {error['name']}: {error['feedback'][:100]}...")
            
            if iteration < MAX_VALIDATION_LOOPS:
                iteration += 1
                state['iteration'] = iteration
            else:
                logger.warning(f"Max loops reached ({MAX_VALIDATION_LOOPS}), proceeding anyway")
                break
    
    logger.info("\n" + "=" * 60)
    logger.info("Steps 1-2 (L1 Extraction & Validation) Completed")
    logger.info("=" * 60)
    logger.info(f"Final L1 concepts: {len(state.get('validated_l1_concepts', []))}")
    logger.info(f"Validation summary: {state.get('validation_summary', {})}")
    
    return state


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Knowledge Graph Builder Pipeline")
    parser.add_argument('--max-loops', type=int, default=3,
                       help='Max validation loops (default: 3)')
    args = parser.parse_args()
    
    config = load_config()
    os.makedirs('data/output', exist_ok=True)
    os.makedirs('logs', exist_ok=True)
    
    final_state = run_pipeline(config, max_loops=args.max_loops)
    
    logger.info("\nPipeline completed!")
    logger.info(f"Final state keys: {list(final_state.keys())}")


if __name__ == "__main__":
    main()
