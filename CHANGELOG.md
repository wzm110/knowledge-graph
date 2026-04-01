# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.1] - 2026-04-01

### Changed
- 文档与当前实现对齐（`docs/**` + 根部 README/CHANGELOG），补齐 6.5/7.5，并纠正若干易误导边界与产物路径。
- 微调能力对齐为 **MERGE/ADD/DELETE**，动作顺序为 **MERGE → ADD → DELETE**（见 `knowledge_graph/agents/refinement.py`）。
- 评测产物对齐为 `data/output/evaluation/<run_id>/*` + `data/output/evaluation/latest.json`，并同步输出到 `data/output/final_evaluation/**`（见 `knowledge_graph/agents/evaluation.py`）。
- 资源边界说明对齐：评测与 Neo4j 入库阶段会过滤 `has_resource`（见 `knowledge_graph/agents/evaluation.py`、`knowledge_graph/agents/graph_builder.py`）。
- `--max-eval-loops` 默认值对齐为 **5**（见 `knowledge_graph/pipeline.py`、`knowledge_graph/__main__.py`）。

## [1.0.0] - 2026-03-10

### ⚡ Breaking Changes
- 重新设计完整流水线架构，从头构建

### Added
#### 核心功能
- **8步LangGraph风格流水线**
  - Node 1: L1知识点提取
  - Node 2: L1验证（带反馈循环）
  - Node 3: L1前置关系提取
  - Node 4: 实体关系提取（L2/L3）
  - Node 5: 向量化
  - Node 6: 数据校准
  - Node 7: LLM评测
  - Node 8: Neo4j图谱构建

- **L1知识点智能验证**
  - 基于反馈循环的验证机制
  - 整体评估模式（而非单个知识点）
  - 科目背景支持（可配置）
  - 大局观评估原则

- **实体关系提取**
  - L2子概念提取
  - L3技能提取
  - Resource资源提取
  - contains/prerequisite/has_resource关系

#### 性能优化
- **LLM缓存机制**
  - 基于MD5的缓存key
  - 相同输入自动复用结果
  - 支持断点恢复

- **进度条显示**
  - 使用tqdm显示处理进度

- **Parquet存储**
  - 高效列式存储格式
  - 分阶段中间文件
  - 支持单独调试数据校准

#### 本地化
- 全中文日志输出
- 中文提示词模板

### Changed
- 提示词模板全面优化
- Agent基类重构
- 数据流程重新设计

### Fixed
- 验证反馈提示词bug（{all_chapters}未替换）
- 整体评估改为从配置文件读取科目

### 主命令与步骤选项

运行入口：

```bash
python -m knowledge_graph [step] [选项...]
```

- **`step`（位置参数，可省略）**：
  - `full`（默认）: 跑完整的 8 步流水线（带 L1 验证循环 + 评估/微调循环）。
  - `extract_l1`: 只跑步骤 1，提取 L1 知识点。
  - `validate_l1`: 只跑步骤 2，验证 L1 知识点。
  - `extract_l1_rels`: 只跑步骤 3，抽取 L1 前置关系。
  - `extract`: 只跑步骤 4，抽取实体与关系。
  - `vectorize`: 只跑步骤 5，向量化。
  - `calibrate`: 只跑步骤 6，校准实体与关系。
  - `evaluate`: 只跑步骤 7，LLM 评测。
  - `build`: 只跑步骤 8，写入 Neo4j。

### 通用选项

- **`--test`**  
  - 开启测试模式：用于快速验证。
  - 效果：
    - 实体抽取时只处理少量章节（由内部 `_max_chapters` 控制，默认 2）。
    - 日志会提示「测试模式：仅处理 N 个章节」。

- **`--max-loops INT`**  
  - 控制 **L1 抽取+验证阶段** 的最大循环次数（默认 3）。
  - 评估逻辑：
    - 每次：`extract_l1` → `validate_l1`。
    - 若 `validation_errors` 非空且未达上限，则再迭代一轮；
    - 达到上限仍不过，就带着问题继续后续步骤。

- **`--max-eval-loops INT`**  
  - 控制 **评估+微调循环（步骤 7 + 7.5）** 的最大次数（默认 5）。
  - 每轮是：`evaluate` → `tune_graph` → 再 evaluate，直到：
    - 通过（`is_passed=True`），或
    - 达到最大评估轮次。

- **`--full-refresh-l1`**（你刚让加的安全开关）  
  - 默认行为：  
    - 如果存在 `data/output/stage1_entities.parquet`，**会跳过 L1 抽取+验证（步骤 1–2）**，直接从步骤 3 开始，避免误覆盖已有 L1。
  - 加上 `--full-refresh-l1` 时：  
    - 强制 **全量重跑 L1 抽取和验证**，即使已有 `stage1_entities.parquet` 也不会跳过。
  - 推荐用法：
    - 日常调试后半段流程（重跑校准、评估、微调）时：  
      `python -m knowledge_graph full`（保留现有 L1，不重抽）。
    - 需要彻底重设计 L1 结构时：  
      `python -m knowledge_graph full --full-refresh-l1`。