#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
使用LangGraph的完整流水线
整合所有8个节点并带有验证循环
"""

import os

from knowledge_graph.utils.config import load_config
from knowledge_graph.utils.logger import get_logger

logger = get_logger(__name__)

MAX_VALIDATION_LOOPS = 3


class PipelineState(dict):
    """知识图谱流水线的统一状态"""
    pass


def extract_l1(state: PipelineState) -> PipelineState:
    """Node 1: 提取L1知识点"""
    from knowledge_graph.agents.l1_extractor import create_l1_extractor
    
    logger.info("=" * 60)
    logger.info("步骤 1: 提取L1知识点")
    logger.info("=" * 60)
    
    validation_errors = state.get('validation_errors', [])
    extractor = create_l1_extractor(state['config'])
    
    if validation_errors:
        feedback = "\n".join([
            f"- {err['name']}: {err['feedback']}"
            for err in validation_errors
        ])
        extractor.set_feedback(feedback)
        logger.info(f"根据{len(validation_errors)}个失败概念进行反馈提取")
    
    state = extractor.execute(state)
    return state


def validate_l1(state: PipelineState) -> PipelineState:
    """Node 2: 验证L1知识点"""
    from knowledge_graph.agents.l1_validator import create_l1_validator
    
    logger.info("=" * 60)
    logger.info("步骤 2: 验证L1知识点")
    logger.info("=" * 60)
    
    validator = create_l1_validator(state['config'])
    state = validator.execute(state)
    return state


def extract_prerequisites(state: PipelineState) -> PipelineState:
    """Node 3: 提取L1前置关系"""
    from knowledge_graph.agents.l1_prerequisite import create_l1_prerequisite_agent
    
    logger.info("=" * 60)
    logger.info("步骤 3: 提取L1前置关系")
    logger.info("=" * 60)
    
    agent = create_l1_prerequisite_agent(state['config'])
    state = agent.execute(state)
    return state


def extract_entities(state: PipelineState) -> PipelineState:
    """Node 4: 提取实体和关系"""
    from knowledge_graph.agents.entity_extractor import create_entity_extractor
    
    logger.info("=" * 60)
    logger.info("步骤 4: 提取实体和关系")
    logger.info("=" * 60)
    
    agent = create_entity_extractor(state['config'])
    state = agent.execute(state)
    return state


def vectorize(state: PipelineState) -> PipelineState:
    """Node 5: 向量化"""
    from knowledge_graph.agents.vectorization import create_vectorization_agent
    
    logger.info("=" * 60)
    logger.info("步骤 5: 向量化")
    logger.info("=" * 60)
    
    agent = create_vectorization_agent(state['config'])
    state = agent.execute(state)
    return state


def calibrate(state: PipelineState) -> PipelineState:
    """Node 6: 数据校准"""
    from knowledge_graph.agents.calibration import create_calibration_agent
    
    logger.info("=" * 60)
    logger.info("步骤 6: 数据校准")
    logger.info("=" * 60)
    
    agent = create_calibration_agent(state['config'])
    state = agent.execute(state)
    return state


def evaluate(state: PipelineState) -> PipelineState:
    """Node 7: LLM评测"""
    from knowledge_graph.agents.evaluation import create_evaluation_agent
    
    logger.info("=" * 60)
    logger.info("步骤 7: LLM评测")
    logger.info("=" * 60)
    
    agent = create_evaluation_agent(state['config'])
    state = agent.execute(state)
    return state


def build_graph(state: PipelineState) -> PipelineState:
    """Node 8: 构建Neo4j图"""
    from knowledge_graph.agents.graph_builder import create_graph_builder_agent
    
    logger.info("=" * 60)
    logger.info("步骤 8: 构建Neo4j图")
    logger.info("=" * 60)
    
    agent = create_graph_builder_agent(state['config'])
    state = agent.execute(state)
    return state


def should_rerun_extraction(state: PipelineState) -> str:
    """根据验证结果判断是否重新运行提取"""
    iteration = state.get('iteration', 1)
    validation_errors = state.get('validation_errors', [])
    
    if validation_errors and iteration < MAX_VALIDATION_LOOPS:
        logger.info(f"验证发现{len(validation_errors)}个错误，将重新运行(迭代{iteration + 1})")
        return "extract_l1"
    elif validation_errors and iteration >= MAX_VALIDATION_LOOPS:
        logger.warning(f"已达到最大验证循环次数({MAX_VALIDATION_LOOPS})，继续执行")
        return "extract_prerequisites"
    else:
        logger.info("验证通过，继续下一步")
        return "extract_prerequisites"


def run_full_pipeline(config: dict, max_loops: int = MAX_VALIDATION_LOOPS, test_mode: bool = False, max_chapters: int = 2):
    """运行完整的8步流水线并带有验证循环
    
    参数:
        config: 配置字典
        max_loops: 步骤2的最大验证循环次数
        test_mode: 如果为True，仅处理少量章节用于快速测试
        max_chapters: 测试模式下的最大章节数
    """
    global MAX_VALIDATION_LOOPS
    MAX_VALIDATION_LOOPS = max_loops
    
    logger.info("=" * 60)
    logger.info("开始知识图谱构建流水线 (8步)")
    if test_mode:
        logger.info(f"测试模式：仅处理{max_chapters}个章节")
    logger.info("=" * 60)
    
    # 初始化状态
    state = PipelineState({
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
        'neo4j_imported': False,
        'l1_extraction_feedback': ''
    })
    
    # =====================
    # 阶段1: L1提取与验证（带循环）
    # =====================
    iteration = 1
    while iteration <= MAX_VALIDATION_LOOPS:
        state['iteration'] = iteration
        
        logger.info(f"\n{'='*60}")
        logger.info(f"=== 迭代 {iteration}/{MAX_VALIDATION_LOOPS} ===")
        logger.info(f"{'='*60}")
        
        state = extract_l1(state)
        
        if state.get('errors'):
            logger.error(f"提取失败: {state['errors']}")
            break
        
        state = validate_l1(state)
        
        if state.get('errors'):
            logger.error(f"验证失败: {state['errors']}")
            break
        
        validation_errors = state.get('validation_errors', [])
        
        if not validation_errors:
            logger.info(f"✓ 迭代{iteration}中验证通过")
            break
        else:
            logger.warning(f"✗ 验证未通过，有{len(validation_errors)}个错误")
            for error in validation_errors:
                logger.warning(f"  - {error['name']}: {error.get('feedback', '')[:80]}...")
            
            if iteration < MAX_VALIDATION_LOOPS:
                iteration += 1
                state['iteration'] = iteration
            else:
                logger.warning(f"已达到最大循环次数({MAX_VALIDATION_LOOPS})，继续执行")
                break
    
    # =====================
    # 阶段2-8: 继续执行剩余步骤
    # =====================
    try:
        state = extract_prerequisites(state)
        
        # 传递测试模式信息到实体提取
        if test_mode:
            state['_test_mode'] = True
            state['_max_chapters'] = max_chapters
            logger.info(f"测试模式：将仅处理{max_chapters}个章节")
        
        state = extract_entities(state)
        state = vectorize(state)
        state = calibrate(state)
        state = evaluate(state)
        state = build_graph(state)
    except Exception as e:
        logger.error(f"执行剩余步骤时出错: {e}")
        state['errors'].append(str(e))
    
    # =====================
    # 总结
    # =====================
    logger.info("\n" + "=" * 60)
    logger.info("流水线完成!")
    logger.info("=" * 60)
    logger.info(f"L1知识点: {len(state.get('validated_l1_concepts', []))}")
    logger.info(f"知识点: {len(state.get('knowledge_points', []))}")
    logger.info(f"资源: {len(state.get('resources', []))}")
    logger.info(f"关系: {len(state.get('relationships', []))}")
    logger.info(f"向量库已更新: {state.get('vector_db_updated', False)}")
    logger.info(f"Neo4j已导入: {state.get('neo4j_imported', False)}")
    
    if state.get('evaluation_report'):
        score = state['evaluation_report'].get('overall_score', 'N/A')
        logger.info(f"评测评分: {score}/10")
    
    return state


def main():
    """主入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description="知识图谱构建流水线")
    parser.add_argument('--max-loops', type=int, default=3,
                       help='最大验证循环次数 (默认: 3)')
    parser.add_argument('--steps', type=str, default='1-8',
                       help='要运行的步骤 (如: 1-2, 3-8, 8)')
    parser.add_argument('--test', action='store_true',
                       help='测试模式：仅处理2个章节用于快速验证')
    args = parser.parse_args()
    
    config = load_config()
    os.makedirs('data/output', exist_ok=True)
    os.makedirs('logs', exist_ok=True)
    
    final_state = run_full_pipeline(config, max_loops=args.max_loops, test_mode=args.test)
    
    logger.info("\n完成!")


if __name__ == "__main__":
    main()
