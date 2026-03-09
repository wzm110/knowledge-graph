#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
图谱构建步骤
"""

import os
import time
import pandas as pd
from neo4j import GraphDatabase
from utils.logger import get_logger

logger = get_logger(__name__)

# 图谱构建
def build_graph(config):
    """图谱构建"""
    logger.info("\n=== 开始图谱构建 ===")
    
    try:
        # 读取校准后的数据
        entities_file = 'output/calibrated_entities.csv'
        relationships_file = 'output/calibrated_relationships.csv'
        
        logger.info(f"读取校准后的实体数据: {entities_file}")
        entities_df = pd.read_csv(entities_file, encoding='utf-8')
        
        logger.info(f"读取校准后的关系数据: {relationships_file}")
        relationships_df = pd.read_csv(relationships_file, encoding='utf-8')
        
        # 处理数据
        calibrated_kps = []
        calibrated_resources = []
        
        for _, row in entities_df.iterrows():
            if row['type'] == 'KnowledgePoint':
                kp = {
                    'id': row['id'],
                    'name': row['name'],
                    'level': row['level'],
                    'description': row['description'],
                    'difficulty': row['difficulty'],
                    'aliases': row['aliases'].split(',') if pd.notna(row['aliases']) else []
                }
                calibrated_kps.append(kp)
            elif row['type'] == 'Resource':
                resource = {
                    'id': row['id'],
                    'url': row['url'],
                    'resource_type': row['resource_type']
                }
                calibrated_resources.append(resource)
        
        calibrated_rels = []
        for _, row in relationships_df.iterrows():
            rel = {
                'type': row['type'],
                'start_id': row['start_id'],
                'end_id': row['end_id'],
                'end_type': row['end_type']
            }
            calibrated_rels.append(rel)
        
        logger.info(f"读取到 {len(calibrated_kps)} 个KnowledgePoint实体")
        logger.info(f"读取到 {len(calibrated_resources)} 个Resource实体")
        logger.info(f"读取到 {len(calibrated_rels)} 条关系")
        
        # 读取Neo4j配置
        neo4j_config = config.get('neo4j', {
            'uri': 'neo4j://127.0.0.1:7687',
            'user': 'neo4j',
            'password': '12345678',
            'database': 'knowledge-graph'
        })
        
        # 确保数据库名称符合Neo4j命名规范
        if '_' in neo4j_config['database']:
            neo4j_config['database'] = neo4j_config['database'].replace('_', '-')
            logger.info(f"修改数据库名称为: {neo4j_config['database']}")
        
        # 确保密码是字符串类型
        neo4j_config['password'] = str(neo4j_config['password'])
        
        logger.info(f"Neo4j配置: {neo4j_config}")
        
        # 连接到Neo4j
        driver = GraphDatabase.driver(
            neo4j_config['uri'],
            auth=(neo4j_config['user'], neo4j_config['password'])
        )
        
        try:
            # 创建数据库（如果不存在）
            with driver.session(database="system") as session:
                # 检查数据库是否存在
                result = session.run(
                    "SHOW DATABASES WHERE name = $name",
                    name=neo4j_config['database']
                )
                if not result.single():
                    # 创建数据库
                    session.run(
                        "CREATE DATABASE $name",
                        name=neo4j_config['database']
                    )
                    logger.info(f"已创建数据库 {neo4j_config['database']}")
                    # 启动数据库
                    session.run(
                        "START DATABASE $name",
                        name=neo4j_config['database']
                    )
                    logger.info(f"已启动数据库 {neo4j_config['database']}")
                    # 等待数据库启动
                    time.sleep(5)
                else:
                    logger.info(f"数据库 {neo4j_config['database']} 已存在")
            
            # 创建实体
            with driver.session(database=neo4j_config['database']) as session:
                # 清空数据库
                session.run("MATCH (n) DETACH DELETE n")
                logger.info("已清空数据库")
                
                # 创建KnowledgePoint实体
                logger.info(f"开始创建 {len(calibrated_kps)} 个KnowledgePoint实体")
                for i, kp in enumerate(calibrated_kps):
                    session.run(
                        """
                        CREATE (k:KnowledgePoint {
                            id: $id,
                            name: $name,
                            level: $level,
                            description: $description,
                            difficulty: $difficulty,
                            aliases: $aliases
                        })
                        """,
                        id=kp['id'],
                        name=kp['name'],
                        level=kp['level'],
                        description=kp['description'],
                        difficulty=kp['difficulty'],
                        aliases=kp['aliases']
                    )
                    if (i + 1) % 10 == 0:
                        logger.info(f"已创建 {i + 1} 个KnowledgePoint实体")
                logger.info(f"已创建 {len(calibrated_kps)} 个KnowledgePoint实体")
                
                # 创建Resource实体
                logger.info(f"开始创建 {len(calibrated_resources)} 个Resource实体")
                for i, resource in enumerate(calibrated_resources):
                    session.run(
                        """
                        CREATE (r:Resource {
                            id: $id,
                            url: $url,
                            resource_type: $resource_type
                        })
                        """,
                        id=resource['id'],
                        url=resource['url'],
                        resource_type=resource['resource_type']
                    )
                    if (i + 1) % 10 == 0:
                        logger.info(f"已创建 {i + 1} 个Resource实体")
                logger.info(f"已创建 {len(calibrated_resources)} 个Resource实体")
                
                # 创建关系
                logger.info(f"开始创建 {len(calibrated_rels)} 条关系")
                for i, rel in enumerate(calibrated_rels):
                    start_id = rel['start_id']
                    end_id = rel['end_id']
                    rel_type = rel['type']
                    end_type = rel['end_type']
                    
                    # 构建Cypher语句
                    if end_type in ['L2', 'L3']:
                        cypher = f"""
                        MATCH (a) WHERE a.id = $start_id
                        MATCH (b:KnowledgePoint) WHERE b.id = $end_id
                        CREATE (a)-[:`{rel_type}`]->(b)
                        """
                    else:
                        cypher = f"""
                        MATCH (a) WHERE a.id = $start_id
                        MATCH (b:Resource) WHERE b.id = $end_id
                        CREATE (a)-[:`{rel_type}`]->(b)
                        """
                    
                    session.run(cypher, start_id=start_id, end_id=end_id)
                    if (i + 1) % 100 == 0:
                        logger.info(f"已创建 {i + 1} 条关系")
                logger.info(f"已创建 {len(calibrated_rels)} 条关系")
        finally:
            driver.close()
            logger.info("已关闭Neo4j连接")
        
        logger.info("图谱构建完成！")
    except Exception as e:
        logger.error(f"图谱构建失败: {e}")
        raise
