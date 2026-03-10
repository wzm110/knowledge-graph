#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Node 1: L1知识点提取智能体
从目录中提取L1知识点
"""

import os
import glob
import json
from typing import Dict, List

from knowledge_graph.agents.base_agent import LLMAgent, AgentState


class L1ExtractorAgent(LLMAgent):
    """从TOC文件提取L1知识点的智能体"""

    def __init__(self, config: dict):
        super().__init__(
            name="L1Extractor",
            config=config,
            prompt_path="prompts/L1_Extraction_Prompt.txt"
        )
        self.feedback = None
        self.use_feedback_prompt = False

    def set_feedback(self, feedback: str):
        """设置来自验证的反馈以改进提取"""
        self.feedback = feedback
        self.use_feedback_prompt = True

    def load_toc_files(self, toc_dir: str = "data/input/Table_of_Contents") -> Dict[str, str]:
        """从目录加载所有TOC文件"""
        self.log(f"正在加载TOC文件: {toc_dir}")
        
        toc_files = glob.glob(os.path.join(toc_dir, "*.txt"))
        self.log(f"找到 {len(toc_files)} 个TOC文件")

        toc_data = {}
        for toc_file in toc_files:
            book_name = os.path.basename(toc_file).replace('.txt', '')
            with open(toc_file, 'r', encoding='utf-8') as f:
                toc_data[book_name] = f.read()
            self.log(f"  已加载: {book_name}, {len(toc_data[book_name])} 字符")

        return toc_data

    def format_chapters_for_prompt(self, toc_data: Dict[str, str]) -> str:
        """格式化章节用于LLM提示词"""
        formatted = []
        for book_name, toc_text in toc_data.items():
            chapters = self._extract_chapters(toc_text)
            formatted.append(f"\n【{book_name}】")
            for ch in chapters:
                formatted.append(f"  - {ch}")
        return "\n".join(formatted)

    def _extract_chapters(self, toc_text: str) -> List[str]:
        """从TOC文本提取章节标题"""
        import re
        lines = toc_text.strip().split('\n')
        chapter_pattern = re.compile(r'^\s*(\d+(?:\.\d+)*)\s*\.?\s*(.+)$')

        chapters = []
        for line in lines:
            match = chapter_pattern.match(line.strip())
            if match:
                number = match.group(1)
                title = match.group(2).strip()
                if number.count('.') == 0 or (number.count('.') == 1 and not title.lower().startswith('chap')):
                    chapters.append(title)
        return chapters

    def execute(self, state: AgentState) -> AgentState:
        """执行L1提取"""
        self.log("开始提取L1知识点")
        
        iteration = state.get('iteration', 1)
        self.log(f"提取迭代: {iteration}")

        toc_dir = "data/input/Table_of_Contents"
        toc_data = self.load_toc_files(toc_dir)
        all_chapters = self.format_chapters_for_prompt(toc_data)

        prompt_template = self.load_prompt()
        
        subject = self.config.get('pipeline', {}).get('subject', '深度学习')
        
        previous_l1 = ""
        if state.get('validated_l1_concepts'):
            previous_l1 = "\n".join([
                f"- {c.get('name', '')}: {c.get('definition', '')}"
                for c in state['validated_l1_concepts']
            ])
        
        if self.use_feedback_prompt and self.feedback:
            feedback_prompt_path = "prompts/L1_Extraction_With_Feedback_Prompt.txt"
            if os.path.exists(feedback_prompt_path):
                prompt_template = self.load_prompt(feedback_prompt_path)
                self.log("使用反馈提示词改进提取")
        
        prompt = prompt_template.replace("{subject}", subject)
        prompt = prompt.replace("{previous_l1_points}", previous_l1 or "无")
        prompt = prompt.replace("{feedback}", self.feedback if self.feedback else "")
        prompt = prompt.replace("{all_chapters}", all_chapters)

        self.log(f"调用LLM，提示词长度: {len(prompt)} 字符")
        
        try:
            response = self.call_llm(prompt, "")
            
            response = response.strip()
            if not response.startswith('['):
                response = '[' + response
            if not response.endswith(']'):
                response = response + ']'
            
            data = json.loads(response)
            
            if isinstance(data, list):
                l1_points = []
                for i, item in enumerate(data, 1):
                    point = {
                        'id': f"l1-{i}",
                        'name': item.get('name', ''),
                        'definition': item.get('definition', ''),
                        'level': 'L1',
                        'source_chapters': item.get('source_chapters', [])
                    }
                    l1_points.append(point)
                
                state['l1_concepts'] = l1_points
                state['l1_extraction_prompt'] = prompt
                state['current_step'] = 'extract_l1'
                
                self.save_parquet(
                    l1_points,
                    'data/output/stage1_entities.parquet'
                )
                
                self.log(f"成功提取 {len(l1_points)} 个L1知识点")
            else:
                state['errors'].append(f"LLM响应格式不符合预期")
                
        except json.JSONDecodeError as e:
            self.log(f"JSON解析错误: {e}", "error")
            state['errors'].append(f"解析LLM响应失败: {e}")
        except Exception as e:
            self.log(f"提取错误: {e}", "error")
            state['errors'].append(str(e))

        return state


def create_l1_extractor(config: dict) -> L1ExtractorAgent:
    """工厂函数：创建L1提取智能体"""
    return L1ExtractorAgent(config)
