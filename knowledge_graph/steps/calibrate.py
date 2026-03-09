#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据校准步骤
"""

import os
import pandas as pd
from src.utils.logger import get_logger
from src.utils.vector_db import VectorDBManager, string_similarity

logger = get_logger(__name__)

# 数据校准
def calibrate_data(knowledge_points, resources, relationships, config=None, update_vector_db=True):
    """数据校准
    
    Args:
        knowledge_points: 知识点列表
        resources: 资源列表
        relationships: 关系列表
        config: 配置信息，用于初始化向量数据库
        update_vector_db: 是否更新向量数据库
    """
    logger.info("\n=== 开始数据校准 ===")
    
    # 初始化向量数据库管理器
    vector_db_manager = None
    if config and update_vector_db:
        try:
            vector_db_manager = VectorDBManager(config, force_recreate=True)
            logger.info("向量数据库管理器初始化成功")
        except Exception as e:
            logger.warning(f"初始化向量数据库失败: {e}，将使用字符串相似度进行去重")
    
    try:
        # 如果有向量数据库管理器，先清空向量数据库，然后写入原始实体（用于语义相似度检测）
        if vector_db_manager and update_vector_db:
            try:
                logger.info("清空向量数据库")
                vector_db_manager.clear()
                logger.info("开始将原始实体写入向量数据库（用于语义相似度检测）")
                vector_db_manager.add_entities(knowledge_points)
                logger.info("原始实体已写入向量数据库")
            except Exception as e:
                logger.warning(f"写入原始实体到向量数据库失败: {e}，将只使用字符串相似度进行去重")
                vector_db_manager = None
        
        # 知识点校准
        def calibrate_knowledge_points(kps, rels):
            """校准知识点，处理重复的L2和L3知识点
            
            返回:
                calibrated_kps: 校准后的知识点列表
                kp_name_map: 知识点名称到知识点的映射
                l2_final_l1: L2知识点到L1知识点的映射
                l3_final_l2: L3知识点到L2知识点的映射
                entity_merge_map: 实体合并映射 {被合并的实体ID: 主实体ID}
            """
            logger.info("开始校准知识点")
            
            # 记录实体合并映射
            entity_merge_map = {}
            
            # 1. 收集所有L1知识点的名称
            l1_names = set()
            for kp in kps:
                name = kp.get('name', '').strip()
                if name and kp.get('level') == 'L1':
                    l1_names.add(name)
            logger.info(f"L1知识点名称集合: {l1_names}")
            
            # 2. 统计每个知识点的级别分布
            kp_levels = {}
            for kp in kps:
                name = kp.get('name', '').strip()
                if not name:
                    continue
                level = kp.get('level', 'L2')
                # 如果L2知识点与L1重名，强制归属为L1
                if level == 'L2' and name in l1_names:
                    level = 'L1'
                    logger.info(f"知识点 '{name}' 与L1重名，强制归属为L1")
                if name not in kp_levels:
                    kp_levels[name] = {}
                kp_levels[name][level] = kp_levels[name].get(level, 0) + 1
            
            # 3. 确定每个知识点的最终级别（选择出现次数最多的级别）
            kp_final_level = {}
            for name, levels in kp_levels.items():
                # 如果与L1重名，强制设置为L1
                if name in l1_names:
                    final_level = 'L1'
                    logger.info(f"知识点 '{name}' 与L1重名，强制设置为L1")
                else:
                    # 选择出现次数最多的级别
                    final_level = max(levels, key=levels.get)
                kp_final_level[name] = final_level
                if len(levels) > 1:
                    logger.info(f"知识点 '{name}' 被识别为多个级别，选择出现次数最多的: {final_level}")
            
            # 3. 基于字符串相似度和语义相似度去重
            l1_kps = []
            l2_kps = []
            l3_kps = []
            
            # 先按名称精确去重
            seen_names = set()
            name_to_entity = {}
            
            for kp in kps:
                name = kp.get('name', '').strip()
                if not name:
                    continue
                
                if name not in seen_names:
                    seen_names.add(name)
                    name_to_entity[name] = kp
            
            # 对精确去重后的实体进行相似度检测
            unique_entities = list(name_to_entity.values())
            final_entities = []
            
            if len(unique_entities) > 1:
                # 字符串相似度检测（使用较低的阈值）
                string_threshold = 0.9
                similar_pairs = []
                
                for i in range(len(unique_entities)):
                    for j in range(i + 1, len(unique_entities)):
                        name1 = unique_entities[i].get('name', '').strip()
                        name2 = unique_entities[j].get('name', '').strip()
                        
                        sim = string_similarity(name1, name2)
                        if sim >= string_threshold:
                            similar_pairs.append((i, j, sim, 'string'))
                            logger.info(f"字符串相似: '{name1}' vs '{name2}' = {sim:.3f}")
                
                # 如果有向量数据库，进行语义相似度检测
                if vector_db_manager:
                    # 临时添加实体到向量数据库
                    temp_entities_for_search = []
                    for ent in unique_entities:
                        temp_entities_for_search.append({
                            'id': ent.get('id', ''),
                            'name': ent.get('name', ''),
                            'description': ent.get('description', '')
                        })
                    
                    vector_threshold = 0.95
                    for i in range(len(unique_entities)):
                        name1 = unique_entities[i].get('name', '').strip()
                        if not name1:
                            continue
                        
                        similar = vector_db_manager.find_similar_entities(
                            name1, 
                            top_k=min(10, len(unique_entities)), 
                            threshold=vector_threshold
                        )
                        
                        for sim_id, sim_name, sim_score in similar:
                            for j, other_ent in enumerate(unique_entities):
                                if j <= i:
                                    continue
                                if str(other_ent.get('id', '')) == str(sim_id) or other_ent.get('name', '').strip() == sim_name:
                                    # 检查是否已经被字符串相似度标记
                                    already_marked = any(
                                        (i == p[0] and j == p[1]) or (i == p[1] and j == p[0]) 
                                        for p in similar_pairs if p[3] == 'string'
                                    )
                                    if not already_marked:
                                        similar_pairs.append((i, j, sim_score, 'vector'))
                                        logger.info(f"语义相似: '{name1}' vs '{sim_name}' = {sim_score:.3f}")
                
                # 合并相似实体（使用并查集）
                parent = list(range(len(unique_entities)))
                
                def find(x):
                    if parent[x] != x:
                        parent[x] = find(parent[x])
                    return parent[x]
                
                def union(x, y):
                    px, py = find(x), find(y)
                    if px != py:
                        parent[px] = py
                
                for i, j, sim, sim_type in similar_pairs:
                    union(i, j)
                
                # 合并在同一组的实体
                groups = {}
                for i in range(len(unique_entities)):
                    root = find(i)
                    if root not in groups:
                        groups[root] = []
                    groups[root].append(i)
                
                # 对每个组进行合并
                for root, indices in groups.items():
                    if len(indices) == 1:
                        final_entities.append(unique_entities[indices[0]])
                    else:
                        # 选择描述最详细的作为主实体
                        best_ent = unique_entities[indices[0]]
                        max_desc_len = len(best_ent.get('description', ''))
                        
                        for idx in indices[1:]:
                            ent = unique_entities[idx]
                            desc = ent.get('description', '')
                            if len(desc) > max_desc_len:
                                best_ent = ent
                                max_desc_len = len(desc)
                        
                        # 记录合并映射
                        for idx in indices:
                            ent = unique_entities[idx]
                            if ent.get('id') != best_ent.get('id'):
                                entity_merge_map[ent.get('id')] = best_ent.get('id')
                                logger.info(f"记录实体合并映射: {ent.get('id')} -> {best_ent.get('id')}")
                        
                        # 合并别名
                        aliases = set(best_ent.get('aliases', []))
                        for idx in indices:
                            ent = unique_entities[idx]
                            ent_aliases = ent.get('aliases', [])
                            if isinstance(ent_aliases, str):
                                ent_aliases = ent_aliases.split(',')
                            aliases.update(ent_aliases)
                        best_ent['aliases'] = list(aliases)
                        
                        logger.info(f"合并了 {len(indices)} 个相似实体: {best_ent.get('name')}")
                        final_entities.append(best_ent)
            else:
                final_entities = unique_entities
            
            # 按级别分组
            for kp in final_entities:
                name = kp.get('name', '').strip()
                if not name:
                    continue
                
                # 使用最终确定的级别
                final_level = kp_final_level.get(name, kp.get('level', 'L2'))
                kp['level'] = final_level
                # 更新名称为strip后的值
                kp['name'] = name
                
                if final_level == 'L1':
                    l1_kps.append(kp)
                elif final_level == 'L2':
                    l2_kps.append(kp)
                elif final_level == 'L3':
                    l3_kps.append(kp)
            
            # 4. 再按ID去重，确保ID唯一
            all_kps = l1_kps + l2_kps + l3_kps
            seen_ids = set()
            unique_kps = []
            
            for kp in all_kps:
                kp_id = kp.get('id', '')
                if kp_id and kp_id in seen_ids:
                    logger.info(f"发现重复ID: {kp_id}，已去重")
                    continue
                if kp_id:
                    seen_ids.add(kp_id)
                unique_kps.append(kp)
            
            # 重新按级别分组
            l1_kps = [kp for kp in unique_kps if kp.get('level') == 'L1']
            l2_kps = [kp for kp in unique_kps if kp.get('level') == 'L2']
            l3_kps = [kp for kp in unique_kps if kp.get('level') == 'L3']
            
            logger.info(f"知识点分布: L1={len(l1_kps)}, L2={len(l2_kps)}, L3={len(l3_kps)}")
            
            # 4. 统计每个L2知识点的L1归属情况
            l2_l1_map = {}
            for rel in rels:
                if rel.get('type') == 'contains' and rel.get('end_id'):
                    end_kp = next((k for k in kps if k.get('id') == rel.get('end_id')), None)
                    if end_kp and end_kp.get('level') == 'L2':
                        l2_name = end_kp.get('name', '').strip()
                        if l2_name:
                            start_kp = next((k for k in kps if k.get('id') == rel.get('start_id')), None)
                            if start_kp and start_kp.get('level') == 'L1':
                                l1_name = start_kp.get('name', '').strip()
                                if l1_name:
                                    if l2_name not in l2_l1_map:
                                        l2_l1_map[l2_name] = {}
                                    l2_l1_map[l2_name][l1_name] = l2_l1_map[l2_name].get(l1_name, 0) + 1
            
            # 5. 确定每个L2知识点的最终L1归属（选择出现次数最多的L1）
            l2_final_l1 = {}
            for l2_name, l1_counts in l2_l1_map.items():
                final_l1 = max(l1_counts, key=l1_counts.get)
                l2_final_l1[l2_name] = final_l1
                if len(l1_counts) > 1:
                    logger.info(f"L2知识点 '{l2_name}' 被归属到多个L1，选择出现次数最多的: {final_l1}")
            
            # 6. 统计每个L3知识点的L2归属情况
            l3_l2_map = {}
            for rel in rels:
                if rel.get('type') == 'contains' and rel.get('end_id'):
                    end_kp = next((k for k in kps if k.get('id') == rel.get('end_id')), None)
                    if end_kp and end_kp.get('level') == 'L3':
                        l3_name = end_kp.get('name', '').strip()
                        if l3_name:
                            start_kp = next((k for k in kps if k.get('id') == rel.get('start_id')), None)
                            if start_kp and start_kp.get('level') == 'L2':
                                l2_name = start_kp.get('name', '').strip()
                                if l2_name:
                                    if l3_name not in l3_l2_map:
                                        l3_l2_map[l3_name] = {}
                                    l3_l2_map[l3_name][l2_name] = l3_l2_map[l3_name].get(l2_name, 0) + 1
            
            # 7. 确定每个L3知识点的最终L2归属（选择出现次数最多的L2）
            l3_final_l2 = {}
            for l3_name, l2_counts in l3_l2_map.items():
                final_l2 = max(l2_counts, key=l2_counts.get)
                l3_final_l2[l3_name] = final_l2
                if len(l2_counts) > 1:
                    logger.info(f"L3知识点 '{l3_name}' 被归属到多个L2，选择出现次数最多的: {final_l2}")
            
            # 8. 合并所有知识点并添加归属信息
            calibrated_kps = []
            kp_name_map = {}
            
            # 首先添加L1知识点
            for kp in l1_kps:
                if 'id' not in kp or not kp['id']:
                    kp['id'] = f"l1-{len(calibrated_kps)+1}"
                calibrated_kps.append(kp)
                kp_name_map[kp['name']] = kp
            
            # 然后添加L2知识点并设置归属
            for kp in l2_kps:
                if 'id' not in kp or not kp['id']:
                    kp['id'] = f"l2-{len(calibrated_kps)+1}"
                l2_name = kp['name']
                if l2_name in l2_final_l1:
                    kp['l1_assignment'] = l2_final_l1[l2_name]
                calibrated_kps.append(kp)
                kp_name_map[kp['name']] = kp
            
            # 最后添加L3知识点并设置归属
            for kp in l3_kps:
                if 'id' not in kp or not kp['id']:
                    kp['id'] = f"l3-{len(calibrated_kps)+1}"
                l3_name = kp['name']
                if l3_name in l3_final_l2:
                    kp['l2_assignment'] = l3_final_l2[l3_name]
                calibrated_kps.append(kp)
                kp_name_map[kp['name']] = kp
            
            # 9. 确保所有知识点都有必要字段
            for kp in calibrated_kps:
                if 'name' not in kp or not kp['name']:
                    kp['name'] = f"知识点{len(calibrated_kps)+1}"
                if 'level' not in kp:
                    kp['level'] = 'L2'  # 默认级别
                if 'description' not in kp:
                    kp['description'] = ''
                if 'difficulty' not in kp:
                    kp['difficulty'] = 0.5
                if 'aliases' not in kp:
                    kp['aliases'] = []
            
            logger.info(f"知识点校准完成，共 {len(calibrated_kps)} 个知识点")
            logger.info(f"实体合并映射: {entity_merge_map}")
            return calibrated_kps, kp_name_map, l2_final_l1, l3_final_l2, entity_merge_map
        
        # 资源校准
        def calibrate_resources(resources):
            """校准资源，处理重复资源"""
            logger.info("开始校准资源")
            
            # 基于URL和资源类型的组合去重
            seen = set()
            unique_resources = []
            
            for resource in resources:
                url = resource.get('url', '').strip()
                resource_type = resource.get('resource_type', 'other').strip()
                key = (url, resource_type)
                
                if url and key not in seen:
                    seen.add(key)
                    # 确保必要字段存在
                    if 'id' not in resource or not resource['id']:
                        resource['id'] = f"resource-{len(unique_resources)+1}"
                    if 'resource_type' not in resource:
                        resource['resource_type'] = 'other'
                    unique_resources.append(resource)
                    logger.debug(f"添加资源: {url}")
            
            logger.info(f"资源校准完成，共 {len(unique_resources)} 个资源")
            return unique_resources
        
        # 关系校准
        def calibrate_relationships(rels, calibrated_kps, calibrated_resources, kp_name_map, l2_final_l1, l3_final_l2, entity_merge_map):
            """校准关系，处理重复关系"""
            logger.info("开始校准关系")
            
            # 构建实体ID集合
            entity_ids = set()
            kp_id_map = {}
            resource_id_map = {}
            kp_name_to_id = {}
            kp_id_to_name = {}
            
            for kp in calibrated_kps:
                entity_ids.add(kp['id'])
                kp_id_map[kp['id']] = kp
                kp_name_to_id[kp['name']] = kp['id']
                kp_id_to_name[kp['id']] = kp['name']
            
            for resource in calibrated_resources:
                entity_ids.add(resource['id'])
                resource_id_map[resource['id']] = resource
            
            logger.info(f"实体ID集合大小: {len(entity_ids)}")
            logger.info(f"L1知识点映射: {[(name, id) for name, id in kp_name_to_id.items() if kp_id_map[id]['level'] == 'L1']}")
            
            # 处理被合并实体的关系映射
            logger.info(f"实体合并映射: {entity_merge_map}")
            
            # 过滤出有效的关系（两端实体都存在或可以通过名称映射）
            valid_rels = []
            for rel in rels:
                start_id = rel.get('start_id')
                end_id = rel.get('end_id')
                
                # 如果起始ID是被合并的实体，映射到主实体
                if start_id in entity_merge_map:
                    original_start_id = start_id
                    start_id = entity_merge_map[start_id]
                    logger.info(f"关系起始ID映射: {original_start_id} -> {start_id}")
                
                # 如果结束ID是被合并的实体，映射到主实体
                if end_id in entity_merge_map:
                    original_end_id = end_id
                    end_id = entity_merge_map[end_id]
                    logger.info(f"关系结束ID映射: {original_end_id} -> {end_id}")
                
                # 更新关系中的ID
                rel['start_id'] = start_id
                rel['end_id'] = end_id
                
                # 检查结束ID是否有效
                if end_id not in entity_ids:
                    continue
                
                # 检查开始ID是否有效，如果无效，尝试通过名称查找
                if start_id not in entity_ids:
                    # 尝试将开始ID作为名称查找对应的实体ID
                    start_id_stripped = start_id.strip()
                    if start_id_stripped in kp_name_to_id:
                        rel['start_id'] = kp_name_to_id[start_id_stripped]
                        valid_rels.append(rel)
                        logger.debug(f"通过名称映射L1知识点: {start_id_stripped} -> {kp_name_to_id[start_id_stripped]}")
                    else:
                        # 尝试查找L1知识点
                        for l1_kp in calibrated_kps:
                            if l1_kp['level'] == 'L1' and l1_kp['name'].strip() == start_id_stripped:
                                rel['start_id'] = l1_kp['id']
                                valid_rels.append(rel)
                                logger.debug(f"通过名称映射L1知识点: {start_id_stripped} -> {l1_kp['id']}")
                                break
                else:
                    valid_rels.append(rel)
            logger.info(f"有效关系数量: {len(valid_rels)}")
            
            # 去重关系（基于类型、开始ID和结束ID的组合）
            seen = set()
            calibrated_rels = []
            
            for rel in valid_rels:
                rel_type = rel.get('type', '').strip()
                start_id = rel.get('start_id', '').strip()
                end_id = rel.get('end_id', '').strip()
                key = (rel_type, start_id, end_id)
                
                if key not in seen:
                    seen.add(key)
                    # 确保必要字段存在
                    if 'type' not in rel:
                        rel['type'] = 'unknown'
                    if 'end_type' not in rel:
                        # 根据结束实体类型推断
                        if end_id in kp_id_map:
                            rel['end_type'] = kp_id_map[end_id]['level']
                        elif end_id in resource_id_map:
                            rel['end_type'] = 'Resource'
                        else:
                            rel['end_type'] = 'unknown'
                    calibrated_rels.append(rel)
            
            logger.info(f"关系去重后数量: {len(calibrated_rels)}")
            
            # 验证和校准contains关系
            final_rels = []
            seen_contains = set()
            
            for rel in calibrated_rels:
                rel_type = rel.get('type')
                start_id = rel.get('start_id')
                end_id = rel.get('end_id')
                
                if rel_type == 'contains':
                    # 验证contains关系的合法性
                    start_kp = kp_id_map.get(start_id)
                    end_kp = kp_id_map.get(end_id)
                    
                    if start_kp and end_kp:
                        start_level = start_kp.get('level')
                        end_level = end_kp.get('level')
                        end_name = end_kp.get('name')
                        
                        # 检查是否符合层级关系
                        if end_level == 'L2' and start_level == 'L1':
                            # 检查L2是否应该归属到这个L1
                            if end_name in l2_final_l1 and l2_final_l1[end_name] == start_kp.get('name'):
                                # 确保每个L2只有一个L1父节点
                                contains_key = (end_id, 'L1')
                                if contains_key not in seen_contains:
                                    seen_contains.add(contains_key)
                                    final_rels.append(rel)
                                    logger.debug(f"保留L2知识点 {end_kp['name']} 与L1 {start_kp['name']} 的contains关系")
                        elif end_level == 'L3' and start_level == 'L2':
                            # 检查L3是否应该归属到这个L2
                            if end_name in l3_final_l2 and l3_final_l2[end_name] == start_kp.get('name'):
                                # 确保每个L3只有一个L2父节点
                                contains_key = (end_id, 'L2')
                                if contains_key not in seen_contains:
                                    seen_contains.add(contains_key)
                                    final_rels.append(rel)
                                    logger.debug(f"保留L3知识点 {end_kp['name']} 与L2 {start_kp['name']} 的contains关系")
                else:
                    # 其他关系类型直接保留
                    final_rels.append(rel)
            
            logger.info(f"关系校准完成，共 {len(final_rels)} 条关系")
            return final_rels
        
        # 执行校准
        calibrated_kps, kp_name_map, l2_final_l1, l3_final_l2, entity_merge_map = calibrate_knowledge_points(knowledge_points, relationships)
        calibrated_resources = calibrate_resources(resources)
        calibrated_rels = calibrate_relationships(relationships, calibrated_kps, calibrated_resources, kp_name_map, l2_final_l1, l3_final_l2, entity_merge_map)
        
        # 更新向量数据库
        if vector_db_manager and update_vector_db:
            try:
                logger.info("开始更新向量数据库")
                vector_db_manager.update_entities(calibrated_kps)
                logger.info("向量数据库更新完成")
            except Exception as e:
                logger.warning(f"更新向量数据库失败: {e}")
        
        # 生成校准后的实体表
        calibrated_entities = []
        
        # 添加校准后的知识点实体
        for kp in calibrated_kps:
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
            calibrated_entities.append(entity)
        
        # 添加校准后的资源实体
        for resource in calibrated_resources:
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
            calibrated_entities.append(entity)
        
        # 保存校准后的实体表
        calibrated_entities_df = pd.DataFrame(calibrated_entities)
        calibrated_entities_file = 'output/calibrated_entities.csv'
        calibrated_entities_df.to_csv(calibrated_entities_file, index=False, encoding='utf-8')
        logger.info(f"实体校准完成，生成 {calibrated_entities_file}，共 {len(calibrated_entities)} 个实体")
        
        # 保存校准后的关系表
        calibrated_relationships_df = pd.DataFrame(calibrated_rels)
        calibrated_relationships_file = 'output/calibrated_relationships.csv'
        calibrated_relationships_df.to_csv(calibrated_relationships_file, index=False, encoding='utf-8')
        logger.info(f"关系校准完成，生成 {calibrated_relationships_file}，共 {len(calibrated_rels)} 条关系")
        
        return calibrated_kps, calibrated_resources, calibrated_rels
    except Exception as e:
        logger.error(f"数据校准失败: {e}")
        raise