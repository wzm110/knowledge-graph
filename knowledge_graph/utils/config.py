#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置工具模块
"""

import yaml
import os
from utils.logger import get_logger

logger = get_logger(__name__)

# 加载配置文件
def load_config(config_file='setting.yaml'):
    """加载配置文件"""
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        logger.info(f"成功加载配置文件: {config_file}")
        logger.debug(f"配置内容: {config}")
        return config
    except Exception as e:
        logger.error(f"加载配置文件失败: {e}")
        raise

# 加载预定义的L1知识点
def load_l1_concepts(l1_file='output/l1_concepts.yaml'):
    """加载预定义的L1知识点"""
    try:
        with open(l1_file, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        l1_concepts = data.get('Concepts', [])
        logger.info(f"成功加载预定义L1知识点，共 {len(l1_concepts)} 个")
        logger.debug(f"L1知识点: {[c['name'] for c in l1_concepts]}")
        return l1_concepts
    except Exception as e:
        logger.error(f"加载L1知识点失败: {e}")
        raise
