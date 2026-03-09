#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
实体和关系提取步骤
"""

import os
import json
import pandas as pd
from utils.logger import get_logger
from utils.llm import call_llm, load_prompt

logger = get_logger(__name__)

# LLM 缓存文件
LLM_CACHE_FILE = 'data/output/llm_cache.json'

# 加载 LLM 缓存
def load_llm_cache():
    """加载 LLM 缓存"""
    if os.path.exists(LLM_CACHE_FILE):
        try:
            with open(LLM_CACHE_FILE, 'r', encoding='utf-8') as f:
                cache = json.load(f)
            logger.info(f"加载 LLM 缓存，共 {len(cache)} 条记录")
            return cache
        except Exception as e:
            logger.error(f"加载 LLM 缓存失败: {e}")
            return {}
    return {}

# 保存 LLM 缓存
def save_llm_cache(cache):
    """保存 LLM 缓存"""
    try:
        with open(LLM_CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
        logger.info(f"保存 LLM 缓存，共 {len(cache)} 条记录")
    except Exception as e:
        logger.error(f"保存 LLM 缓存失败: {e}")

# 生成缓存键
def generate_cache_key(text_chunk, l1_list, resource_links):
    """生成缓存键"""
    # 使用文本块内容、L1列表和资源链接生成缓存键
    key = f"{text_chunk[:500]}|||{str(l1_list)}|||{str(resource_links)}"
    return key

# 知识点去重函数
def deduplicate_knowledge_points(kps):
    """去重知识点"""
    if not kps:
        return []
    
    # 基于名称的相似度计算
    seen_names = set()
    unique_kps = []
    
    for kp in kps:
        name = kp.get('name', '').strip()
        if name and name not in seen_names:
            seen_names.add(name)
            unique_kps.append(kp)
    
    return unique_kps

# 联合提取实体和关系
def extract_entities_relations(processed_data, l1_concepts, config):
    """联合提取实体和关系"""
    logger.info("\n=== 开始联合提取实体和关系 ===")
    
    knowledge_points = []
    resources = []
    relationships = []
    
    try:
        # 加载 LLM 缓存
        llm_cache = load_llm_cache()
        
        # 创建L1知识点实体
        for i, l1_concept in enumerate(l1_concepts):
            l1_kp = {
                'id': f"l1-{i+1}",
                'name': l1_concept['name'],
                'level': l1_concept['level'],
                'description': l1_concept.get('definition', ''),
                'difficulty': 0.7,
                'aliases': l1_concept.get('aliases', [])
            }
            knowledge_points.append(l1_kp)
            logger.debug(f"添加L1知识点: {l1_kp['name']}")
        
        # 构建L1知识点列表
        l1_list = [concept['name'] for concept in l1_concepts]
        logger.info(f"L1知识点列表: {l1_list}")
        
        # 加载提示词
        prompt_file = 'prompts/entity_relation_extraction.txt'
        if os.path.exists(prompt_file):
            prompt_template = load_prompt(prompt_file)
        else:
            # 如果提示词文件不存在，使用默认提示词
            prompt_template = """请根据以下L1知识点列表和资源链接信息，完成以下任务：
        L1知识点列表：{l1_list}
        
        资源链接信息：
        {resource_links}
        
        任务1：判断当前文本块属于哪个L1知识点
        任务2：提取该L1下的L2和L3知识点
        任务3：从资源链接中提取Resource资源实体
        任务4：提取知识点之间的关系（contains关系、prerequisite关系）
        任务5：提取知识点与资源的关联关系（has_resource关系）
        
        提取要求：
        - L2（子概念）：具体概念名称
        - L3（技能）：实现方法、算法步骤的名称
        - Resource：从链接中提取资源实体，包含id、url、resource_type
        - 关系类型：contains、prerequisite、has_resource
        
        输出格式为JSON对象，包含：
        {
            "l1_assignment": "所属L1知识点名称",
            "l2_points": [每个L2知识点包含：id、name、level、description、difficulty、aliases],
            "l3_points": [每个L3知识点包含：id、name、level、description、difficulty、aliases],
            "resources": [每个资源包含：id、url、resource_type],
            "relationships": [每个关系包含：type、start_id、end_id、end_type]
        }
        """
        
        # 联合提取知识点、资源和关系
        for item in processed_data:
            text_chunk = item['text_chunk']
            chunk_id = item['chunk_id']
            chapter_title = item['chapter_title']
            
            # 获取资源链接信息
            resource_links = {
                'lecture': item.get('lecture_link'),
                'ppt': item.get('ppt_link'),
                'code': item.get('code_link'),
                'video': item.get('video_link')
            }
            
            logger.info(f"处理文本块 {chunk_id} - 章节: {chapter_title}")
            logger.debug(f"资源链接: {resource_links}")
            
            # 生成缓存键
            cache_key = generate_cache_key(text_chunk, l1_list, resource_links)
            
            # 检查缓存
            if cache_key in llm_cache:
                logger.info(f"文本块 {chunk_id} 命中 LLM 缓存，直接使用缓存结果")
                result = llm_cache[cache_key]
            else:
                # 构建联合提取提示词
                prompt = prompt_template.replace('{l1_list}', str(l1_list))
                prompt = prompt.replace('{resource_links}', str(resource_links))
                
                # 调用LLM
                result = call_llm(prompt, text_chunk, config)
                
                # 保存到缓存
                if result:
                    llm_cache[cache_key] = result
                    # 每处理10个文本块保存一次缓存
                    if (chunk_id + 1) % 10 == 0:
                        save_llm_cache(llm_cache)
            
            # 解析结果
            if result:
                try:
                    extracted_data = json.loads(result)
                    l1_assignment = extracted_data.get('l1_assignment')
                    logger.info(f"文本块 {chunk_id} 分配到L1: {l1_assignment}")
                    
                    # 找到对应的L1知识点
                    l1_kp = next((kp for kp in knowledge_points if kp['name'] == l1_assignment and kp['level'] == 'L1'), None)
                    
                    if l1_kp:
                        # 添加L2知识点
                        for l2_point in extracted_data.get('l2_points', []):
                            # 确保L2知识点关联到正确的L1
                            l2_point['level'] = 'L2'
                            knowledge_points.append(l2_point)
                            logger.debug(f"添加L2知识点: {l2_point['name']}")
                        
                        # 添加L3知识点
                        for l3_point in extracted_data.get('l3_points', []):
                            # 确保L3知识点关联到正确的L1
                            l3_point['level'] = 'L3'
                            knowledge_points.append(l3_point)
                            logger.debug(f"添加L3知识点: {l3_point['name']}")
                        
                        # 添加资源
                        for resource in extracted_data.get('resources', []):
                            resources.append(resource)
                            logger.debug(f"添加资源: {resource['url']}")
                        
                        # 添加关系并处理L1知识点的ID映射
                        rels = extracted_data.get('relationships', [])
                        for rel in rels:
                            # 检查关系的start_id是否是L1知识点的名称
                            start_id = rel.get('start_id')
                            if start_id:
                                # 尝试将L1知识点名称映射到对应的ID
                                mapped_l1 = next((kp for kp in knowledge_points if kp['name'] == start_id and kp['level'] == 'L1'), None)
                                if mapped_l1:
                                    rel['start_id'] = mapped_l1['id']
                                    logger.debug(f"将L1知识点名称 '{start_id}' 映射到ID '{mapped_l1['id']}'")
                        relationships.extend(rels)
                        logger.debug(f"添加 {len(rels)} 条关系")
                    else:
                        logger.warning(f"未找到对应的L1知识点: {l1_assignment}")
                except json.JSONDecodeError as e:
                    logger.error(f"解析LLM响应失败: {e}")
            else:
                logger.warning(f"LLM调用失败，跳过文本块 {chunk_id}")
        
        # 保存最终的缓存
        save_llm_cache(llm_cache)
        
        # 生成实体表
        entities = []
        
        # 添加知识点实体
        for kp in knowledge_points:
            entity = {
                'id': kp['id'],
                'name': kp['name'],
                'type': 'KnowledgePoint',
                'level': kp.get('level', ''),
                'description': kp.get('description', ''),
                'difficulty': kp.get('difficulty', 0.0),
                'aliases': ','.join(kp.get('aliases', [])),
                'url': '',
                'resource_type': ''
            }
            entities.append(entity)
        
        # 添加资源实体
        for resource in resources:
            entity = {
                'id': resource['id'],
                'name': resource['url'],
                'type': 'Resource',
                'level': '',
                'description': '',
                'difficulty': 0.0,
                'aliases': '',
                'url': resource.get('url', ''),
                'resource_type': resource.get('resource_type', '')
            }
            entities.append(entity)
        
        # 保存实体表
        entities_df = pd.DataFrame(entities)
        entities_file = 'data/output/entities.csv'
        entities_df.to_csv(entities_file, index=False, encoding='utf-8')
        logger.info(f"实体提取完成，生成 {entities_file}，共 {len(entities)} 个实体")
        
        # 生成关系表
        relationships_df = pd.DataFrame(relationships)
        relationships_file = 'data/output/relationships.csv'
        relationships_df.to_csv(relationships_file, index=False, encoding='utf-8')
        logger.info(f"关系提取完成，生成 {relationships_file}，共 {len(relationships)} 条关系")
        
        return knowledge_points, resources, relationships
    except Exception as e:
        logger.error(f"实体和关系提取失败: {e}")
        raise
