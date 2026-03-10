#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
向量数据库管理模块
使用LanceDB存储实体的名称和描述向量，支持字符串相似度和语义相似度去重
"""

import os
import lancedb
import pandas as pd
import numpy as np
import pyarrow as pa
import openai
from knowledge_graph.utils.logger import get_logger

logger = get_logger(__name__)

class VectorDBManager:
    def __init__(self, config, db_path="data/output/lancedb", force_recreate=False):
        self.config = config
        self.db_path = db_path
        self.embedding_config = config['models']['default_embedding_model']
        self._ensure_db_directory()
        self.db = self._connect_db()
        self.table = self._get_or_create_table(force_recreate=force_recreate)
        self._openai_client = None
    
    def _get_openai_client(self):
        """获取或创建OpenAI客户端"""
        if self._openai_client is None:
            self._openai_client = openai.OpenAI(
                api_key=self.embedding_config['api_key'],
                base_url=self.embedding_config['api_base']
            )
        return self._openai_client
    
    def _ensure_db_directory(self):
        """确保数据库目录存在"""
        os.makedirs(self.db_path, exist_ok=True)
    
    def _connect_db(self):
        """连接到LanceDB数据库"""
        try:
            db = lancedb.connect(self.db_path)
            logger.info(f"成功连接到LanceDB数据库: {self.db_path}")
            return db
        except Exception as e:
            logger.error(f"连接LanceDB数据库失败: {e}")
            raise
    
    def _get_or_create_table(self, force_recreate=False):
        """获取或创建表
        
        Args:
            force_recreate: 是否强制重新创建表
        """
        table_name = "knowledge_entities"
        
        # 检查表是否存在
        table_exists = table_name in self.db.table_names()
        
        # 如果强制重新创建，先删除旧表
        if force_recreate and table_exists:
            self.db.drop_table(table_name)
            logger.info(f"已删除旧表: {table_name}")
            table_exists = False
        
        # 如果表不存在，获取embedding维度并创建
        if not table_exists:
            # 动态获取embedding维度
            embedding_dim = 1024  # 默认维度
            try:
                test_embedding = self._get_embedding("测试")
                if test_embedding:
                    embedding_dim = len(test_embedding)
                    logger.info(f"检测到embedding维度: {embedding_dim}")
            except Exception as e:
                logger.warning(f"无法检测embedding维度，使用默认值: {embedding_dim}")
            
            try:
                schema = pa.schema([
                    ('id', pa.string()),
                    ('name', pa.string()),
                    ('description', pa.string()),
                    ('level', pa.string()),
                    ('name_embedding', pa.list_(pa.float32(), embedding_dim)),
                    ('description_embedding', pa.list_(pa.float32(), embedding_dim))
                ])
                self.db.create_table(table_name, schema=schema)
                logger.info(f"创建新表: {table_name}")
            except Exception as e:
                logger.error(f"创建表失败: {e}")
                raise
        
        try:
            table = self.db.open_table(table_name)
            return table
        except Exception as e:
            logger.error(f"打开表失败: {e}")
            raise
    
    def _get_embedding(self, text):
        """获取文本的embedding向量"""
        if not text or not text.strip():
            return None
        
        try:
            client = self._get_openai_client()
            
            response = client.embeddings.create(
                model=self.embedding_config['model'],
                input=text.strip()
            )
            
            embedding = response.data[0].embedding
            embedding_dim = len(embedding)
            logger.debug(f"成功生成embedding，维度: {embedding_dim}")
            return embedding
        except Exception as e:
            logger.error(f"生成embedding失败: {e}")
            return None
    
    def _get_embeddings_batch(self, texts):
        """批量获取embedding向量"""
        if not texts:
            return []
        
        try:
            client = self._get_openai_client()
            
            batch_size = self.embedding_config.get('batch_size', 10)
            embeddings = []
            
            for i in range(0, len(texts), batch_size):
                batch = texts[i:i + batch_size]
                batch = [t.strip() if t and t.strip() else " " for t in batch]
                
                response = client.embeddings.create(
                    model=self.embedding_config['model'],
                    input=batch
                )
                
                for item in response.data:
                    embeddings.append(item.embedding)
                
                logger.debug(f"已处理 {min(i + batch_size, len(texts))}/{len(texts)} 个文本")
            
            logger.info(f"批量生成embedding完成，共 {len(embeddings)} 个")
            return embeddings
        except Exception as e:
            logger.error(f"批量生成embedding失败: {e}")
            return [None] * len(texts)
    
    def add_entities(self, entities):
        """添加实体到向量数据库"""
        if not entities:
            logger.warning("没有实体需要添加到向量数据库")
            return
        
        try:
            # 准备数据
            ids = []
            names = []
            descriptions = []
            levels = []
            name_embeddings = []
            description_embeddings = []
            
            # 收集需要生成embedding的文本
            names_to_embed = []
            descs_to_embed = []
            entity_indices = []
            
            for i, entity in enumerate(entities):
                ids.append(str(entity.get('id', '')))
                names.append(str(entity.get('name', '')))
                descriptions.append(str(entity.get('description', '')))
                levels.append(str(entity.get('level', '')))
                
                # 准备生成embedding
                name = entity.get('name', '')
                desc = entity.get('description', '')
                
                if name and name.strip():
                    names_to_embed.append(name)
                    entity_indices.append(i)
                else:
                    names_to_embed.append("")
                
                if desc and desc.strip():
                    descs_to_embed.append(desc)
                else:
                    descs_to_embed.append("")
            
            # 批量生成embedding
            logger.info(f"开始生成 {len(names_to_embed)} 个名称的embedding")
            name_embeddings = self._get_embeddings_batch(names_to_embed)
            
            logger.info(f"开始生成 {len(descs_to_embed)} 个描述的embedding")
            description_embeddings = self._get_embeddings_batch(descs_to_embed)
            
            # 获取实际的embedding维度
            actual_dim = 1024
            valid_embeddings = [e for e in name_embeddings if e is not None]
            if valid_embeddings:
                actual_dim = len(valid_embeddings[0])
            
            # 确保所有embedding长度一致
            def normalize_embedding(e, dim):
                if e is None:
                    return [0.0] * dim
                if len(e) != dim:
                    return e[:dim] + [0.0] * max(0, dim - len(e))
                return e
            
            name_embeddings = [normalize_embedding(e, actual_dim) for e in name_embeddings]
            description_embeddings = [normalize_embedding(e, actual_dim) for e in description_embeddings]
            
            # 构建DataFrame
            data = {
                'id': ids,
                'name': names,
                'description': descriptions,
                'level': levels,
                'name_embedding': name_embeddings,
                'description_embedding': description_embeddings
            }
            
            df = pd.DataFrame(data)
            
            # 删除已存在的同名实体
            existing_names = set(self.table.to_pandas()['name'].tolist()) if self.table.to_pandas().shape[0] > 0 else set()
            df = df[~df['name'].isin(existing_names)]
            
            if len(df) > 0:
                # 转换为列表格式
                df['name_embedding'] = df['name_embedding'].apply(lambda x: x if isinstance(x, list) else list(x))
                df['description_embedding'] = df['description_embedding'].apply(lambda x: x if isinstance(x, list) else list(x))
                
                self.table.add(df)
                logger.info(f"成功添加 {len(df)} 个实体到向量数据库")
            else:
                logger.info("没有新实体需要添加（均已存在）")
                
        except Exception as e:
            logger.error(f"添加实体到向量数据库失败: {e}")
            raise
    
    def update_entities(self, entities):
        """更新向量数据库中的实体"""
        if not entities:
            logger.warning("没有实体需要更新")
            return
        
        try:
            # 清空向量数据库，然后写入新实体
            self.clear()
            self.add_entities(entities)
            logger.info(f"已更新 {len(entities)} 个实体到向量数据库")
            
        except Exception as e:
            logger.error(f"更新向量数据库失败: {e}")
            raise
    
    def clear(self):
        """清空向量数据库"""
        try:
            table_name = "knowledge_entities"
            if table_name in self.db.table_names():
                self.db.drop_table(table_name)
                logger.info("已清空向量数据库")
            self.table = self._get_or_create_table()
        except Exception as e:
            logger.error(f"清空向量数据库失败: {e}")
            raise
    
    def find_similar_entities(self, query_text, top_k=5, threshold=0.8):
        """查找相似实体"""
        try:
            query_embedding = self._get_embedding(query_text)
            if query_embedding is None:
                logger.warning("无法生成查询文本的embedding")
                return []
            
            df = self.table.to_pandas()
            if df.shape[0] == 0:
                logger.info("向量数据库为空")
                return []
            
            # 计算余弦相似度
            query_vec = np.array(query_embedding)
            similarities = []
            
            for idx, row in df.iterrows():
                name_emb = np.array(row['name_embedding'])
                desc_emb = np.array(row['description_embedding'])
                
                # 计算名称相似度
                name_sim = np.dot(query_vec, name_emb) / (np.linalg.norm(query_vec) * np.linalg.norm(name_emb) + 1e-8)
                
                # 计算描述相似度
                desc_sim = np.dot(query_vec, desc_emb) / (np.linalg.norm(query_vec) * np.linalg.norm(desc_emb) + 1e-8)
                
                # 取最大值
                max_sim = max(name_sim, desc_sim)
                similarities.append((row['id'], row['name'], max_sim))
            
            # 排序并返回top_k
            similarities.sort(key=lambda x: x[2], reverse=True)
            results = [(sid, name, sim) for sid, name, sim in similarities[:top_k] if sim >= threshold]
            
            logger.info(f"找到 {len(results)} 个相似实体（阈值: {threshold}）")
            return results
            
        except Exception as e:
            logger.error(f"查找相似实体失败: {e}")
            return []
    
    def get_all_entities(self):
        """获取所有实体"""
        try:
            df = self.table.to_pandas()
            return df.to_dict('records')
        except Exception as e:
            logger.error(f"获取所有实体失败: {e}")
            return []
    
    def close(self):
        """关闭数据库连接"""
        try:
            # LanceDB不需要显式关闭连接
            logger.info("向量数据库连接已关闭")
        except Exception as e:
            logger.error(f"关闭向量数据库连接失败: {e}")


def string_similarity(str1, str2):
    """计算两个字符串的相似度（使用difflib）"""
    import difflib
    if not str1 or not str2:
        return 0.0
    return difflib.SequenceMatcher(None, str1.strip(), str2.strip()).ratio()


def find_duplicate_entities_by_similarity(entities, string_threshold=0.9, vector_threshold=0.85, vector_db_manager=None):
    """
    基于字符串相似度和语义相似度查找重复实体
    
    Args:
        entities: 实体列表
        string_threshold: 字符串相似度阈值
        vector_threshold: 向量相似度阈值
        vector_db_manager: VectorDBManager实例
    
    Returns:
        duplicate_groups: 重复实体组，每组包含需要合并的实体
    """
    logger.info(f"开始查找重复实体，共 {len(entities)} 个")
    
    # 首先按字符串相似度分组
    string_duplicate_groups = []
    processed = set()
    
    for i, entity1 in enumerate(entities):
        if i in processed:
            continue
        
        name1 = entity1.get('name', '').strip()
        if not name1:
            continue
        
        group = [entity1]
        
        for j, entity2 in enumerate(entities):
            if j <= i or j in processed:
                continue
            
            name2 = entity2.get('name', '').strip()
            if not name2:
                continue
            
            # 字符串相似度检查
            sim = string_similarity(name1, name2)
            if sim >= string_threshold:
                group.append(entity2)
                processed.add(j)
        
        if len(group) > 1:
            string_duplicate_groups.append(group)
            processed.add(i)
    
    logger.info(f"基于字符串相似度找到 {len(string_duplicate_groups)} 组重复实体")
    
    # 如果有向量数据库，使用向量相似度进一步细分
    if vector_db_manager:
        final_groups = []
        
        for group in string_duplicate_groups:
            if len(group) <= 1:
                final_groups.append(group)
                continue
            
            # 将组内实体添加到临时向量数据库进行相似度计算
            temp_entities = []
            for entity in group:
                temp_entities.append({
                    'id': entity.get('id', ''),
                    'name': entity.get('name', ''),
                    'description': entity.get('description', '')
                })
            
            # 查找组内实体的语义相似实体
            sub_groups = []
            sub_processed = set()
            
            for i, ent in enumerate(temp_entities):
                if i in sub_processed:
                    continue
                
                sub_group = [ent]
                
                # 使用向量相似度查找
                similar = vector_db_manager.find_similar_entities(
                    ent['name'], 
                    top_k=len(temp_entities), 
                    threshold=vector_threshold
                )
                
                for sim_id, sim_name, sim_score in similar:
                    for j, other_ent in enumerate(temp_entities):
                        if j <= i or j in sub_processed:
                            continue
                        if str(other_ent.get('id', '')) == str(sim_id) or other_ent['name'] == sim_name:
                            sub_group.append(other_ent)
                            sub_processed.add(j)
                
                if len(sub_group) > 1:
                    sub_groups.append(sub_group)
                    sub_processed.add(i)
            
            final_groups.extend(sub_groups)
        
        return final_groups
    else:
        return string_duplicate_groups


def merge_duplicate_entities(entities, duplicate_groups):
    """
    合并重复实体
    
    Args:
        entities: 所有实体列表
        duplicate_groups: 重复实体组
    
    Returns:
        merged_entities: 合并后的实体列表
    """
    logger.info(f"开始合并 {len(duplicate_groups)} 组重复实体")
    
    # 收集所有需要保留的实体ID
    ids_to_remove = set()
    
    for group in duplicate_groups:
        if len(group) <= 1:
            continue
        
        # 选择第一个实体作为主实体，合并其他实体的信息
        primary = group[0]
        
        # 合并描述（保留最长的）
        max_desc_len = len(primary.get('description', ''))
        for entity in group[1:]:
            desc = entity.get('description', '')
            if len(desc) > max_desc_len:
                primary['description'] = desc
                max_desc_len = len(desc)
        
        # 合并别名
        aliases = set(primary.get('aliases', []))
        for entity in group[1:]:
            entity_aliases = entity.get('aliases', [])
            if isinstance(entity_aliases, str):
                entity_aliases = entity_aliases.split(',')
            aliases.update(entity_aliases)
        primary['aliases'] = list(aliases)
        
        # 记录要移除的实体ID
        for entity in group[1:]:
            ids_to_remove.add(entity.get('id', ''))
    
    # 过滤出保留的实体
    merged_entities = [e for e in entities if e.get('id', '') not in ids_to_remove]
    
    logger.info(f"合并完成，移除了 {len(ids_to_remove)} 个重复实体，保留 {len(merged_entities)} 个实体")
    return merged_entities
