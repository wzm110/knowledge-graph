#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Node 7: 评测智能体
使用LLM评估知识图谱质量
"""

import json

from knowledge_graph.agents.base_agent import LLMAgent, AgentState


class EvaluationAgent(LLMAgent):
    """评估知识图谱质量的智能体"""

    def __init__(self, config: dict):
        super().__init__(
            name="Evaluation",
            config=config,
            prompt_path="prompts/Evaluation_Prompt.txt"
        )

    def prepare_evaluation_data(self, state: AgentState) -> dict:
        """准备评估数据"""
        kps = state.get('calibrated_kps', [])
        resources = state.get('calibrated_resources', [])
        relationships = state.get('calibrated_relationships', [])
        
        l1_kps = [kp for kp in kps if kp.get('level') == 'L1']
        l2_kps = [kp for kp in kps if kp.get('level') == 'L2']
        l3_kps = [kp for kp in kps if kp.get('level') == 'L3']
        
        rel_types = {}
        for rel in relationships:
            rel_type = rel.get('type', 'unknown')
            rel_types[rel_type] = rel_types.get(rel_type, 0) + 1
        
        return {
            'l1_list': [kp['name'] for kp in l1_kps],
            'kp_count': len(kps),
            'l1_count': len(l1_kps),
            'l2_count': len(l2_kps),
            'l3_count': len(l3_kps),
            'res_count': len(resources),
            'rel_count': len(relationships),
            'rel_types': json.dumps(rel_types, ensure_ascii=False)
        }

    def execute(self, state: AgentState) -> AgentState:
        """执行评估"""
        self.log("开始知识图谱评估")
        
        data = self.prepare_evaluation_data(state)
        
        prompt_template = self.load_prompt()
        
        prompt = prompt_template.replace("{l1_list}", json.dumps(data['l1_list'], ensure_ascii=False, indent=2))
        prompt = prompt.replace("{kp_count}", str(data['kp_count']))
        prompt = prompt.replace("{l1_count}", str(data['l1_count']))
        prompt = prompt.replace("{l2_count}", str(data['l2_count']))
        prompt = prompt.replace("{l3_count}", str(data['l3_count']))
        prompt = prompt.replace("{res_count}", str(data['res_count']))
        prompt = prompt.replace("{rel_count}", str(data['rel_count']))
        prompt = prompt.replace("{rel_types}", data['rel_types'])
        
        try:
            response = self.call_llm(prompt, "")
            result = json.loads(response)
            
            state['evaluation_report'] = result
            state['current_step'] = 'evaluate'
            
            self.save_yaml(result, 'data/output/evaluation_report.json')
            
            self.log(f"评估完成。总体评分: {result.get('overall_score', 'N/A')}/10")
            
        except json.JSONDecodeError as e:
            self.log(f"JSON解析错误: {e}", "error")
            state['errors'].append(f"解析评估结果失败: {e}")
        except Exception as e:
            self.log(f"评估错误: {e}", "error")
            state['errors'].append(str(e))
        
        return state


def create_evaluation_agent(config: dict) -> EvaluationAgent:
    """工厂函数：创建评测智能体"""
    return EvaluationAgent(config)
