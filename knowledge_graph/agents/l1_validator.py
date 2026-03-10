#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Node 2: L1知识点验证智能体（整体评估）
使用整体系统视角验证L1知识点
"""

import json

from knowledge_graph.agents.base_agent import LLMAgent, AgentState


class L1ValidatorAgent(LLMAgent):
    """使用整体评估验证L1知识点的智能体"""

    def __init__(self, config: dict):
        super().__init__(
            name="L1Validator",
            config=config,
            prompt_path="prompts/L1_Validation_Prompt.txt"
        )

    def validate_holistic(self, concepts: list) -> dict:
        """整体验证L1知识系统"""
        prompt_template = self.load_prompt()
        
        all_l1_points = []
        for concept in concepts:
            all_l1_points.append(f"- {concept.get('name', '')}: {concept.get('definition', '')}")
        
        l1_list_str = "\n".join(all_l1_points)
        
        subject = self.config.get('pipeline', {}).get('subject', '深度学习')
        
        prompt = prompt_template.replace("{all_l1_points}", l1_list_str)
        prompt = prompt.replace("{subject}", subject)
        
        try:
            response = self.call_llm(prompt, "")
            result = json.loads(response)
            return result
        except json.JSONDecodeError as e:
            self.log(f"JSON解析错误: {e}", "warning")
            return {'error': str(e), 'is_valid': True}
        except Exception as e:
            self.log(f"错误: {e}", "error")
            return {'error': str(e), 'is_valid': True}

    def execute(self, state: AgentState) -> AgentState:
        """执行L1整体验证"""
        self.log("开始L1知识点整体验证")
        
        l1_concepts = state.get('l1_concepts', [])
        if not l1_concepts:
            l1_concepts = state.get('validated_l1_concepts', [])
        
        if not l1_concepts:
            state['errors'].append("没有可验证的L1知识点")
            return state

        self.log(f"整体验证 {len(l1_concepts)} 个L1知识点")
        
        result = self.validate_holistic(l1_concepts)
        
        validation_summary = {
            'total': len(l1_concepts),
            'valid': 1 if result.get('is_valid', True) else 0,
            'invalid': 0 if result.get('is_valid', True) else 1,
            'overall_score': result.get('overall_score', 0),
            'dimensions': result.get('dimensions', {}),
            'overall_feedback': result.get('overall_feedback', '')
        }
        
        validated_concepts = []
        for concept in l1_concepts:
            validated_concepts.append({
                **concept,
                'validation': {
                    'overall_score': result.get('overall_score', 0),
                    'overall_feedback': result.get('overall_feedback', ''),
                    'is_valid': result.get('is_valid', True)
                }
            })
        
        validation_errors = []
        if not result.get('is_valid', True):
            issues = result.get('issues_found', [])
            feedback = result.get('overall_feedback', '')
            validation_errors.append({
                'name': '整体系统',
                'feedback': f"{feedback}\n问题: {', '.join(issues)}" if issues else feedback,
                'total_score': result.get('overall_score', 0)
            })
        
        state['validated_l1_concepts'] = validated_concepts
        state['validation_summary'] = validation_summary
        state['validation_errors'] = validation_errors
        state['current_step'] = 'validate_l1'

        self.save_parquet(
            validated_concepts,
            'data/output/stage1_entities.parquet'
        )
        
        self.log(f"验证完成。总体评分: {result.get('overall_score', 'N/A')}/10, 有效: {result.get('is_valid', True)}")
        
        return state


def create_l1_validator(config: dict) -> L1ValidatorAgent:
    """工厂函数：创建L1验证智能体"""
    return L1ValidatorAgent(config)
