#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LLM调用工具模块 - 支持缓存
"""

import openai
import re
import os
import json
import hashlib
from knowledge_graph.utils.logger import get_logger

logger = get_logger(__name__)

CACHE_DIR = "data/output/llm_cache"


def get_cache_key(full_prompt: str, config: dict) -> str:
    """生成缓存key"""
    chat_config = config.get('models', {}).get('default_chat_model', {})
    model = chat_config.get('model', 'default')
    
    content = f"{model}:{full_prompt}"
    return hashlib.md5(content.encode('utf-8')).hexdigest()


def load_from_cache(cache_key: str) -> str | None:
    """从缓存加载"""
    cache_file = os.path.join(CACHE_DIR, f"{cache_key}.json")
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            logger.info(f"从缓存加载: {cache_key[:8]}...")
            return data.get('response')
        except Exception as e:
            logger.warning(f"缓存加载失败: {e}")
    return None


def save_to_cache(cache_key: str, full_prompt: str, response: str, config: dict):
    """保存到缓存"""
    os.makedirs(CACHE_DIR, exist_ok=True)
    
    chat_config = config.get('models', {}).get('default_chat_model', {})
    model = chat_config.get('model', 'default')
    
    cache_file = os.path.join(CACHE_DIR, f"{cache_key}.json")
    try:
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump({
                'model': model,
                'prompt': full_prompt,
                'response': response
            }, f, ensure_ascii=False, indent=2)
        logger.info(f"已保存到缓存: {cache_key[:8]}...")
    except Exception as e:
        logger.warning(f"缓存保存失败: {e}")


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


def call_llm(prompt, text, config):
    """调用LLM，支持缓存"""
    chat_config = config['models']['default_chat_model']
    
    client = openai.OpenAI(
        api_key=chat_config['api_key'],
        base_url=chat_config['api_base']
    )
    
    try:
        full_prompt = f"{prompt}\n\n文本块内容：\n{text}\n\n请以JSON格式输出结果。"
        logger.info(f"调用LLM，提示词长度: {len(full_prompt)}")
        logger.info(f"文本块长度: {len(text)}")
        
        cache_key = get_cache_key(full_prompt, config)
        cached_response = load_from_cache(cache_key)
        
        if cached_response:
            logger.info("使用缓存响应")
            return cached_response
        
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
        
        json_str = re.search(r'\{[\s\S]*\}', content).group(0)
        logger.debug(f"提取的JSON: {json_str}")
        
        save_to_cache(cache_key, full_prompt, json_str, config)
        
        return json_str
    except Exception as e:
        logger.error(f"LLM调用失败: {e}")
        return None
