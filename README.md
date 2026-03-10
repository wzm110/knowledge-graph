# Knowledge Graph Builder - 知识图谱构建工具

基于LLM的自动化知识图谱构建流水线，从教材内容中提取知识点、关系和资源。

## 功能特性

### 🚀 核心功能
- **L1知识点提取**: 从教材目录自动提取顶层知识点
- **智能验证**: 基于反馈循环的知识点质量验证
- **前置关系提取**: 自动分析知识点间的学习依赖关系
- **实体关系提取**: 从教材内容提取L2/L3知识点和关系
- **向量检索**: 支持语义相似度搜索
- **Neo4j图谱**: 构建可查询的知识图谱

### ⚡ 性能优化
- **LLM缓存**: 相同输入自动复用结果，支持断点恢复
- **进度条**: 实时显示处理进度
- **Parquet存储**: 高效的列式存储格式

### 🏗️ 架构
- **LangGraph风格**: 8步流水线设计，清晰的任务分工
- **Agent模块化**: 每个节点独立可扩展
- **状态持久化**: 支持从任意阶段恢复

## 项目结构

```
knowledge_graph/
├── agents/                    # 智能体模块
│   ├── base_agent.py         # Agent基类
│   ├── l1_extractor.py       # Node 1: L1知识点提取
│   ├── l1_validator.py       # Node 2: L1验证
│   ├── l1_prerequisite.py   # Node 3: 前置关系提取
│   ├── entity_extractor.py   # Node 4: 实体关系提取
│   ├── vectorization.py      # Node 5: 向量化
│   ├── calibration.py        # Node 6: 数据校准
│   ├── evaluation.py         # Node 7: LLM评测
│   └── graph_builder.py     # Node 8: 图谱构建
├── utils/                    # 工具模块
│   ├── config.py            # 配置管理
│   ├── llm.py              # LLM调用(含缓存)
│   ├── logger.py            # 日志工具
│   ├── vector_db.py         # 向量数据库
│   └── preprocessing.py     # 数据预处理
├── pipeline.py               # 主流水线入口
└── __main__.py              # CLI入口

prompts/                      # 提示词模板
├── L1_Extraction_Prompt.txt
├── L1_Validation_Prompt.txt
├── L1_Prerequisite_Prompt.txt
├── Entity_Extraction_Prompt.txt
└── Evaluation_Prompt.txt

config/
└── default.yaml             # 配置文件
```

## 快速开始

### 安装依赖
```bash
pip install -r requirements.txt
```

### 配置
复制并编辑配置文件:
```bash
cp .env.example .env
# 编辑 .env 填入API密钥
```

### 运行
```bash
# 完整流程
python -m knowledge_graph.pipeline

# 测试模式(仅处理少量数据)
python -m knowledge_graph.pipeline --test

# 自定义验证循环次数
python -m knowledge_graph.pipeline --max-loops 5
```

## 数据流

```
输入数据
  │
  ├─→ Table_of_Contents/     # 教材目录
  └─→ *.csv                   # 教材内容
          │
          ▼
┌─────────────────────────────────────────────┐
│  Node 1-2: L1提取 + 验证 (带反馈循环)       │
└─────────────────────────────────────────────┘
          │
          ▼ stage1_entities.parquet (L1)
┌─────────────────────────────────────────────┐
│  Node 3: L1前置关系提取                      │
└─────────────────────────────────────────────┘
          │
          ▼ stage2_relationships.parquet
┌─────────────────────────────────────────────┐
│  Node 4: 实体关系提取 (L2/L3)               │
└─────────────────────────────────────────────┘
          │
          ▼ stage3_entities.parquet
          ▼ stage3_relationships.parquet
┌─────────────────────────────────────────────┐
│  Node 5-6: 向量化 + 校准                    │
└─────────────────────────────────────────────┘
          │
          ▼ calibrated_entities.parquet
          ▼ calibrated_relationships.parquet
┌─────────────────────────────────────────────┐
│  Node 7-8: 评测 + Neo4j图谱                │
└─────────────────────────────────────────────┘
```

## 中间文件说明

| 文件 | 说明 |
|------|------|
| stage1_entities.parquet | L1知识点 |
| stage2_relationships.parquet | L1前置关系 |
| stage3_entities.parquet | L2/L3知识点 |
| stage3_relationships.parquet | L2/L3关系 |
| calibrated_entities.parquet | 校准后全量知识点 |
| calibrated_relationships.parquet | 校准后全量关系 |

支持从任意阶段读取中间文件单独调试后续步骤。

## 配置说明

```yaml
pipeline:
  subject: 深度学习          # 科目背景
  max_workers: 5            # 并发数
  batch_size: 10            # 批处理大小

models:
  default_chat_model:
    model: qwen3-max        # LLM模型
    api_key: ${API_KEY}    # API密钥
    api_base: https://dashscope.aliyuncs.com/...
    temperature: 0.3

vector_db:
  provider: lancedb
  path: data/output/lancedb

neo4j:
  uri: neo4j://127.0.0.1:7687
  user: neo4j
  password: ${NEO4J_PASSWORD}
```

## 版本历史

### v1.0.0 (2026-03-10)
**重大更新: LangGraph重构**

#### 新增功能
- ✅ 完整8步LangGraph风格流水线
- ✅ L1知识点智能验证(带反馈循环)
- ✅ 整体评估模式(而非单个知识点评估)
- ✅ 科目背景支持(可配置)
- ✅ 大局观评估原则

#### 架构改进
- ✅ Agent模块化设计
- ✅ Parquet中间文件存储
- ✅ 支持断点恢复
- ✅ LLM响应缓存
- ✅ 进度条显示
- ✅ 全中文日志

#### 提示词优化
- ✅ 实体提取提示词完善(L2/L3/Resource)
- ✅ 包含示例输出
- ✅ 评估规则细化

#### 数据格式
- ✅ Parquet替代CSV存储
- ✅ 分阶段中间文件
- ✅ 支持单独调试数据校准

---

### v0.x (早期版本)
- 初始版本
- 基本的实体关系提取
