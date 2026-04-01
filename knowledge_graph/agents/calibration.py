#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Node 6: 数据校准智能体
去重、层级归属、相似度去重和LLM合并
"""

import os
import json
import difflib
import numpy as np
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict

from knowledge_graph.agents.base_agent import LLMAgent, AgentState


class CalibrationAgent(LLMAgent):
    """校准知识图谱数据的智能体"""

    STRING_SIM_THRESHOLD = 0.8
    SEMANTIC_SIM_THRESHOLD = 0.9

    def _strip_json_fences(self, text: str) -> str:
        """去掉常见 ```json ... ``` 围栏，降低 JSONDecodeError 概率。"""
        s = (text or "").strip()
        if not s:
            return s
        if s.startswith("```"):
            # remove first fence line
            nl = s.find("\n")
            if nl != -1:
                s = s[nl + 1 :]
            # remove trailing fence
            end = s.rfind("```")
            if end != -1:
                s = s[:end]
        return s.strip()

    def _safe_load_json_object(self, raw: str) -> dict:
        """尽最大努力将 LLM 输出解析为 JSON 对象。失败则抛出异常。"""
        s = self._strip_json_fences(raw)
        # 常见：模型在 JSON 前后加解释；尽量截取首个 { ... } 块
        if s and not s.lstrip().startswith("{"):
            lb = s.find("{")
            rb = s.rfind("}")
            if lb != -1 and rb != -1 and rb > lb:
                s = s[lb : rb + 1]
        try:
            obj = json.loads(s or "{}")
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass

        # 兜底：让模型修复为严格 JSON（不改变语义，只修复格式）
        repair_prompt = (
            "你是JSON修复助手。请将下面内容修复为严格合法JSON对象；"
            "不得新增字段、不得删减语义、不得输出解释，只输出JSON对象。"
        )
        repaired = self.call_llm(repair_prompt, raw or "")
        repaired = self._strip_json_fences(repaired)
        obj = json.loads(repaired or "{}")
        if not isinstance(obj, dict):
            raise ValueError("repaired_json_not_object")
        return obj

    def _chunk_list(self, items: list, chunk_size: int) -> list:
        """按固定大小切分列表"""
        if chunk_size <= 0:
            return [items]
        return [items[i:i + chunk_size] for i in range(0, len(items), chunk_size)]

    def _build_batch_judge_prompt(self, indexed_pairs: list) -> str:
        """构建批量相似对判定提示词"""
        payload = []
        for item in indexed_pairs:
            pair_index = int(item.get('pair_index', -1))
            pair = item.get('pair', {}) or {}
            kp_a = pair.get('kp_a', {}) or {}
            kp_b = pair.get('kp_b', {}) or {}
            payload.append({
                "pair_index": pair_index,
                "string_similarity": pair.get('string_similarity', 0),
                "a": {
                    "id": kp_a.get('id', ''),
                    "name": kp_a.get('name', ''),
                    "level": kp_a.get('level', ''),
                    "definition": kp_a.get('definition', '')
                },
                "b": {
                    "id": kp_b.get('id', ''),
                    "name": kp_b.get('name', ''),
                    "level": kp_b.get('level', ''),
                    "definition": kp_b.get('definition', '')
                }
            })

        prompt = f"""你是知识图谱去重专家。请对下面每一对候选实体判断是否应该合并。

候选实体对(JSON):
{json.dumps(payload, ensure_ascii=False, indent=2)}

判定标准：
1) 语义确实同一概念才合并；
2) 不同层级或不同语义不要合并；
3) 置信度范围 0~1；
4) merged_name 要可读且稳定；
5) merged_level 只允许 L1/L2/L3/L4（默认继承更高层级概念）。

仅输出JSON对象，格式如下：
{{
  "decisions": [
    {{
      "pair_index": 0,
      "should_merge": true,
      "confidence": 0.92,
      "merged_name": "合并后名称",
      "merged_definition": "合并后定义",
      "merged_level": "L2",
      "reason": "简要原因"
    }}
  ]
}}
"""
        return prompt

    def _judge_pairs_batch_with_llm(self, indexed_pairs: list) -> dict:
        """单次调用LLM批量判定多个相似对"""
        prompt = self._build_batch_judge_prompt(indexed_pairs)
        try:
            response = self.call_llm(prompt, "")
            result = self._safe_load_json_object(response or "")
            decisions = result.get('decisions', [])
            if not isinstance(decisions, list):
                decisions = []

            out = {}
            valid_indices = {int(x.get('pair_index', -1)) for x in indexed_pairs}
            for d in decisions:
                if not isinstance(d, dict):
                    continue
                idx = d.get('pair_index', -1)
                try:
                    idx = int(idx)
                except Exception:
                    continue
                if idx not in valid_indices:
                    continue
                out[idx] = {
                    "should_merge": bool(d.get('should_merge', False)),
                    "confidence": float(d.get('confidence', 0) or 0),
                    "merged_name": d.get('merged_name', ''),
                    "merged_definition": d.get('merged_definition', ''),
                    "merged_level": d.get('merged_level', ''),
                    "reason": d.get('reason', '')
                }
            return out
        except Exception as e:
            snippet = (response or "").replace("\n", "\\n")[:400]
            self.log(f"批量LLM合并判定失败: {e}; response_head={snippet}", "warning")
            return {}

    def _judge_pairs_parallel(self, similar_pairs: list) -> dict:
        """并行批量判定相似对，返回 pair_index -> merge_result"""
        batch_size = int(self.config.get('calibration', {}).get('llm_pair_batch_size', 8))
        max_workers = int(self.config.get('calibration', {}).get('llm_judge_workers', 4))
        max_workers = max(1, max_workers)
        indexed_pairs = [{'pair_index': i, 'pair': p} for i, p in enumerate(similar_pairs)]
        batches = self._chunk_list(indexed_pairs, batch_size)
        if not batches:
            return {}

        merged_results = {}
        worker_count = min(max_workers, len(batches))
        self.log(f"批量并行判定: pairs={len(similar_pairs)}, batches={len(batches)}, workers={worker_count}")

        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = [executor.submit(self._judge_pairs_batch_with_llm, batch) for batch in batches]
            for future in as_completed(futures):
                try:
                    merged_results.update(future.result() or {})
                except Exception as e:
                    self.log(f"并行批次执行失败: {e}", "warning")

        return merged_results

    def __init__(self, config: dict):
        super().__init__(
            name="Calibration",
            config=config,
            prompt_path="prompts/Merge_Entities_Prompt.txt"
        )

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

    def calculate_string_similarity(self, str1: str, str2: str) -> float:
        """计算两个字符串的相似度（使用difflib）"""
        return difflib.SequenceMatcher(None, str1.lower(), str2.lower()).ratio()

    def calculate_semantic_similarity(self, vec1: list, vec2: list) -> float:
        """计算两个向量的余弦相似度"""
        if not vec1 or not vec2:
            return 0.0
        v1 = np.array(vec1)
        v2 = np.array(vec2)
        dot = np.dot(v1, v2)
        norm1 = np.linalg.norm(v1)
        norm2 = np.linalg.norm(v2)
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return float(dot / (norm1 * norm2))

    def find_similar_entities(self, kps: list, vector_db=None) -> list:
        """找出相似的实体对（仅使用字符串相似度）"""
        self.log("正在查找相似实体（字符串相似度）...")
        
        similar_pairs = []
        
        for i in range(len(kps)):
            for j in range(i + 1, len(kps)):
                kp_a = kps[i]
                kp_b = kps[j]
                
                name_a = kp_a.get('name', '').lower().strip()
                name_b = kp_b.get('name', '').lower().strip()
                
                if not name_a or not name_b:
                    continue
                
                string_sim = self.calculate_string_similarity(name_a, name_b)
                
                if string_sim >= self.STRING_SIM_THRESHOLD:
                    similar_pairs.append({
                        'idx_a': i,
                        'idx_b': j,
                        'kp_a': kp_a,
                        'kp_b': kp_b,
                        'string_similarity': string_sim,
                        'method': 'string'
                    })
        
        self.log(f"找到 {len(similar_pairs)} 对相似实体")
        return similar_pairs

    def merge_entities_with_llm(self, kp_a: dict, kp_b: dict) -> dict:
        """使用LLM判断并合并两个实体"""
        prompt_template = self.load_prompt()
        
        prompt = prompt_template.replace("{name_a}", kp_a.get('name', ''))
        prompt = prompt.replace("{definition_a}", kp_a.get('definition', ''))
        prompt = prompt.replace("{level_a}", kp_a.get('level', ''))
        prompt = prompt.replace("{id_a}", kp_a.get('id', ''))
        
        prompt = prompt.replace("{name_b}", kp_b.get('name', ''))
        prompt = prompt.replace("{definition_b}", kp_b.get('definition', ''))
        prompt = prompt.replace("{level_b}", kp_b.get('level', ''))
        prompt = prompt.replace("{id_b}", kp_b.get('id', ''))
        
        try:
            response = self.call_llm(prompt, "")
            result = json.loads(response)
            return result
        except Exception as e:
            self.log(f"LLM合并判断失败: {e}", "warning")
            return {"should_merge": False, "confidence": 0, "reason": str(e)}

    def merge_two_entities(self, kp_a: dict, kp_b: dict, merge_result: dict) -> dict:
        """合并两个实体，返回合并后的实体"""
        level_a = kp_a.get('level', 'L2')
        level_b = kp_b.get('level', 'L2')
        
        has_l1 = level_a == 'L1' or level_b == 'L1'
        
        if has_l1:
            if level_a == 'L1':
                merged_id = kp_a.get('id', '')
                merged_name = merge_result.get('merged_name', kp_a.get('name', ''))
                merged_definition = merge_result.get('merged_definition', kp_a.get('definition', ''))
            else:
                merged_id = kp_b.get('id', '')
                merged_name = merge_result.get('merged_name', kp_b.get('name', ''))
                merged_definition = merge_result.get('merged_definition', kp_b.get('definition', ''))
            merged_level = 'L1'
        else:
            merged_id = kp_a.get('id', '')
            merged_name = merge_result.get('merged_name', kp_a.get('name', ''))
            merged_definition = merge_result.get('merged_definition', kp_a.get('definition', ''))
            merged_level = merge_result.get('merged_level', 'L2')
        
        merged = {
            'id': merged_id,
            'name': merged_name,
            'definition': merged_definition,
            'level': merged_level,
            'merged_from': [kp_a.get('id', ''), kp_b.get('id', '')],
            'original_names': [kp_a.get('name', ''), kp_b.get('name', '')]
        }
        
        return merged

    def merge_relationships(self, rels_a: list, rels_b: list, old_id_a: str, old_id_b: str, new_id: str) -> list:
        """合并两组关系，处理ID变更"""
        merged_rels = []
        seen = set()
        
        all_rels = rels_a + rels_b
        
        for rel in all_rels:
            new_rel = dict(rel)
            
            if rel.get('start_id') == old_id_a:
                new_rel['start_id'] = new_id
            elif rel.get('start_id') == old_id_b:
                new_rel['start_id'] = new_id
            
            if rel.get('end_id') == old_id_a:
                new_rel['end_id'] = new_id
            elif rel.get('end_id') == old_id_b:
                new_rel['end_id'] = new_id
            
            rel_key = (new_rel.get('type', ''), new_rel.get('start_id', ''), new_rel.get('end_id', ''))
            if rel_key not in seen:
                seen.add(rel_key)
                merged_rels.append(new_rel)
        
        return merged_rels

    def deduplicate_with_similarity(self, entities: list, relationships: list = None, vector_db=None) -> tuple:
        """基于相似度的去重，返回去重后的实体和更新后的关系"""
        if not entities:
            return [], relationships or []
        
        self.log(f"正在为 {len(entities)} 个实体进行相似度去重...")
        
        similar_pairs = self.find_similar_entities(entities, vector_db)
        
        if not similar_pairs:
            self.log("未找到相似实体")
            return entities, relationships or []
        
        self.log(f"使用LLM判断 {len(similar_pairs)} 对相似实体是否合并...")
        
        confidence_threshold = float(self.config.get('calibration', {}).get('llm_merge_confidence_threshold', 0.7))
        decision_map = self._judge_pairs_parallel(similar_pairs)
        fallback_count = 0
        skipped_conflict = 0
        used_entity_ids = set()

        to_merge = []
        for idx, pair in enumerate(similar_pairs):
            merge_result = decision_map.get(idx)
            if merge_result is None:
                # 批量缺失时回退单对判断，保证功能正确性
                fallback_count += 1
                merge_result = self.merge_entities_with_llm(pair['kp_a'], pair['kp_b'])

            id_a = pair['kp_a'].get('id', '')
            id_b = pair['kp_b'].get('id', '')
            if id_a in used_entity_ids or id_b in used_entity_ids:
                skipped_conflict += 1
                continue

            if merge_result.get('should_merge', False) and merge_result.get('confidence', 0) >= confidence_threshold:
                to_merge.append({
                    'kp_a': pair['kp_a'],
                    'kp_b': pair['kp_b'],
                    'merge_result': merge_result
                })
                used_entity_ids.add(id_a)
                used_entity_ids.add(id_b)
                self.log(f"决定合并: {pair['kp_a'].get('name')} + {pair['kp_b'].get('name')}")
            else:
                self.log(f"不合并: {pair['kp_a'].get('name')} vs {pair['kp_b'].get('name')} - {merge_result.get('reason', '')}")

        if fallback_count > 0:
            self.log(f"批量判定缺失，已回退单对判定: {fallback_count} 对", "warning")
        if skipped_conflict > 0:
            self.log(f"跳过冲突合并对: {skipped_conflict} 对")
        
        if not to_merge:
            self.log("无需合并实体")
            return entities, relationships or []
        
        entity_map = {kp.get('id', ''): kp for kp in entities}
        
        for merge_info in to_merge:
            kp_a = merge_info['kp_a']
            kp_b = merge_info['kp_b']
            merge_result = merge_info['merge_result']
            
            merged = self.merge_two_entities(kp_a, kp_b, merge_result)
            
            entity_map[kp_a.get('id', '')] = merged
            if kp_b.get('id', '') in entity_map:
                del entity_map[kp_b.get('id', '')]
        
        if relationships:
            new_rels = []
            for rel in relationships:
                new_rel = dict(rel)
                start_id = rel.get('start_id', '')
                end_id = rel.get('end_id', '')
                
                if start_id in entity_map:
                    start_id = entity_map[start_id].get('id', start_id)
                if end_id in entity_map:
                    end_id = entity_map[end_id].get('id', end_id)
                
                new_rel['start_id'] = start_id
                new_rel['end_id'] = end_id
                new_rels.append(new_rel)
            
            relationships = new_rels
        
        unique_entities = list(entity_map.values())
        self.log(f"去重完成: {len(entities)} -> {len(unique_entities)} 个实体")
        
        return unique_entities, relationships

    def deduplicate(self, entities: list, entity_type: str = 'knowledge_point') -> list:
        """基于名称完全匹配去除重复实体"""
        if not entities:
            return []
        
        self.log(f"正在为 {len(entities)} 个实体精确去重...")
        
        unique = []
        seen = set()
        
        for entity in entities:
            if entity_type == 'resource':
                name = entity.get('url', '').lower().strip()
            else:
                name = entity.get('name', '').lower().strip()
            
            if name and name not in seen:
                seen.add(name)
                unique.append(entity)
        
        self.log(f"精确去重后: {len(unique)} 个实体")
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
                        kp['parent_name'] = parent_kp.get('name', '')
                    else:
                        kp['parent_name'] = ''
                else:
                    kp['parent_id'] = ''
                    kp['parent_name'] = ''
        
        return kps

    def merge_all_entities(self, state: AgentState) -> list:
        """合并所有阶段的实体"""
        all_kps = []
        
        l1_list = state.get('validated_l1_concepts', [])
        if l1_list:
            all_kps.extend(l1_list)
            self.log(f"从validated加载 {len(l1_list)} 个L1知识点")
        
        stage2_rels = self.load_parquet('data/output/stage2_relationships.parquet')
        stage3_ents = self.load_parquet('data/output/stage3_entities.parquet')
        if stage3_ents:
            all_kps.extend(stage3_ents)
            self.log(f"从stage3加载 {len(stage3_ents)} 个知识点")
        
        self.log(f"合并后共 {len(all_kps)} 个知识点")
        return all_kps

    def load_all_relationships(self, state: AgentState) -> list:
        """加载并合并所有关系"""
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

    def validate_and_calibrate_relationships(self, kps: list, relationships: list) -> list:
        """验证和校准关系"""
        self.log("开始验证和校准关系...")
        
        kp_map = {kp['id']: kp for kp in kps}
        level_map = {kp['id']: kp.get('level', '') for kp in kps}
        
        rels_to_keep = []
        rels_removed = {'duplicate': 0, 'invalid_level': 0, 'multiple_parents': 0, 'cycle': 0}
        
        parent_count_l2 = {}
        parent_count_l3 = {}
        
        seen_rels = set()
        
        for rel in relationships:
            rel_type = rel.get('type', '')
            start_id = rel.get('start_id', '')
            end_id = rel.get('end_id', '')
            
            if not start_id or not end_id:
                rels_removed['invalid_level'] += 1
                continue
            
            start_level = level_map.get(start_id, '')
            end_level = level_map.get(end_id, '')
            
            if rel_type == 'has_resource':
                if start_id in kp_map:
                    rels_to_keep.append(rel)
                else:
                    rels_removed['invalid_level'] += 1
                continue
            
            if not start_level or not end_level:
                rels_removed['invalid_level'] += 1
                continue
            
            rel_key = (rel_type, start_id, end_id)
            if rel_key in seen_rels:
                rels_removed['duplicate'] += 1
                continue
            seen_rels.add(rel_key)
            
            if rel_type == 'contains':
                if not (start_level == 'L1' and end_level == 'L2') \
                   and not (start_level == 'L2' and end_level == 'L3') \
                   and not (start_level == 'L3' and end_level == 'L4'):
                    rels_removed['invalid_level'] += 1
                    continue
                
                if end_level == 'L2':
                    if end_id not in parent_count_l2:
                        parent_count_l2[end_id] = []
                    parent_count_l2[end_id].append(start_id)
                elif end_level == 'L3':
                    if end_id not in parent_count_l3:
                        parent_count_l3[end_id] = []
                    parent_count_l3[end_id].append(start_id)
            
            elif rel_type == 'prerequisite':
                if start_level != end_level:
                    rels_removed['invalid_level'] += 1
                    continue
            
            reverse_key = (rel_type, end_id, start_id)
            if reverse_key in seen_rels:
                rels_removed['cycle'] += 1
                continue
            
            rels_to_keep.append(rel)
        
        for l2_id, parents in parent_count_l2.items():
            if len(parents) > 1:
                rels_removed['multiple_parents'] += len(parents) - 1
                keep_parent = parents[0]
                rels_to_keep = [r for r in rels_to_keep 
                               if not (r.get('end_id') == l2_id and r.get('type') == 'contains' 
                                       and r.get('start_id') != keep_parent)]
        
        for l3_id, parents in parent_count_l3.items():
            if len(parents) > 1:
                rels_removed['multiple_parents'] += len(parents) - 1
                keep_parent = parents[0]
                rels_to_keep = [r for r in rels_to_keep 
                               if not (r.get('end_id') == l3_id and r.get('type') == 'contains' 
                                       and r.get('start_id') != keep_parent)]
        
        self.log(f"关系去重: {rels_removed['duplicate']} 条")
        self.log(f"层级验证移除: {rels_removed['invalid_level']} 条")
        self.log(f"多父节点移除: {rels_removed['multiple_parents']} 条")
        self.log(f"循环检测移除: {rels_removed['cycle']} 条")
        self.log(f"校准后关系数: {len(rels_to_keep)}")
        
        return rels_to_keep
    
    def execute(self, state: AgentState) -> AgentState:
        """执行校准"""
        self.log("开始数据校准")
        
        l1_list = state.get('validated_l1_concepts', [])
        
        all_kps = self.merge_all_entities(state)
        
        kps = self.deduplicate(all_kps)
        
        vector_db = None
        try:
            from knowledge_graph.utils.vector_db import VectorDBManager
            vector_db = VectorDBManager(self.config, force_recreate=False)
            self.log("已加载向量数据库，可进行语义相似度去重")
        except Exception as e:
            self.log(f"无法加载向量数据库，将仅使用字符串相似度: {e}", "warning")
        
        relationships = self.load_all_relationships(state)
        
        kps, relationships = self.deduplicate_with_similarity(kps, relationships, vector_db)
        
        kps = self.assign_hierarchy(kps, l1_list, relationships)
        
        relationships = self.validate_and_calibrate_relationships(kps, relationships)
        
        # 资源仍保留在 stage3_resources.parquet 供后续独立入图；校准阶段不入图、不写 calibrated_resources
        state['calibrated_kps'] = kps
        state['calibrated_resources'] = []
        state['calibrated_relationships'] = relationships
        state['current_step'] = 'calibrate'
        
        kps = self.merge_definition_description(kps)
        
        self.save_parquet(kps, 'data/output/calibrated_entities.parquet')
        self.save_parquet(relationships, 'data/output/calibrated_relationships.parquet')
        
        self.log(f"校准完成: {len(kps)} 个知识点, {len(relationships)} 条关系（资源已忽略，未写入 calibrated_resources）")
        
        return state


def create_calibration_agent(config: dict) -> CalibrationAgent:
    """工厂函数：创建校准智能体"""
    return CalibrationAgent(config)
