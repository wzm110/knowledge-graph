#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Node 5: 向量化智能体
将实体向量化并存入向量数据库
"""

import os

from knowledge_graph.agents.base_agent import BaseAgent, AgentState


class VectorizationAgent(BaseAgent):
    """向量化实体并存储到向量数据库的智能体"""

    def __init__(self, config: dict):
        super().__init__(name="Vectorization", config=config)

    def execute(self, state: AgentState) -> AgentState:
        """执行向量化"""
        self.log("开始向量化")
        
        try:
            from knowledge_graph.utils.vector_db import VectorDBManager
            
            # 仅向量化知识点；资源仍由 Step4 落盘 stage3_resources，后续独立步骤入图，此处不参与以节省成本
            kps = state.get('knowledge_points', [])
            
            if not kps:
                self.log("没有需要向量化的知识点实体", "warning")
                state['errors'].append("没有需要向量化的实体")
                return state
            
            all_entities = kps
            
            self.log(f"正在向量化 {len(all_entities)} 个知识点实体（已忽略资源）")
            
            vector_db = VectorDBManager(self.config, force_recreate=True)
            vector_db.add_entities(all_entities)
            
            state['vector_db_updated'] = True
            state['current_step'] = 'vectorize'
            
            self.log(f"成功向量化 {len(all_entities)} 个实体")
            
        except Exception as e:
            self.log(f"向量化错误: {e}", "error")
            state['errors'].append(str(e))
        
        return state


def create_vectorization_agent(config: dict) -> VectorizationAgent:
    """工厂函数：创建向量化智能体"""
    return VectorizationAgent(config)
