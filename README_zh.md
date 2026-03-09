# Knowledge Graph Builder - 知识图谱构建工具

[English](./README.md) | 中文

面向教育与学习场景的知识图谱构建系统，支持多教材并存、前置关系推理与学习路径规划。

## 项目目标

在真实教学与学习过程中，同一学科通常存在多种教材、课程与教学资源，不同教材在章节划分、知识点顺序、讲解深度上存在显著差异。然而，学习者真正需要掌握的是稳定的知识点体系，而不是某一本教材的章节结构。

本系统的核心业务目标是：
- 将教材结构与知识体系解耦，构建统一的知识本体图谱
- 在此基础上支撑智能学习与教学应用
- 支持前置关系推理与学习路径规划

## 功能特性

- **多教材支持**: 解耦教材结构与知识体系
- **层次化知识点**: L1（顶层）、L2、L3（详细）三级概念体系
- **前置关系推理**: 使用LLM自动推断学习前置关系
- **学习路径规划**: 基于知识图谱构建个性化学习路径
- **Neo4j集成**: 存储和查询知识图谱
- **向量相似度搜索**: 支持语义相似度检索

## 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                    知识图谱构建系统                           │
├─────────────────────────────────────────────────────────────┤
│  输入（教材数据）                                           │
│    ↓                                                       │
│  ┌─────────────────┐    ┌─────────────────┐                │
│  │  LLM 实体关系   │ → │  数据校准       │                │
│  │    抽取        │    │  (去重、层级)   │                │
│  └─────────────────┘    └─────────────────┘                │
│    ↓                                                       │
│  ┌─────────────────┐    ┌─────────────────┐                │
│  │ L1 前置关系     │ → │  Neo4j 存储     │                │
│  │    推理        │    │                 │                │
│  └─────────────────┘    └─────────────────┘                │
└─────────────────────────────────────────────────────────────┘
```

## 快速开始

### 环境要求

- Python 3.10+
- Neo4j 5.x
- OpenAI API Key（或兼容API）

### 安装

#### 使用 Poetry（推荐）

```bash
# 克隆仓库
git clone https://github.com/wzm110/knowledge-graph.git
cd knowledge-graph

# 安装依赖
poetry install

# 激活虚拟环境
poetry shell
```

#### 使用 pip

```bash
pip install -r requirements.txt
```

### 配置

编辑 `config/default.yaml`：

```yaml
models:
  default_chat_model:
    api_key: your-api-key
    model: qwen3-max
    api_base: https://dashscope.aliyuncs.com/compatible-mode/v1

neo4j:
  uri: neo4j://127.0.0.1:7687
  user: neo4j
  password: your-password
  database: knowledge-graph
```

### 使用

#### 构建知识图谱

```bash
poetry run kg-build
```

#### 查询知识图谱

```python
from knowledge_graph.utils.vector_db import VectorDBManager
from knowledge_graph.steps.build import query_graph

# 查询相似概念
results = query_graph("神经网络", top_k=5)
```

## 项目结构

```
knowledge-graph/
├── config/              # 配置文件
├── data/               # 数据目录
│   ├── input/         # 输入教材数据
│   └── output/        # 生成的图谱
├── docs/              # 文档
├── examples/          # 示例脚本
├── knowledge_graph/   # 主包
│   ├── steps/        # 处理步骤
│   └── utils/        # 工具模块
├── tests/            # 测试
└── prompts/          # LLM提示词
```

## 知识层次

- **L1**: 顶层概念（如"神经网络基础"、"卷积神经网络"）
- **L2**: 子概念（如"反向传播"、"激活函数"）
- **L3**: 详细知识点（如"Sigmoid梯度计算"）

## 关系类型

- **contains**: 层级包含关系（L1→L2→L3）
- **prerequisite**: 学习前置关系
- **has_resource**: 关联学习资源

## 数据说明

本项目包含的教材数据为**示例数据**，来自 [D2L (动手学深度学习)](https://d2l.ai/) 课程内容。

如需使用自己的教材数据，请将 CSV 文件放入 `data/input/` 目录，格式要求：

```csv
title,text,lecture_link,ppt_link,code_link,video_link
章节标题,章节正文内容,视频链接,PPT链接,代码链接,视频链接
```

## 许可证

MIT License - 详见 [LICENSE](./LICENSE)

## 贡献

欢迎提交 Pull Request！

## 致谢

- [D2L (动手学深度学习)](https://d2l.ai/) - 示例教材数据来源
- [OpenAI](https://openai.com/) - LLM API
- [Neo4j](https://neo4j.com/) - 图数据库
