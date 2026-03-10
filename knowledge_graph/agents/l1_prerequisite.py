#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Node 3: L1前置关系提取智能体
提取L1知识点之间的学习前置关系
"""

import json
import os

from knowledge_graph.agents.base_agent import LLMAgent, AgentState


class L1PrerequisiteAgent(LLMAgent):
    """提取L1前置关系的智能体"""

    def __init__(self, config: dict):
        super().__init__(
            name="L1Prerequisite",
            config=config,
            prompt_path="prompts/L1_Prerequisite_Prompt.txt"
        )

    def execute(self, state: AgentState) -> AgentState:
        """执行L1前置关系提取"""
        self.log("开始提取L1前置关系")
        
        validated_l1 = state.get('validated_l1_concepts', [])
        if not validated_l1:
            state['errors'].append("没有找到已验证的L1知识点")
            return state

        l1_names = [kp['name'] for kp in validated_l1]
        
        prompt_template = self.load_prompt()
        prompt = prompt_template.replace("{l1_list}", json.dumps(l1_names, ensure_ascii=False, indent=2))
        
        self.log(f"调用LLM为 {len(l1_names)} 个L1知识点提取前置关系")
        
        try:
            response = self.call_llm(prompt, "")
            
            response = response.strip()
            if not response.startswith('{'):
                response = '{' + response
            if not response.endswith('}'):
                response = response + '}'
            
            result = json.loads(response)
            prerequisites = result.get('prerequisites', [])
            
            l1_id_map = {kp['name']: kp['id'] for kp in validated_l1}
            
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
            
            state['l1_prerequisites'] = relationships
            state['current_step'] = 'extract_prerequisites'
            
            if relationships:
                self.save_parquet(relationships, 'data/output/stage2_relationships.parquet')
                self.log(f"提取了 {len(relationships)} 条前置关系")
            else:
                self.log("未提取到前置关系", "warning")
                
        except json.JSONDecodeError as e:
            self.log(f"JSON解析错误: {e}", "error")
            state['errors'].append(f"解析LLM响应失败: {e}")
        except Exception as e:
            self.log(f"提取错误: {e}", "error")
            state['errors'].append(str(e))
        
        return state


def create_l1_prerequisite_agent(config: dict) -> L1PrerequisiteAgent:
    """工厂函数：创建L1前置关系提取智能体"""
    return L1PrerequisiteAgent(config)
