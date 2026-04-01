"""Knowledge Graph Builder - Main Entry Point"""

import os
import argparse

from knowledge_graph.utils.logger import get_logger
from knowledge_graph.utils.config import load_config

logger = get_logger(__name__)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="知识图谱构建流水线 - 8步")
    parser.add_argument(
        'step',
        nargs='?',
        choices=[
            'full',           # 全部8步
            'extract_l1',    # 步骤1
            'validate_l1',   # 步骤2
            'extract_l1_rels', # 步骤3
            'extract',       # 步骤4
            'vectorize',     # 步骤5
            'calibrate',     # 步骤6
            'evaluate',      # 步骤7
            'build'          # 步骤8
        ],
        default='full',
        help='选择要运行的步骤'
    )
    parser.add_argument('--test', action='store_true',
                       help='测试模式：仅处理2个章节用于快速验证')
    parser.add_argument('--max-loops', type=int, default=3,
                       help='最大验证循环次数 (默认: 3)')
    parser.add_argument('--max-eval-loops', type=int, default=5,
                       help='最大评估-微调循环次数 (默认: 5)')
    parser.add_argument('--full-refresh-l1', action='store_true',
                       help='全量重跑 L1 抽取与验证（即使已存在 stage1_entities.parquet 也不跳过）')
    args = parser.parse_args()

    os.makedirs('data/output', exist_ok=True)
    os.makedirs('logs', exist_ok=True)

    config = load_config()

    if args.step == 'full':
        from knowledge_graph.pipeline import run_full_pipeline
        run_full_pipeline(
            config,
            max_loops=args.max_loops,
            max_eval_loops=args.max_eval_loops,
            test_mode=args.test,
            skip_l1_if_exists=not args.full_refresh_l1
        )
    elif args.step == 'extract_l1':
        from knowledge_graph.agents.l1_extractor import create_l1_extractor
        agent = create_l1_extractor(config)
        from knowledge_graph.pipeline import PipelineState
        state = PipelineState({'config': config})
        state = agent.execute(state)
        logger.info(f"步骤1完成: 提取了 {len(state.get('l1_concepts', []))} 个L1知识点")
    elif args.step == 'validate_l1':
        from knowledge_graph.agents.l1_validator import create_l1_validator
        agent = create_l1_validator(config)
        from knowledge_graph.pipeline import PipelineState
        state = PipelineState({'config': config})
        state = agent.execute(state)
        logger.info(f"步骤2完成: 验证了 {len(state.get('validated_l1_concepts', []))} 个L1知识点")
    elif args.step == 'extract_l1_rels':
        from knowledge_graph.agents.l1_prerequisite import create_l1_prerequisite_agent
        agent = create_l1_prerequisite_agent(config)
        from knowledge_graph.pipeline import PipelineState
        state = PipelineState({'config': config})
        state = agent.execute(state)
        logger.info(f"步骤3完成: 提取了 {len(state.get('l1_prerequisites', []))} 条前置关系")
    elif args.step == 'extract':
        from knowledge_graph.agents.entity_extractor import create_entity_extractor
        agent = create_entity_extractor(config)
        from knowledge_graph.pipeline import PipelineState
        state = PipelineState({'config': config, '_test_mode': args.test, '_max_chapters': 2})
        state = agent.execute(state)
        logger.info(f"步骤4完成: {len(state.get('knowledge_points', []))} 个知识点, {len(state.get('resources', []))} 个资源, {len(state.get('relationships', []))} 条关系")
    elif args.step == 'vectorize':
        from knowledge_graph.agents.vectorization import create_vectorization_agent
        agent = create_vectorization_agent(config)
        from knowledge_graph.pipeline import PipelineState
        state = PipelineState({'config': config})
        state = agent.execute(state)
        logger.info(f"步骤5完成: 向量化完成")
    elif args.step == 'calibrate':
        from knowledge_graph.agents.calibration import create_calibration_agent
        agent = create_calibration_agent(config)
        from knowledge_graph.pipeline import PipelineState
        state = PipelineState({'config': config})
        state = agent.execute(state)
        logger.info(f"步骤6完成: {len(state.get('calibrated_kps', []))} 个知识点, {len(state.get('calibrated_resources', []))} 个资源, {len(state.get('calibrated_relationships', []))} 条关系")
    elif args.step == 'evaluate':
        from knowledge_graph.agents.evaluation import create_evaluation_agent
        agent = create_evaluation_agent(config)
        from knowledge_graph.pipeline import PipelineState
        state = PipelineState({'config': config})
        state = agent.execute(state)
        logger.info(f"步骤7完成: 评测完成")
    elif args.step == 'build':
        from knowledge_graph.agents.graph_builder import create_graph_builder_agent
        agent = create_graph_builder_agent(config)
        from knowledge_graph.pipeline import PipelineState
        state = PipelineState({'config': config})
        state = agent.execute(state)
        logger.info(f"步骤8完成: 图谱构建完成")


if __name__ == "__main__":
    main()
