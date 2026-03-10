#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Node 6: 数据校准智能体
去重、层级归属和关系验证
"""

import os

from knowledge_graph.agents.base_agent import BaseAgent, AgentState


class CalibrationAgent(BaseAgent):
    """校准知识图谱数据的智能体"""

    def __init__(self, config: dict):
        super().__init__(name="Calibration", config=config)

    def merge_definition_description(self, kps: list) -> list:
        """将 definition 和 description 合并为一个字段"""
        for kp in kps:
            definition = kp.get('definition', '')
            description = kp.get('description', '')
            
            if definition and description:
                kp['definition'] = f"{definition} {description}"
            elif description and not definition:
                kp['definition'] = description
            
            if 'description' in kp:
                del kp['description']
        
        return kps

    def deduplicate(self, entities: list) -> list:
        """基于名称相似度去除重复实体"""
        if not entities:
            return []
        
        self.log(f"正在为 {len(entities)} 个实体去重")
        
        unique = []
        seen = set()
        
        for entity in entities:
            name = entity.get('name', '').lower().strip()
            if name and name not in seen:
                seen.add(name)
                unique.append(entity)
        
        self.log(f"去重后: {len(unique)} 个实体")
        return unique

    def assign_hierarchy(self, kps: list, l1_list: list, relationships: list = None) -> list:
        """为知识点分配层级（L1, L2, L3）"""
        self.log("正在分配层级")
        
        l1_names = {kp['name'].lower(): kp['id'] for kp in l1_list}
        l1_ids = {kp['id']: kp['name'] for kp in l1_list}
        kp_ids = {kp['id']: kp for kp in kps}
        
        parent_map = {}
        if relationships:
            for rel in relationships:
                if rel.get('type') == 'contains':
                    end_id = rel.get('end_id', '')
                    start_id = rel.get('start_id', '')
                    if end_id and start_id:
                        parent_map[end_id] = start_id
        
        for kp in kps:
            level = kp.get('level', '')
            kp_id = kp.get('id', '')
            
            if level == 'L1':
                kp['parent_id'] = ''
                kp['parent_name'] = ''
            elif level == 'L2':
                if kp_id in parent_map:
                    parent_id = parent_map[kp_id]
                    kp['parent_id'] = parent_id
                    if parent_id in kp_ids:
                        parent_kp = kp_ids[parent_id]
                        if parent_kp.get('level') == 'L1':
                            kp['parent_name'] = parent_kp.get('name', '')
                        elif parent_id in l1_ids:
                            kp['parent_name'] = l1_ids[parent_id]
                        else:
                            kp['parent_name'] = ''
                    elif parent_id.lower() in l1_names:
                        parent_name = None
                        for l1 in l1_list:
                            if l1['id'] == l1_names[parent_id.lower()]:
                                parent_name = l1.get('name', '')
                                break
                        kp['parent_name'] = parent_name or ''
                    else:
                        kp['parent_name'] = ''
                else:
                    kp['parent_id'] = ''
                    kp['parent_name'] = ''
            elif level == 'L3':
                if kp_id in parent_map:
                    parent_id = parent_map[kp_id]
                    kp['parent_id'] = parent_id
                    if parent_id in kp_ids:
                        parent_kp = kp_ids[parent_id]
                        if parent_kp.get('level') == 'L2':
                            kp['parent_name'] = parent_kp.get('name', '')
                        else:
                            kp['parent_name'] = ''
                    else:
                        kp['parent_name'] = ''
                else:
                    kp['parent_id'] = ''
                    kp['parent_name'] = ''
        
        return kps

    def merge_all_entities(self, state: AgentState) -> list:
        """合并L1、L2、L3实体为全量知识点"""
        all_kps = []
        
        l1_concepts = state.get('validated_l1_concepts', [])
        if l1_concepts:
            for kp in l1_concepts:
                kp['level'] = 'L1'
            all_kps.extend(l1_concepts)
            self.log(f"已加载 {len(l1_concepts)} 个L1知识点")
        
        stage1_entities = self.load_parquet('data/output/stage1_entities.parquet')
        if stage1_entities:
            existing_ids = {kp.get('id') for kp in all_kps}
            for kp in stage1_entities:
                if kp.get('id') not in existing_ids:
                    all_kps.append(kp)
            self.log(f"从stage1加载 {len(stage1_entities)} 个实体")
        
        stage3_entities = self.load_parquet('data/output/stage3_entities.parquet')
        if stage3_entities:
            existing_ids = {kp.get('id') for kp in all_kps}
            for kp in stage3_entities:
                if kp.get('id') not in existing_ids:
                    all_kps.append(kp)
            self.log(f"从stage3加载 {len(stage3_entities)} 个L2/L3实体")
        
        self.log(f"合并后共 {len(all_kps)} 个实体")
        return all_kps

    def load_all_relationships(self, state: AgentState) -> list:
        """加载所有关系"""
        all_rels = []
        
        l1_prereqs = state.get('l1_prerequisites', [])
        if l1_prereqs:
            all_rels.extend(l1_prereqs)
        
        stage2_rels = self.load_parquet('data/output/stage2_relationships.parquet')
        if stage2_rels:
            all_rels.extend(stage2_rels)
            self.log(f"从stage2加载 {len(stage2_rels)} 条关系")
        
        stage3_rels = self.load_parquet('data/output/stage3_relationships.parquet')
        if stage3_rels:
            all_rels.extend(stage3_rels)
            self.log(f"从stage3加载 {len(stage3_rels)} 条关系")
        
        self.log(f"合并后共 {len(all_rels)} 条关系")
        return all_rels

    def execute(self, state: AgentState) -> AgentState:
        """执行校准"""
        self.log("开始数据校准")
        
        l1_list = state.get('validated_l1_concepts', [])
        
        all_kps = self.merge_all_entities(state)
        
        kps = self.deduplicate(all_kps)
        
        resources = self.load_parquet('data/output/stage3_resources.parquet')
        if not resources:
            resources = []
        resources = self.deduplicate(resources)
        
        relationships = self.load_all_relationships(state)
        
        state['calibrated_kps'] = kps
        state['calibrated_resources'] = resources
        state['calibrated_relationships'] = relationships
        state['current_step'] = 'calibrate'
        
        kps = self.assign_hierarchy(kps, l1_list, relationships)
        
        kps = self.merge_definition_description(kps)
        
        self.save_parquet(kps, 'data/output/calibrated_entities.parquet')
        self.save_parquet(resources, 'data/output/calibrated_resources.parquet')
        self.save_parquet(relationships, 'data/output/calibrated_relationships.parquet')
        
        self.log(f"校准完成: {len(kps)} 个知识点, {len(resources)} 个资源, {len(relationships)} 条关系")
        
        return state


def create_calibration_agent(config: dict) -> CalibrationAgent:
    """工厂函数：创建校准智能体"""
    return CalibrationAgent(config)
