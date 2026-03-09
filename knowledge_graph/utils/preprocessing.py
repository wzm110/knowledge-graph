#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据预处理步骤
"""

import os
import pandas as pd
from utils.logger import get_logger

logger = get_logger(__name__)

# 文本分块函数
def chunk_text(text, max_chunk_size=1500):
    """将长文本分割成小块"""
    chunks = []
    current_chunk = ""
    for sentence in text.split('\n'):
        if len(current_chunk) + len(sentence) < max_chunk_size:
            current_chunk += sentence + '\n'
        else:
            chunks.append(current_chunk)
            current_chunk = sentence + '\n'
    if current_chunk:
        chunks.append(current_chunk)
    return chunks

# 数据预处理
def data_preprocessing(config, input_file="data/input/多层感知机.csv"):
    """数据预处理"""
    logger.info("=== 开始数据预处理 ===")
    
    # 创建输出目录
    os.makedirs('output', exist_ok=True)
    
    try:
        # 读取CSV文件
        logger.info(f"读取输入文件: {input_file}")
        # 读取CSV文件时处理BOM
        df = pd.read_csv(input_file, encoding='utf-8-sig')
        logger.info(f"成功读取 {len(df)} 个章节")
        logger.debug(f"CSV列名: {list(df.columns)}")
        # 检查是否有'title'列
        if 'title' in df.columns:
            logger.debug(f"章节标题: {list(df['title'].values[:5])}...")
        else:
            logger.error(f"CSV文件中没有'title'列，列名是: {list(df.columns)}")
            # 尝试使用第一个列作为标题
            if len(df.columns) > 0:
                logger.info(f"使用第一列 '{df.columns[0]}' 作为标题列")
        
        # 数据预处理和分块
        processed_data = []
        chunk_id = 0
        
        # 限制处理的章节数量，仅处理前3个章节以加快测试速度
        for chapter_id, row in df.iterrows():
            if chapter_id >= 3:
                break
            # 更灵活地获取列数据
            chapter_title = row.get('title', row.get(df.columns[0], ''))
            text = row.get('text', '')
            lecture_link = row.get('lecture_link', '')
            ppt_link = row.get('ppt_link', '')
            code_link = row.get('code_link', '')
            video_link = row.get('video_link', '')
            
            # 清理文本
            text = text.strip()
            logger.debug(f"章节 {chapter_id} - {chapter_title}, 文本长度: {len(text)}")
            
            # 文本分块
            chunks = chunk_text(text)
            logger.info(f"章节 {chapter_id} - {chapter_title} 分成 {len(chunks)} 个文本块")
            
            for i, chunk in enumerate(chunks):
                processed_item = {
                    'chapter_id': chapter_id,
                    'chapter_title': chapter_title,
                    'chunk_id': chunk_id,
                    'text_chunk': chunk,
                    'lecture_link': lecture_link,
                    'ppt_link': ppt_link,
                    'code_link': code_link,
                    'video_link': video_link
                }
                processed_data.append(processed_item)
                logger.debug(f"添加文本块 {chunk_id}: 长度={len(chunk)}")
                chunk_id += 1
        
        # 保存处理后的数据
        processed_df = pd.DataFrame(processed_data)
        output_file = 'output/processed_data.csv'
        processed_df.to_csv(output_file, index=False, encoding='utf-8')
        logger.info(f"数据预处理完成，生成 {output_file}，共 {len(processed_data)} 个文本块")
        
        return processed_data
    except Exception as e:
        logger.error(f"数据预处理失败: {e}")
        raise
