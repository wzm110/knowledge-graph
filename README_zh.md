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
- **支持向量查询**: 通过向量数据库进行语义相似度搜索

## 建图流程

```
┌─────────────────────────────────────────────────────────────────────┐
│                        知识图谱构建流程                                │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────┐       │
│  │  步骤1       │     │  步骤2        │     │  步骤3       │       │
│  │  提取L1概念   │ ──→ │  提取实体关系  │ ──→ │  向量化处理   │       │
│  │  (目录数据)   │     │  (CSV分块数据) │     │              │       │
│  └──────────────┘     └──────────────┘     └──────────────┘       │
│         │                    │                    │                  │
│         │                    │                    │                  │
│         ↓                    ↓                    ↓                  │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                      步骤4: 数据校准                          │   │
│  │         (去重、层级归属、实体合并、关系验证)                 │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                              │                                      │
│                              ↓                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                      步骤5: 图谱更新                          │   │
│  │         (更新向量库 + 导入Neo4j)                           │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                              │                                      │
│                              ↓                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                      步骤6: 查询                             │   │
│  │         (向量语义搜索 + Neo4j图查询)                        │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### 详细步骤说明

1. **步骤1: 提取L1概念**
   - 输入: 章节目录数据（`目录.csv`）
   - 通过LLM从章节目录中提取顶层知识点（L1概念）
   - 输出: L1概念列表（`l1_concepts.yaml`）

2. **步骤2: 提取实体关系**
   - 输入: 已分块的CSV教材数据
   - 通过LLM从教材正文中提取：
     - 知识点（L2、L3）
     - 知识点之间的关系（contains、prerequisite）
     - 关联的学习资源
   - 输出: 实体列表、关系列表、资源列表

3. **步骤3: 向量化处理**
   - 将提取的实体进行向量化
   - 存储到向量数据库（用于语义相似度搜索）

4. **步骤4: 数据校准**
   - 实体去重（字符串相似度 + 语义相似度）
   - 层级归属确定（L2→L1, L3→L2）
   - 实体合并与别名整合
   - 关系验证与过滤

5. **步骤5: 图谱更新**
   - 更新向量数据库
   - 导入Neo4j图数据库

6. **步骤6: 查询**
   - 向量语义搜索（相似概念推荐）
   - Neo4j图查询（路径分析、学习路径规划）

## 快速开始

### 环境要求

- Python 3.10+
- Neo4j 5.x
- OpenAI API Key（或兼容API）

### 安装

```bash
# 克隆仓库
git clone https://github.com/wzm110/knowledge-graph.git
cd knowledge-graph

# 安装依赖
poetry install

# 复制环境变量配置
cp .env.example .env
# 编辑 .env 填入你的 API Key
```

### 配置

编辑 `config/default.yaml` 或设置环境变量：

```bash
# 环境变量方式（推荐）
export OPENAI_API_KEY=your-api-key
export NEO4J_PASSWORD=your-password
```

### 运行

```bash
# 完整流程（步骤1-6）
poetry run python -m knowledge_graph

# 或分步执行
poetry run python -m knowledge_graph steps.extract_l1      # 步骤1
poetry run python -m knowledge_graph steps.extract       # 步骤2
poetry run python -m knowledge_graph steps.calibrate      # 步骤3-4
poetry run python -m knowledge_graph steps.build           # 步骤5-6
```

### 查询

```python
from knowledge_graph.utils.vector_db import VectorDBManager
from knowledge_graph.utils.neo4j_client import Neo4jClient

# 向量语义搜索
vector_db = VectorDBManager(config)
results = vector_db.find_similar_entities("神经网络", top_k=5)

# Neo4j图查询
neo4j = Neo4jClient(config)
# 查询某个知识点的所有关联
results = neo4j.query("MATCH (k {name: '神经网络基础'})-[r]->(n) RETURN k, r, n")
```

## 项目结构

```
knowledge-graph/
├── config/                    # 配置文件
├── data/
│   └── input/               # 输入教材数据
│       ├── 目录.csv          # 章节目录
│       └── *.csv            # 分章教材内容
├── docs/                     # 文档
├── knowledge_graph/          # 主包
│   ├── steps/              # 处理步骤
│   │   ├── extract_l1.py   # 步骤1: 提取L1概念
│   │   ├── extract.py       # 步骤2: 提取实体关系
│   │   ├── calibrate.py     # 步骤3-4: 数据校准
│   │   └── build.py        # 步骤5-6: 图谱构建
│   └── utils/              # 工具模块
├── tests/                   # 测试
└── prompts/                 # LLM提示词
```

## 数据格式

### 输入数据

**目录数据**（`目录.csv`）：
```csv
title,text
目录," 2. 预备知识 
     2.1. 数据操作 
     2.2. 数据预处理 
     ..."
```

**教材内容**（`*.csv`）：
```csv
title,text,lecture_link,ppt_link,code_link,video_link
章节标题,章节正文内容,视频链接,PPT链接,代码链接,视频链接
```

### 输出数据

- `data/output/l1_concepts.yaml`: L1概念定义
- `data/output/entities.csv`: 所有实体
- `data/output/relationships.csv`: 所有关系
- `data/output/calibrated_entities.csv`: 校准后实体
- `data/output/calibrated_relationships.csv`: 校准后关系

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

如需使用自己的教材数据，请将CSV文件放入 `data/input/` 目录。

## 许可证

MIT License - 详见 [LICENSE](./LICENSE)

## 贡献

欢迎提交 Pull Request！

## 致谢

- [D2L (动手学深度学习)](https://d2l.ai/) - 示例教材数据来源
- [OpenAI](https://openai.com/) - LLM API
- [Neo4j](https://neo4j.com/) - 图数据库
