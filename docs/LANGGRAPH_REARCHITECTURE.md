# Knowledge Graph Builder - LangGraph 重构规划文档

## 1. 概述

### 1.1 目标
使用LangGraph框架重构知识图谱构建系统，将8个步骤封装为独立的Agent/Node，实现：
- 统一的状态管理
- 清晰的工作流程
- 自动反馈循环
- 更好的可维护性和扩展性

### 1.2 当前架构问题
- 步骤之间状态传递不够清晰
- 反馈循环逻辑分散
- 难以追踪整个流程状态
- 错误处理不够统一

---

## 2. LangGraph架构设计

### 2.1 整体流程图

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          Knowledge Graph Pipeline                        │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐                │
│  │   Node 1    │───▶│   Node 2    │───▶│   Node 3    │                │
│  │ Extract L1  │    │ Validate L1 │    │ Extract L1  │                │
│  │             │    │   + Loop    │    │ Prerequisites│               │
│  └─────────────┘    └─────────────┘    └─────────────┘                │
│       │                   │                   │                         │
│       │                   │  (validation     │                         │
│       │                   │   failed?)       │                         │
│       │                   │       │          │                         │
│       │                   │       ▼          │                         │
│       │                   │  ┌────────┐      │                         │
│       │                   │  │ Loop   │      │                         │
│       │                   │  │ Back   │      │                         │
│       │                   │  └────────┘      │                         │
│       │                   │       │          │                         │
│       ▼                   ▼       ▼          ▼                         │
│  ┌─────────────────────────────────────────────────────────────┐        │
│  │                       Node 4                               │        │
│  │              Extract Entities & Relations                  │        │
│  └─────────────────────────────────────────────────────────────┘        │
│       │                                                            │
│       ▼                                                            │
│  ┌─────────────────────────────────────────────────────────────┐        │
│  │                       Node 5                                 │        │
│  │                    Vectorization                            │        │
│  └─────────────────────────────────────────────────────────────┘        │
│       │                                                            │
│       ▼                                                            │
│  ┌─────────────────────────────────────────────────────────────┐        │
│  │                       Node 6                                 │        │
│  │               Data Calibration                              │        │
│  └─────────────────────────────────────────────────────────────┘        │
│       │                                                            │
│       ▼                                                            │
│  ┌─────────────────────────────────────────────────────────────┐        │
│  │                       Node 7                                 │        │
│  │                    LLM Evaluation                           │        │
│  └─────────────────────────────────────────────────────────────┘        │
│       │                                                            │
│       ▼                                                            │
│  ┌─────────────────────────────────────────────────────────────┐        │
│  │                       Node 8                                 │        │
│  │              Build Neo4j Graph                              │        │
│  └─────────────────────────────────────────────────────────────┘        │
│                                                                      │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.2 状态定义 (KnowledgeGraphState)

```python
class KnowledgeGraphState(TypedDict):
    # ==================== 输入 ====================
    toc_files: List[dict]              # TOC文件内容
    textbook_data: List[dict]           # 教材章节数据
    
    # ==================== Step 1: L1提取 ====================
    l1_concepts: List[dict]            # 提取的L1知识点
    l1_extraction_prompt: str          # 使用的提示词
    
    # ==================== Step 2: L1校验 ====================
    validated_l1_concepts: List[dict]   # 校验后的L1知识点
    validation_summary: dict             # 校验摘要
    validation_errors: List[dict]       # 校验失败的知识點
    
    # ==================== Step 3: L1前置关系 ====================
    l1_prerequisites: List[dict]        # L1前置关系
    
    # ==================== Step 4: 实体关系提取 ====================
    knowledge_points: List[dict]        # 所有知识点
    resources: List[dict]              # 资源
    relationships: List[dict]          # 关系
    
    # ==================== Step 5: 向量化 ====================
    vector_db_path: str                # 向量数据库路径
    
    # ==================== Step 6: 数据校准 ====================
    calibrated_kps: List[dict]         # 校准后的知识点
    calibrated_resources: List[dict]    # 校准后的资源
    calibrated_relationships: List[dict] # 校准后的关系
    
    # ==================== Step 7: LLM评测 ====================
    evaluation_report: dict            # 评测报告
    
    # ==================== Step 8: 图谱构建 ====================
    neo4j_status: dict                # Neo4j导入状态
    
    # ==================== 元数据 ====================
    config: dict                       # 配置
    current_step: str                  # 当前步骤
    errors: List[str]                  # 错误列表
    iteration: int                     # 当前迭代次数
```

---

## 3. 节点设计

### 3.1 Node 1: Extract L1 Concepts (L1ExtractorAgent)

**职责**: 从多本教材的章节目录中提取L1知识点

**输入状态**:
- `toc_files`: List[dict]

**输出状态**:
- `l1_concepts`: List[dict]
- `l1_extraction_prompt`: str

**逻辑**:
1. 加载提示词模板 `prompts/L1_Extraction_Prompt.txt`
2. 格式化所有章节列表
3. 调用LLM提取L1知识点
4. 解析JSON响应
5. 保存到 `data/output/l1_concepts.yaml`

**重试策略**: 失败重试3次

---

### 3.2 Node 2: Validate L1 Concepts (L1ValidatorAgent)

**职责**: 校验L1知识点质量，包含反馈循环

**输入状态**:
- `l1_concepts`: List[dict]

**输出状态**:
- `validated_l1_concepts`: List[dict]
- `validation_summary`: dict
- `validation_errors`: List[dict]

**逻辑**:
1. 加载提示词模板 `prompts/L1_Validation_Prompt.txt`
2. 对每个L1知识点调用LLM评估
3. 收集评分和反馈
4. 判断是否通过（总分≥7，每项≥6）
5. 如果有失败项：
   - 收集失败反馈
   - 触发循环（返回Node 1）
6. 保存校验结果

**评估维度**:
| 维度 | 说明 | 阈值 |
|------|------|------|
| 颗粒度 | 同一领域内容 | ≥6 |
| 完整性 | 核心内容覆盖 | ≥6 |
| 认知逻辑性 | 知识递进关系 | ≥6 |
| 学习路径导向 | 里程碑意义 | ≥6 |
| 定义清晰度 | 明确边界 | ≥6 |

**循环条件**: validation_errors > 0 且 iteration < 3

---

### 3.3 Node 3: Extract L1 Prerequisites (L1PrerequisiteAgent)

**职责**: 提取L1知识点之间的前置关系

**输入状态**:
- `validated_l1_concepts`: List[dict]

**输出状态**:
- `l1_prerequisites`: List[dict]

**逻辑**:
1. 加载所有L1知识点
2. 调用LLM分析前置关系
3. 保存到 `data/output/l1_prerequisites.csv`

---

### 3.4 Node 4: Extract Entities & Relations (EntityExtractorAgent)

**职责**: 从教材内容中提取知识点、关系和资源

**输入状态**:
- `validated_l1_concepts`: List[dict]
- `textbook_data`: List[dict]

**输出状态**:
- `knowledge_points`: List[dict]
- `resources`: List[dict]
- `relationships`: List[dict]

**逻辑**:
1. 对每个教材章节调用LLM
2. 提取L2/L3知识点
3. 提取关系（contains, prerequisite, has_resource）
4. 提取资源链接
5. 保存到CSV

---

### 3.5 Node 5: Vectorization (VectorizationAgent)

**职责**: 将知识点向量化并存入向量数据库

**输入状态**:
- `knowledge_points`: List[dict]
- `resources`: List[dict]

**输出状态**:
- `vector_db_path`: str

**逻辑**:
1. 初始化向量数据库
2. 批量向量化实体
3. 存储到LanceDB

---

### 3.6 Node 6: Data Calibration (CalibrationAgent)

**职责**: 数据去重、层级归属、关系验证

**输入状态**:
- `knowledge_points`: List[dict]
- `resources`: List[dict]
- `relationships`: List[dict]
- `l1_prerequisites`: List[dict]

**输出状态**:
- `calibrated_kps`: List[dict]
- `calibrated_resources`: List[dict]
- `calibrated_relationships`: List[dict]

**逻辑**:
1. 字符串相似度去重
2. 语义相似度聚类
3. 层级归属（L2→L1, L3→L2）
4. 整合L1前置关系
5. 关系验证

---

### 3.7 Node 7: LLM Evaluation (EvaluationAgent)

**职责**: 对完整知识图谱进行质量评估

**输入状态**:
- `calibrated_kps`: List[dict]
- `calibrated_resources`: List[dict]
- `calibrated_relationships`: List[dict]

**输出状态**:
- `evaluation_report`: dict

**逻辑**:
1. 收集图谱统计信息
2. 调用LLM进行多维度评估
3. 生成改进建议
4. 保存报告

---

### 3.8 Node 8: Build Neo4j Graph (GraphBuilderAgent)

**职责**: 将知识图谱导入Neo4j

**输入状态**:
- `calibrated_kps`: List[dict]
- `calibrated_resources`: List[dict]
- `calibrated_relationships`: List[dict]

**输出状态**:
- `neo4j_status`: dict

**逻辑**:
1. 连接Neo4j
2. 创建节点和关系
3. 验证导入结果

---

## 4. 条件分支

### 4.1 Validation Loop (验证循环)

```python
def should_rerun_extraction(state: KnowledgeGraphState) -> str:
    """判断是否需要重新提取L1"""
    if state.get('validation_errors'):
        if state.get('iteration', 0) < 3:
            return "extract_l1"
    return "extract_prerequisites"
```

### 4.2 Error Handling (错误处理)

```python
def should_retry(state: KnowledgeGraphState) -> bool:
    """判断是否需要重试"""
    if state.get('errors') and state.get('iteration', 0) < 3:
        return True
    return False
```

---

## 5. 文件结构

```
knowledge_graph/
├── __main__.py                      # 入口
├── langgraph_state.py              # 状态定义
├── langgraph_pipeline.py           # 主流程
├── agents/
│   ├── __init__.py
│   ├── base_agent.py               # 基础Agent类
│   ├── l1_extractor.py             # Node 1
│   ├── l1_validator.py              # Node 2
│   ├── l1_prerequisite.py          # Node 3
│   ├── entity_extractor.py          # Node 4
│   ├── vectorization.py             # Node 5
│   ├── calibration.py               # Node 6
│   ├── evaluation.py                # Node 7
│   └── graph_builder.py            # Node 8
├── utils/
│   └── ...
└── prompts/
    └── ...
```

---

## 6. 使用方式

### 6.1 命令行
```bash
# 运行完整流程
poetry run python -m knowledge_graph

# 运行特定步骤
poetry run python -m knowledge_graph --step 1
poetry run python -m knowledge_graph --step validate_l1
```

### 6.2 Python API
```python
from knowledge_graph.langgraph_pipeline import create_pipeline

# 创建pipeline
graph = create_pipeline()

# 运行
result = graph.invoke({
    "toc_files": [...],
    "textbook_data": [...],
    "config": {...}
})

# 查看结果
print(result["validated_l1_concepts"])
print(result["evaluation_report"])
```

---

## 7. 待定问题

### 已确定
- **状态持久化**: 文件持久化（每个Node执行后保存状态，支持断点续跑）
- **错误策略**: 快速失败（一个Node失败则停止）
- **验证循环**: 最多3次

### 实现注意事项
- 步骤二L1验证不通过 → 返回步骤一重新提取 → 再次验证 → 直至通过或达到最大循环次数 → 进入下一流程

---

## 8. 实现计划

| 阶段 | 任务 | 预估工作量 |
|------|------|------------|
| Phase 1 | 基础框架 + 状态定义 | 1小时 |
| Phase 2 | Node 1-3 实现 | 2小时 |
| Phase 3 | Node 4-6 实现 | 2小时 |
| Phase 4 | Node 7-8 实现 | 1小时 |
| Phase 5 | 测试和调试 | 2小时 |

---

## 9. 文档更新记录

| 日期 | 更新内容 | 更新人 |
|------|----------|--------|
| 2026-03-10 | 初始版本 | AI |
| 2026-03-10 | 添加Phase 1-2实现（Agent基类、L1提取器、验证器、循环逻辑） | AI |
| 2026-03-10 | 完成所有8个Node实现 + 完整Pipeline | AI |
