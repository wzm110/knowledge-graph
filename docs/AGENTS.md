# Agent 详细解释文档

本文档详细说明了知识图谱构建系统中的各个智能体（Agent）的功能、职责和实现细节。

## 目录

1. [架构概述](#1-架构概述)
2. [Agent 列表](#2-agent-列表)
3. [基类说明](#3-基类说明)

---

## 1. 架构概述

知识图谱构建系统采用多阶段流水线架构，包含8个核心智能体：

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        知识图谱构建流水线                                 │
├─────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐                │
│  │   Agent 1   │───▶│   Agent 2   │───▶│   Agent 3   │                │
│  │ L1Extractor │    │L1Validator  │    │L1Prerequisite               │
│  │   (L1提取)   │    │  (L1验证)    │    │ (前置关系)  │               │
│  └─────────────┘    └─────────────┘    └─────────────┘                │
│       │                   │                   │                         │
│       │  (验证失败?)       │                   │                         │
│       │       │          │                   ▼                         │
│       │       ▼          │           ┌─────────────┐                   │
│       │  ┌────────┐      │           │   Agent 4   │                   │
│       │  │ 循环   │      │           │EntityExtractor               │
│       │  │ 回到   │      │           │ (实体提取)  │                   │
│       │  │ Agent1 │      │           └─────────────┘                   │
│       │  └────────┘      │                   │                         │
│       │       │          │                   ▼                         │
│       │       ▼          │           ┌─────────────┐                   │
│       │  ┌───────────────┴──────────▶│   Agent 5   │                   │
│       │                              │Vectorization │                   │
│       │                              │  (向量化)    │                   │
│       │                              └─────────────┘                   │
│       │                                    │                           │
│       │                                    ▼                           │
│       │                              ┌─────────────┐                   │
│       │                              │   Agent 6   │                   │
│       │                              │ Calibration  │                   │
│       │                              │  (数据校准)  │                   │
│       │                              └─────────────┘                   │
│       │                                    │                           │
│       │                                    ▼                           │
│       │                              ┌─────────────┐                   │
│       │                              │   Agent 7   │                   │
│       │                              │ Evaluation  │                   │
│       │                              │   (评测)     │                   │
│       │                              └─────────────┘                   │
│       │                                    │                           │
│       │                                    ▼                           │
│       │                              ┌─────────────┐                   │
│       └─────────────────────────────▶│   Agent 8   │                   │
│                                     │GraphBuilder  │                   │
│                                     │  (图构建)    │                   │
│                                     └─────────────┘                   │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Agent 列表

### 2.1 L1ExtractorAgent - L1知识点提取智能体

| 属性 | 值 |
|------|-----|
| **Node编号** | Node 1 |
| **文件位置** | `knowledge_graph/agents/l1_extractor.py` |
| **类名** | `L1ExtractorAgent` |
| **父类** | `LLMAgent` |

#### 功能说明

L1ExtractorAgent 是知识图谱构建流水线的第一个智能体，负责从教材章节目录（TOC）中提取L1级别（最顶层）的知识点。

#### 输入数据

- **TOC文件**：位于 `data/input/Table_of_Contents/` 目录下的 `.txt` 文件
- **配置信息**：包含主题（subject）等 pipeline 配置

#### 处理流程

1. **加载TOC文件**：读取所有章节目录文件
2. **格式化章节**：将TOC文本解析为章节标题列表
3. **构建提示词**：使用 `L1_Extraction_Prompt.txt` 模板构建LLM提示词
4. **调用LLM**：请求大语言模型提取L1知识点
5. **解析响应**：将LLM返回的JSON转换为知识点对象
6. **保存结果**：输出到 YAML 和 Parquet 格式

#### 输出数据

```python
l1_concepts: [
    {
        "id": "l1-1",
        "name": "知识点名称",
        "definition": "知识点定义",
        "level": "L1",
        "source_chapters": ["章节1", "章节2"]
    },
    ...
]
```

#### 提示词模板

使用文件：`prompts/L1_Extraction_Prompt.txt`

#### 反馈循环支持

当验证失败时，该Agent可以接收反馈并使用 `L1_Extraction_With_Feedback_Prompt.txt` 提示词重新提取。

#### 迭代机制

- 支持迭代次数跟踪（`iteration`）
- 最多支持3次重试

---

### 2.2 L1ValidatorAgent - L1知识点验证智能体

| 属性 | 值 |
|------|-----|
| **Node编号** | Node 2 |
| **文件位置** | `knowledge_graph/agents/l1_validator.py` |
| **类名** | `L1ValidatorAgent` |
| **父类** | `LLMAgent` |

#### 功能说明

L1ValidatorAgent 负责对提取的L1知识点进行整体验证，确保知识系统的完整性、一致性和认知逻辑性。

#### 输入数据

- **L1知识点列表**：来自 L1ExtractorAgent 的输出
- **配置信息**：包含主题（subject）

#### 处理流程

1. **加载验证提示词**：使用 `L1_Validation_Prompt.txt` 模板
2. **构建验证请求**：将所有L1知识点格式化为提示词
3. **调用LLM评估**：请求大语言模型进行整体评估
4. **解析评估结果**：提取评分、反馈和改进建议
5. **判断是否通过**：
   - 总体评分 ≥ 7 分
   - 每个维度评分 ≥ 6 分
6. **生成验证报告**：输出详细的验证摘要

#### 评估维度

| 维度 | 说明 | 阈值 |
|------|------|------|
| 整体完整性 | 核心内容覆盖是否全面 | ≥6 |
| 认知逻辑性 | 知识递进关系是否合理 | ≥6 |
| 学习路径导向 | 是否具有里程碑意义 | ≥6 |
| 颗粒度一致性 | 同一领域内容颗粒度是否一致 | ≥6 |
| 定义清晰度 | 边界是否明确 | ≥6 |

#### 输出数据

```python
validated_l1_concepts: [
    {
        "id": "l1-1",
        "name": "知识点名称",
        "definition": "知识点定义",
        "level": "L1",
        "validation": {
            "overall_score": 8,
            "overall_feedback": "验证反馈",
            "is_valid": True
        }
    },
    ...
]

validation_summary: {
    "total": 10,
    "valid": 1,
    "invalid": 0,
    "overall_score": 8,
    "dimensions": {...},
    "overall_feedback": "..."
}

validation_errors: [
    {
        "name": "整体系统",
        "feedback": "问题描述",
        "total_score": 8
    }
]
```

#### 验证循环

- 如果验证失败，生成详细的反馈信息
- 将反馈返回给 L1ExtractorAgent 进行重新提取
- 最多支持3次迭代

---

### 2.3 L1PrerequisiteAgent - L1前置关系提取智能体

| 属性 | 值 |
|------|-----|
| **Node编号** | Node 3 |
| **文件位置** | `knowledge_graph/agents/l1_prerequisite.py` |
| **类名** | `L1PrerequisiteAgent` |
| **父类** | `LLMAgent` |

#### 功能说明

L1PrerequisiteAgent 负责提取L1知识点之间的学习前置关系，即学习某个知识点之前需要先掌握哪些知识点。

#### 输入数据

- **已验证的L1知识点列表**：来自 L1ValidatorAgent 的输出

#### 处理流程

1. **加载知识点**：获取所有已验证的L1知识点
2. **构建提示词**：使用 `L1_Prerequisite_Prompt.txt` 模板
3. **调用LLM分析**：请求大语言模型分析前置关系
4. **解析响应**：提取前置关系列表
5. **ID映射**：将知识点名称映射为实际ID
6. **保存结果**：输出到 CSV 和 Parquet 格式

#### 输出数据

```python
l1_prerequisites: [
    {
        "type": "prerequisite",
        "start_id": "l1-1",
        "end_id": "l1-2",
        "end_type": "L1",
        "reason": "学习A之前需要先掌握B，因为..."
    },
    ...
]
```

#### 关系类型

- **prerequisite**：前置关系，表示学习的先后顺序

---

### 2.4 EntityExtractorAgent - 实体与关系提取智能体

| 属性 | 值 |
|------|-----|
| **Node编号** | Node 4 |
| **文件位置** | `knowledge_graph/agents/entity_extractor.py` |
| **类名** | `EntityExtractorAgent` |
| **父类** | `LLMAgent` |

#### 功能说明

EntityExtractorAgent 是知识图谱构建的核心智能体之一，负责从教材内容中提取L2和L3级别的知识点、关系和教学资源。

#### 输入数据

- **已验证的L1知识点列表**：来自 L1ValidatorAgent
- **教材章节数据**：来自 `data/input/*.csv` 文件

#### 处理流程

1. **加载教材数据**：读取所有CSV文件中的章节内容
2. **遍历章节**：对每个章节逐一处理
3. **构建提取提示词**：
   - 包含当前L1知识点列表
   - 包含该章节对应的资源链接
   - 包含章节文本内容
4. **调用LLM提取**：
   - 提取L2知识点（从属于L1）
   - 提取L3知识点（更细粒度）
   - 提取关系（contains, prerequisite, has_resource）
   - 提取资源链接
5. **保存结果**：输出到 CSV 和 Parquet 格式

#### 输出数据

```python
knowledge_points: [
    {
        "id": "l2-1",
        "name": "L2知识点名称",
        "definition": "知识点定义",
        "level": "L2",
        "parent_l1": "父级L1知识点",
        "source": "来源章节"
    },
    {
        "id": "l3-1",
        "name": "L3知识点名称",
        "definition": "知识点定义",
        "level": "L3",
        "source": "来源章节"
    },
    ...
]

relationships: [
    {
        "type": "contains",
        "start_id": "l1-1",
        "end_id": "l2-1",
        "reason": "..."
    },
    ...
]

resources: [
    {
        "id": "res-1",
        "type": "lecture",
        "title": "课程标题",
        "url": "https://...",
        "source": "来源章节"
    },
    ...
]
```

#### 资源类型

- **lecture**：课程讲义
- **ppt**：演示文稿
- **code**：代码示例
- **video**：视频教程

---

### 2.5 VectorizationAgent - 向量化智能体

| 属性 | 值 |
|------|-----|
| **Node编号** | Node 5 |
| **文件位置** | `knowledge_graph/agents/vectorization.py` |
| **类名** | `VectorizationAgent` |
| **父类** | `BaseAgent` |

#### 功能说明

VectorizationAgent 负责将提取的知识点和资源转换为向量表示，并存储到向量数据库中，支持语义检索。

#### 输入数据

- **知识点列表**：来自 EntityExtractorAgent
- **资源列表**：来自 EntityExtractorAgent

#### 处理流程

1. **合并实体**：将知识点和资源合并为统一实体列表
2. **初始化向量数据库**：使用配置中的向量数据库设置
3. **批量向量化**：将实体文本转换为向量表示
4. **存储到向量数据库**：使用 LanceDB 或其他向量数据库
5. **保存状态**：记录向量数据库更新状态

#### 输出数据

```python
vector_db_updated: True
```

#### 向量数据库

- 默认使用 **LanceDB**
- 支持向量相似度检索
- 用于后续的语义搜索和推荐

---

### 2.6 CalibrationAgent - 数据校准智能体

| 属性 | 值 |
|------|-----|
| **Node编号** | Node 6 |
| **文件位置** | `knowledge_graph/agents/calibration.py` |
| **类名** | `CalibrationAgent` |
| **父类** | `BaseAgent` |

#### 功能说明

CalibrationAgent 是数据质量保障的核心智能体，负责对多个阶段提取的数据进行去重、层级归属和关系验证。

#### 输入数据

- **L1知识点**：来自 L1ValidatorAgent
- **Stage1实体**：来自 L1ExtractorAgent（第一阶段）
- **Stage2关系**：来自 L1PrerequisiteAgent
- **Stage3实体**：来自 EntityExtractorAgent

#### 处理流程

1. **合并实体**：
   - 合并 L1、Stage1、Stage3 的所有知识点
   - 避免重复ID
2. **去重处理**：
   - 基于名称相似度进行去重
   - 保留首次出现的实体
3. **层级归属**：
   - L2知识点关联到对应的L1父节点
   - L3知识点标记层级
4. **资源去重**：对教学资源进行去重
5. **关系整合**：合并前置关系和其他关系
6. **保存校准结果**：输出到 CSV 和 Parquet 格式

#### 输出数据

```python
calibrated_kps: [
    {
        "id": "l1-1",
        "name": "知识点名称",
        "definition": "定义",
        "level": "L1",
        "parent_id": "",
        "source": "stage1/stage3"
    },
    ...
]

calibrated_resources: [...]

calibrated_relationships: [
    {
        "type": "prerequisite/contains/has_resource",
        "start_id": "...",
        "end_id": "...",
        "end_type": "L1/L2/L3",
        "reason": "..."
    },
    ...
]
```

---

### 2.7 EvaluationAgent - 评测智能体

| 属性 | 值 |
|------|-----|
| **Node编号** | Node 7 |
| **文件位置** | `knowledge_graph/agents/evaluation.py` |
| **类名** | `EvaluationAgent` |
| **父类** | `LLMAgent` |

#### 功能说明

EvaluationAgent 负责对构建完成的知识图谱进行全面的质量评估，生成评估报告和改进建议。

#### 输入数据

- **校准后的知识点**：来自 CalibrationAgent
- **校准后的资源**：来自 CalibrationAgent
- **校准后的关系**：来自 CalibrationAgent

#### 处理流程

1. **收集统计信息**：
   - 知识点总数
   - L1/L2/L3 各层级数量
   - 资源总数
   - 关系总数及类型分布
2. **构建评估提示词**：使用 `Evaluation_Prompt.txt` 模板
3. **调用LLM评估**：请求大语言模型进行多维度评估
4. **生成评估报告**：输出总体评分和改进建议
5. **保存报告**：输出 JSON/YAML 格式的评估报告

#### 输出数据

```python
evaluation_report: {
    "overall_score": 8.5,
    "dimensions": {
        "completeness": {...},
        "accuracy": {...},
        "consistency": {...},
        "usefulness": {...}
    },
    "strengths": [...],
    "improvements": [...],
    "recommendations": [...]
}
```

#### 评估维度（示例）

| 维度 | 说明 |
|------|------|
| 完整性 | 知识点覆盖是否全面 |
| 准确性 | 知识点定义是否准确 |
| 一致性 | 层级结构是否一致 |
| 可用性 | 是否适合教学使用 |

---

### 2.8 GraphBuilderAgent - 图构建智能体

| 属性 | 值 |
|------|-----|
| **Node编号** | Node 8 |
| **文件位置** | `knowledge_graph/agents/graph_builder.py` |
| **类名** | `GraphBuilderAgent` |
| **父类** | `BaseAgent` |

#### 功能说明

GraphBuilderAgent 是流水线的最后一个智能体，负责将校准后的知识图谱数据导入到 Neo4j 图数据库中。

#### 输入数据

- **校准后的知识点**：来自 CalibrationAgent
- **校准后的资源**：来自 CalibrationAgent
- **校准后的关系**：来自 CalibrationAgent

#### 处理流程

1. **连接Neo4j**：使用配置的连接信息
2. **清除现有数据**：删除图谱中的所有现有节点和关系
3. **创建L1节点**：批量创建L1知识点节点
4. **创建L2节点**：批量创建L2知识点节点（含父节点ID）
5. **创建L3节点**：批量创建L3知识点节点
6. **创建资源节点**：批量创建资源节点
7. **创建关系**：根据类型创建各类关系
8. **关闭连接**：释放数据库连接

#### 输出数据

```python
neo4j_imported: True
```

#### Neo4j 数据模型

**节点类型**：
- `KnowledgePoint`：知识点
  - id, name, definition, level, parent_id
- `Resource`：教学资源
  - id, type, title, url

**关系类型**：
- `prerequisite`：前置关系
- `contains`：包含关系
- `has_resource`：资源关联

---

## 3. 基类说明

### 3.1 BaseAgent - 基础智能体类

| 属性 | 值 |
|------|-----|
| **文件位置** | `knowledge_graph/agents/base_agent.py` |
| **类名** | `BaseAgent` |

#### 功能说明

BaseAgent 是所有智能体的基类，提供通用的状态管理、持久化和日志功能。

#### 核心方法

| 方法 | 说明 |
|------|------|
| `execute(state)` | 抽象方法，执行智能体逻辑 |
| `save_state(state, filename)` | 保存状态到JSON文件 |
| `load_state(filename)` | 从JSON文件加载状态 |
| `save_yaml(data, filepath)` | 保存数据到YAML文件 |
| `save_parquet(data, filepath)` | 保存数据到Parquet文件 |
| `load_parquet(filepath)` | 从Parquet文件加载数据 |
| `save_csv(data, filepath)` | 保存数据到CSV文件 |
| `log(message, level)` | 带智能体名前缀的日志 |

#### AgentState 定义

```python
class AgentState(TypedDict):
    config: dict           # 配置信息
    current_step: str      # 当前步骤名称
    iteration: int         # 当前迭代次数
    errors: List[str]      # 错误列表
```

---

### 3.2 LLMAgent - 大语言模型智能体基类

| 属性 | 值 |
|------|-----|
| **文件位置** | `knowledge_graph/agents/base_agent.py` |
| **类名** | `LLMAgent` |
| **父类** | `BaseAgent` |

#### 功能说明

LLMAgent 继承自 BaseAgent，专门用于需要调用大语言模型的智能体。

#### 核心方法

| 方法 | 说明 |
|------|------|
| `load_prompt(prompt_path)` | 从文件加载提示词模板 |
| `call_llm(prompt, text)` | 调用LLM获取响应 |

#### 使用方式

```python
class MyLLMAgent(LLMAgent):
    def __init__(self, config: dict):
        super().__init__(
            name="MyAgent",
            config=config,
            prompt_path="prompts/my_prompt.txt"
        )

    def execute(self, state: AgentState) -> AgentState:
        prompt_template = self.load_prompt()
        prompt = prompt_template.replace("{variable}", "value")
        response = self.call_llm(prompt, "")
        # 处理响应...
        return state
```

---

## 附录：文件路径映射

| Agent | Python文件 | 提示词文件 | 输出文件 |
|-------|------------|------------|----------|
| L1Extractor | `l1_extractor.py` | `L1_Extraction_Prompt.txt` | `l1_concepts.yaml` |
| L1Validator | `l1_validator.py` | `L1_Validation_Prompt.txt` | `l1_validation_report.csv` |
| L1Prerequisite | `l1_prerequisite.py` | `L1_Prerequisite_Prompt.txt` | `l1_prerequisites.csv` |
| EntityExtractor | `entity_extractor.py` | `Entity_Extraction_Prompt.txt` | `entities.csv`, `relationships.csv` |
| Vectorization | `vectorization.py` | - | 向量数据库 |
| Calibration | `calibration.py` | - | `calibrated_*.csv` |
| Evaluation | `evaluation.py` | `Evaluation_Prompt.txt` | `evaluation_report.json` |
| GraphBuilder | `graph_builder.py` | - | Neo4j图谱 |
