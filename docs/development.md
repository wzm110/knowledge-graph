# Knowledge Graph Builder - 开发指南（代码对齐版）

本文档面向**本仓库当前实现**，用于本地开发/调试/验收。  
运行入口与流程以 `knowledge_graph/__main__.py`、`knowledge_graph/pipeline.py` 为准。

## 环境要求

- Python：**3.10+**（见 `pyproject.toml`）
- Neo4j：**5.x**（用于步骤8入库；不需要 Neo4j 也可跑到步骤7/7.5）

## 1. 安装依赖（Poetry）

本仓库使用 `pyproject.toml`（Poetry）管理依赖。

```bash
poetry install
```

## 2. 配置（config/default.yaml + 环境变量展开）

系统会从 `config/default.yaml` 加载配置（`knowledge_graph/utils/config.py`），并支持在 YAML 中使用环境变量占位：

- `${VAR}`：读取环境变量 `VAR`
- `${VAR:-default}`：没有设置时使用默认值

你需要关注的核心配置通常包括：

- **LLM**：`models.default_chat_model.api_key / api_base / model`（见 `knowledge_graph/utils/llm.py`）
- **Neo4j**：`neo4j.uri / user / password / database`（见 `knowledge_graph/agents/graph_builder.py`）

Windows（PowerShell）示例（仅示意，具体变量名以你的 `config/default.yaml` 为准）：

```powershell
$env:OPENAI_API_KEY="..."
```

## 3. 启动 Neo4j（可选）

确保 Neo4j 5.x 已启动，或用 Docker：

```bash
docker run -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=neo4j/your-password neo4j:5
```

## 4. 运行方式（CLI 入口）

### 4.1 跑全流程

```bash
poetry run python -m knowledge_graph
```

### 4.2 常用参数

```bash
# 控制 L1 提取↔验证最大循环次数（默认 3）
poetry run python -m knowledge_graph full --max-loops 3

# 控制 评测↔微调 最大循环次数（默认 5）
poetry run python -m knowledge_graph full --max-eval-loops 2

# 增量模式：仅处理新增输入文件（依赖 data/processed_files.json）
poetry run python -m knowledge_graph full --incremental

# 强制重跑步骤 1-2（否则可能复用 data/output/stage1_entities.parquet 并跳过）
poetry run python -m knowledge_graph full --full-refresh-l1
```

### 4.3 单步执行（用于调试某一步）

`step` 是位置参数（见 `knowledge_graph/__main__.py`），可取：

- `extract_l1|validate_l1|extract_l1_rels|extract|vectorize|calibrate|evaluate|build`

例如：

```bash
poetry run python -m knowledge_graph extract
poetry run python -m knowledge_graph evaluate
poetry run python -m knowledge_graph build
```

## 5. 项目结构（当前实现）

```
graph/
├── config/                 # 配置（default.yaml）
├── data/
│   ├── input/              # 输入（教材 csv、TOC 等）
│   └── output/             # 输出（parquet、评测归档等）
├── docs/                   # 文档
├── prompts/                # 提示词
├── knowledge_graph/
│   ├── __main__.py         # CLI 入口
│   ├── pipeline.py         # 主流程与循环控制
│   ├── agents/             # 各步骤 Agent（1-8 + 6.5 + 7.5）
│   └── utils/              # 配置/日志/LLM/向量库工具
└── tests/                  # 测试
```

## 6. 输出产物定位（调试必看）

- `data/output/stage1_entities.parquet`：步骤1-2（L1提取与验证）
- `data/output/stage2_relationships.parquet`：步骤3（L1前置关系）
- `data/output/stage3_*.parquet`：步骤4（实体/关系/资源抽取）
- `data/output/calibrated_*.parquet`：步骤6（校准；随后 6.5/7.5 可能覆盖更新）
- `data/output/evaluation/<run_id>/*` + `data/output/evaluation/latest.json`：步骤7评测归档
- `data/output/final_evaluation/**`：最新评测同步输出（含 `clusters/*.md`）

## 7. 测试

```bash
poetry run pytest tests/
```

## 8. 代码规范（工具链）

依赖与工具配置见 `pyproject.toml`：

- Ruff（lint）
- Black（format）
- MyPy（类型检查）
