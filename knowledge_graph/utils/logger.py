#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
日志工具模块
"""

import logging
import os
from datetime import datetime

# 创建日志目录
log_dir = 'logs'
os.makedirs(log_dir, exist_ok=True)

# 生成日志文件名
log_filename = os.path.join(log_dir, f"knowledge_graph_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")

# 配置日志
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_filename, encoding='utf-8'),
        logging.StreamHandler()
    ]
)

# 创建日志器
def get_logger(name):
    """获取日志器"""
    return logging.getLogger(name)

# 示例使用
if __name__ == "__main__":
    logger = get_logger(__name__)
    logger.debug("调试信息")
    logger.info("信息")
    logger.warning("警告")
    logger.error("错误")
