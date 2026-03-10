#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Node 4: 实体与关系提取智能体
从教材内容提取L2/L3知识点、关系和资源
"""

import json
import os
import glob as glob_module

from knowledge_graph.agents.base_agent import LLMAgent, AgentState


class EntityExtractorAgent(LLMAgent):
    """从教材数据提取实体和关系的智能体"""

    def __init__(self, config: dict):
        super().__init__(
            name="EntityExtractor",
            config=config,
            prompt_path="prompts/Entity_Extraction_Prompt.txt"
        )

    def load_textbook_data(self, input_dir: str = "data/input") -> list:
        """从CSV文件加载教材数据"""
        self.log(f"正在加载教材数据: {input_dir}")
        
        csv_files = glob_module.glob(f"{input_dir}/*.csv")
        csv_files = [f for f in csv_files if not f.endswith('目录.csv')]
        self.log(f"找到 {len(csv_files)} 个CSV文件")

        import pandas as pd
        data = []
        
        for csv_file in csv_files:
            self.log(f"  读取: {os.path.basename(csv_file)}")
            df = pd.read_csv(csv_file, encoding='utf-8-sig')
            for _, row in df.iterrows():
                data.append({
                    'chapter_title': row.get('title', ''),
                    'text': row.get('text', ''),
                    'lecture_link': row.get('lecture_link', ''),
                    'ppt_link': row.get('ppt_link', ''),
                    'code_link': row.get('code_link', ''),
                    'video_link': row.get('video_link', '')
                })
        
        self.log(f"已加载 {len(data)} 个章节")
        return data

    def extract_from_chunk(self, text: str, l1_list: list, resource_links: dict) -> dict:
        """从单个文本块提取实体"""
        prompt_template = self.load_prompt()
        
        l1_json = json.dumps([kp['name'] for kp in l1_list], ensure_ascii=False)
        prompt = prompt_template.replace("{l1_list}", l1_json)
        prompt = prompt.replace("{resource_links}", json.dumps(resource_links, ensure_ascii=False, indent=2))
        prompt = prompt.replace("{text}", text[:5000] if len(text) > 5000 else text)
        
        try:
            response = self.call_llm(prompt, text)
            
            response = response.strip()
            if not response.startswith('{'):
                response = '{' + response
            if not response.endswith('}'):
                response = response + '}'
            
            result = json.loads(response)
            return result
            
        except json.JSONDecodeError as e:
            self.log(f"JSON解析错误: {e}", "warning")
            return {'knowledge_points': [], 'relationships': [], 'resources': []}
        except Exception as e:
            self.log(f"提取错误: {e}", "error")
            return {'knowledge_points': [], 'relationships': [], 'resources': []}

    def execute(self, state: AgentState) -> AgentState:
        """执行实体提取"""
        self.log("开始实体和关系提取")
        
        l1_list = state.get('validated_l1_concepts', [])
        if not l1_list:
            state['errors'].append("没有找到已验证的L1知识点")
            return state
        
        textbook_data = state.get('textbook_data', [])
        if not textbook_data:
            textbook_data = self.load_textbook_data()
            
            if state.get('_test_mode'):
                max_chapters = state.get('_max_chapters', 2)
                textbook_data = textbook_data[:max_chapters]
                self.log(f"测试模式：仅处理 {len(textbook_data)} 个章节")
            
            state['textbook_data'] = textbook_data
        
        all_kps = []
        all_rels = []
        all_resources = []
        
        try:
            from tqdm import tqdm
            iterator = tqdm(textbook_data, desc="提取实体", unit="个")
        except ImportError:
            iterator = textbook_data
        
        for i, chunk in enumerate(iterator):
            self.log(f"处理章节 {i+1}/{len(textbook_data)}")
            
            result = self.extract_from_chunk(
                chunk.get('text', ''),
                l1_list,
                {
                    'lecture': chunk.get('lecture_link', ''),
                    'ppt': chunk.get('ppt_link', ''),
                    'code': chunk.get('code_link', ''),
                    'video': chunk.get('video_link', '')
                }
            )
            
            for kp in result.get('l2_points', []):
                kp['level'] = 'L2'
                all_kps.append(kp)
            
            for kp in result.get('l3_points', []):
                kp['level'] = 'L3'
                all_kps.append(kp)
            
            for rel in result.get('relationships', []):
                all_rels.append(rel)
            
            for res in result.get('resources', []):
                if res.get('url'):
                    res['source'] = chunk.get('chapter_title', '')
                    all_resources.append(res)
        
        l1_name_to_id = {kp['name']: kp['id'] for kp in l1_list}
        
        for rel in all_rels:
            start_id = rel.get('start_id', '')
            if start_id in l1_name_to_id:
                rel['start_id'] = l1_name_to_id[start_id]
        
        state['knowledge_points'] = all_kps
        state['relationships'] = all_rels
        state['resources'] = all_resources
        state['current_step'] = 'extract_entities'
        
        self.save_parquet(all_kps, 'data/output/stage3_entities.parquet')
        self.save_parquet(all_rels, 'data/output/stage3_relationships.parquet')
        self.save_parquet(all_resources, 'data/output/stage3_resources.parquet')
        
        self.log(f"已提取: {len(all_kps)} 个知识点, {len(all_rels)} 条关系, {len(all_resources)} 个资源")
        
        return state


def create_entity_extractor(config: dict) -> EntityExtractorAgent:
    """工厂函数：创建实体提取智能体"""
    return EntityExtractorAgent(config)
