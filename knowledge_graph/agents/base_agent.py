"""知识图谱构建智能体基类"""

import os
import json
import yaml
from abc import ABC, abstractmethod
from typing import Any, Dict, List, TypedDict

from knowledge_graph.utils.logger import get_logger

logger = get_logger(__name__)


class AgentState(TypedDict):
    """所有智能体的基础状态"""
    config: dict
    current_step: str
    iteration: int
    errors: List[str]


class BaseAgent(ABC):
    """知识图谱流水线中所有智能体的基类"""

    def __init__(self, name: str, config: dict, state_persist_path: str = "data/output/agent_state"):
        self.name = name
        self.config = config
        self.state_persist_path = state_persist_path
        os.makedirs(state_persist_path, exist_ok=True)

    @abstractmethod
    def execute(self, state: AgentState) -> AgentState:
        """执行智能体逻辑
        
        参数:
            state: 包含所有数据的当前状态
            
        返回:
            更新后的状态
        """
        pass

    def save_state(self, state: dict, filename: str):
        """保存状态到文件用于持久化"""
        filepath = os.path.join(self.state_persist_path, f"{self.name}_{filename}.json")
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        logger.debug(f"已保存状态到 {filepath}")

    def load_state(self, filename: str) -> dict:
        """从文件加载状态"""
        filepath = os.path.join(self.state_persist_path, f"{self.name}_{filename}.json")
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}

    def save_yaml(self, data: Any, filepath: str):
        """保存数据到YAML文件"""
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False)
        logger.info(f"已保存数据到 {filepath}")

    def save_parquet(self, data: list, filepath: str, mode: str = 'write'):
        """保存数据到Parquet文件
        
        Args:
            data: 数据列表
            filepath: 文件路径
            mode: 'write'覆盖写入, 'append'追加
        """
        import pandas as pd
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        
        df = pd.DataFrame(data)
        
        if mode == 'append' and os.path.exists(filepath):
            existing_df = pd.read_parquet(filepath)
            df = pd.concat([existing_df, df], ignore_index=True)
        
        df.to_parquet(filepath, index=False, engine='pyarrow')
        self.log(f"已保存 {len(df)} 条记录到 {filepath} (mode={mode})")

    def load_parquet(self, filepath: str) -> list:
        """从Parquet文件加载数据"""
        import pandas as pd
        if os.path.exists(filepath):
            df = pd.read_parquet(filepath)
            return df.to_dict('records')
        return []

    def save_csv(self, data: List[dict], filepath: str):
        """保存数据到CSV文件"""
        import pandas as pd
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        df = pd.DataFrame(data)
        df.to_csv(filepath, index=False, encoding='utf-8-sig')
        logger.info(f"已保存 {len(data)} 条记录到 {filepath}")

    def log(self, message: str, level: str = "info"):
        """带智能体名前缀的日志"""
        prefix = f"[{self.name}]"
        if level == "info":
            logger.info(f"{prefix} {message}")
        elif level == "warning":
            logger.warning(f"{prefix} {message}")
        elif level == "error":
            logger.error(f"{prefix} {message}")
        elif level == "debug":
            logger.debug(f"{prefix} {message}")


class LLMAgent(BaseAgent):
    """使用LLM的智能体基类"""

    def __init__(self, name: str, config: dict, prompt_path: str = None):
        super().__init__(name, config)
        self.prompt_path = prompt_path

    def load_prompt(self, prompt_path: str = None) -> str:
        """从文件加载提示词模板"""
        path = prompt_path or self.prompt_path
        if path and os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return f.read()
        return ""

    def call_llm(self, prompt: str, text: str = "") -> str:
        """调用LLM"""
        from knowledge_graph.utils.llm import call_llm
        return call_llm(prompt, text, self.config)
