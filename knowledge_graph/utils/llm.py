#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LLM调用工具模块
"""

import openai
import re
import os
from knowledge_graph.utils.logger import get_logger

logger = get_logger(__name__)

# 读取提示词文件
def load_prompt(prompt_file):
    """读取提示词文件"""
    try:
        with open(prompt_file, 'r', encoding='utf-8') as f:
            prompt = f.read()
        logger.info(f"成功加载提示词文件: {prompt_file}")
        return prompt
    except Exception as e:
        logger.error(f"加载提示词文件失败: {e}")
        raise

# 调用LLM函数
def call_llm(prompt, text, config):
    """调用LLM进行实体和关系提取"""
    chat_config = config['models']['default_chat_model']
    
    # 配置OpenAI客户端
    client = openai.OpenAI(
        api_key=chat_config['api_key'],
        base_url=chat_config['api_base']
    )
    
    try:
        # 构建完整的提示词，包含文本块内容
        full_prompt = f"{prompt}\n\n文本块内容：\n{text}\n\n请以JSON格式输出结果。"
        logger.info(f"调用LLM，提示词长度: {len(full_prompt)}")
        logger.info(f"文本块长度: {len(text)}")
        logger.debug(f"完整提示词: {full_prompt}")

        response = client.chat.completions.create(
            model=chat_config['model'],
            messages=[
                {"role": "user", "content": full_prompt}
            ],
            temperature=0.3
        )
        
        content = response.choices[0].message.content
        logger.debug(f"LLM响应: {content}")
        
        # 提取JSON部分
        json_str = re.search(r'\{[\s\S]*\}', content).group(0)
        logger.debug(f"提取的JSON: {json_str}")
        return json_str
    except Exception as e:
        logger.error(f"LLM调用失败: {e}")
        return None
