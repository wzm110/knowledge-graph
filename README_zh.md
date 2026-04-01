## Knowledge Graph Builder（知识图谱构建系统）

把“教材章节数据（CSV）+ 目录（TOC）”变成**可评测、可微调、可入库（Neo4j）**的课程知识图谱流水线。

<div align="left">
  <a href="./LICENSE">
    <img alt="License" src="https://img.shields.io/badge/license-MIT-blue">
  </a>
  <a href="./pyproject.toml">
    <img alt="Python" src="https://img.shields.io/badge/python-3.10%2B-blue">
  </a>
  <a href="./CHANGELOG.md">
    <img alt="Changelog" src="https://img.shields.io/badge/changelog-Keep%20a%20Changelog-brightgreen">
  </a>
</div>

### 一张图看懂全流程

![知识图谱构建流水线架构图](docs/architecture.png)

### 可交互预览（GitHub Pages）

README 里不能运行 JS，所以完整版交互放在 GitHub Pages。启用后点击下图进入 Demo：

[![Interactive Matrix Demo](docs/architecture.png)](docs/index.html)

---

## Overview（这项目能做什么）

你会得到：

- **知识图谱数据**：L1/L2/L3/L4 知识点 + `contains` / `prerequisite` 等关系
- **评测报告（可追溯）**：每次评测都有 `run_id` 归档，并输出簇级报告（`clusters/*.md`）
- **微调闭环**：基于评测建议执行 **MERGE / ADD / DELETE**，并带回滚保护
- **Neo4j 入库（可选）**：当前默认只入库“知识点图”（过滤 `has_resource`）

---

## Quickstart（3 分钟跑起来）

⚠️ **提醒**：LLM 抽取/评测/微调可能有成本，请先用小数据验证，再扩大规模。

### 1) 环境要求

- Python **3.10+**
- （可选）Neo4j **5.x**（仅 Step 8 需要）

### 2) 安装依赖（Poetry）

```bash
poetry install
```

### 3) 准备配置（本地配置不提交）

本仓库默认读取 `config/default.yaml`（`knowledge_graph/utils/config.py`）。  
推荐做法：

- 复制示例：`config/default.example.yaml` → `config/default.yaml`
- 在本地 `config/default.yaml` 填入你自己的 `api_key / api_base / model`
- **不要提交 `config/`**（仓库已在 `.gitignore` 忽略 `config/`）

### 4) 一键跑全流程

```bash
poetry run python -m knowledge_graph.pipeline
```

等价入口（你也可以用这个）：

```bash
poetry run python -m knowledge_graph
```

---

## 启用 GitHub Pages（让 Demo 真正可交互）

1. GitHub 仓库 → **Settings** → **Pages**
2. **Build and deployment**
   - Source 选 **Deploy from a branch**
   - Branch 选 **main**，Folder 选 **/docs**
3. 保存后等待 1-2 分钟，访问你的 Pages 地址：
   - `https://<你的用户名>.github.io/<仓库名>/`

---

## 常用命令（Copy & Paste）

### 只跑某一步（调试专用）

`step` 是位置参数（见 `knowledge_graph/__main__.py`）：

- `extract_l1|validate_l1|extract_l1_rels|extract|vectorize|calibrate|evaluate|build`

示例：

```bash
poetry run python -m knowledge_graph extract
poetry run python -m knowledge_graph evaluate
poetry run python -m knowledge_graph build
```

### 两个最常用的循环开关

```bash
# L1 提取↔验证最大循环次数（默认 3）
poetry run python -m knowledge_graph full --max-loops 3

# 评测↔微调最大循环次数（默认 5）
poetry run python -m knowledge_graph full --max-eval-loops 2
```

### 增量模式（只处理新增输入文件）

```bash
poetry run python -m knowledge_graph full --incremental
```

---

## 输出产物（去哪看结果）

- `data/output/stage1_entities.parquet`：Step 1–2
- `data/output/stage2_relationships.parquet`：Step 3
- `data/output/stage3_{entities,relationships,resources}.parquet`：Step 4
- `data/output/calibrated_{entities,relationships}.parquet`：Step 6（随后 6.5 / 7.5 可能覆盖更新）
- `data/output/evaluation/<run_id>/*` + `data/output/evaluation/latest.json`：Step 7
- `data/output/final_evaluation/**`：最新评估同步输出（含 `clusters/*.md`）

---

## 仓库指引（读文档的正确方式）

- 流程总览与循环：`docs/项目流程/00_总体说明与全架构图.md`
- 细节级对齐代码：`docs/项目流程/11_全流程细节级实现说明.md`
- 文档与代码对照：`docs/文档与代码对照表.md`
- 本地开发指南：`docs/development.md`

---

## 重要边界（最容易误解的点）

- Step 5 向量化：当前只向量化**知识点**（资源不参与）
- Step 7 评测：会过滤 `has_resource`（资源不参与评测）
- Step 8 入库：会过滤 `has_resource`（当前只入库知识点图）

---

## FAQ（常见问题）

### 为什么我看不到 resources 入库或参与评测？

当前实现中：

- Step4 会落盘 `stage3_resources.parquet`
- 但 Step7/Step8 会过滤 `has_resource`，只处理知识点图（见 `knowledge_graph/agents/evaluation.py`、`knowledge_graph/agents/graph_builder.py`）

---

## 功能特性

### 🚀 核心能力

- **L1 知识点提取 + 验证回环**：从 TOC/章节信息抽取 L1，并可多轮迭代修正（`--max-loops`）
- **L1 前置关系**：在 L1 粒度上推断学习依赖关系
- **实体与关系抽取**：从教材章节抽取 L2/L3、关系与资源（资源单独落盘）
- **向量检索底座**：将知识点写入向量库，支持后续语义检索（当前仅向量化知识点）
- **校准与清洗**：去重、层级归属、关系合法性校验，输出可评测/可入库基线
- **评测 + 微调闭环**：产出可执行建议并落盘归档，微调支持 **MERGE/ADD/DELETE**
- **Neo4j 图谱**：将最终知识点图写入 Neo4j（当前过滤 `has_resource`）

### ⚡ 工程体验

- **可追溯评测产物**：每次评测都有 `run_id` 目录归档 + `final_evaluation/**` 最新同步
- **增量处理**：只处理新增输入文件（依赖 `data/processed_files.json`）
- **分阶段 Parquet 产物**：便于断点调试与定位问题

---

## 项目结构（融合旧版 README）

```text
graph/
├── config/                 # 本地配置（仓库默认忽略，不提交）
├── data/
│   ├── input/              # 输入（教材 csv、TOC 等）
│   └── output/             # 输出（parquet、评测归档等，已忽略不提交）
├── docs/                   # 文档 + GitHub Pages Demo（/docs）
├── prompts/                # 提示词
├── knowledge_graph/
│   ├── __main__.py         # CLI 入口（单步/参数）
│   ├── pipeline.py         # 主流程与循环控制
│   ├── agents/             # 各步骤 Agent（1-8 + 6.5 + 7.5）
│   └── utils/              # 配置/日志/LLM/向量库工具
└── tests/                  # 测试
```

---

## 数据流（融合旧版 README，按当前实现对齐）

```text
输入数据
  │
  ├─→ data/input/Table_of_Contents/*.txt   # 目录（TOC）
  └─→ data/input/*.csv                    # 章节内容（排除 *目录.csv）
          │
          ▼
Step 1–2: L1 提取 + 验证回环
          │
          ▼ data/output/stage1_entities.parquet
Step 3: L1 前置关系
          │
          ▼ data/output/stage2_relationships.parquet
Step 4: 实体/关系/资源抽取（L2/L3）
          │
          ▼ data/output/stage3_{entities,relationships,resources}.parquet
Step 5–6: 向量化（仅知识点） + 校准（去重/层级/关系校验）
          │
          ▼ data/output/calibrated_{entities,relationships}.parquet
Step 6.5: 重聚合（按 L1 聚合 L2，下沉 L2→L3、L3→L4）
          │
Step 7 ↔ 7.5: 评测 ↔ 微调（MERGE/ADD/DELETE）
          │
Step 8: Neo4j 入库（知识点图，过滤 has_resource）
```

---

## 本次更新说明（你会感知到的变化）

- **README 更可上手**：补齐 GitHub Pages 交互 Demo（README 预览 + /docs 站点）
- **新增示例配置**：`config/default.example.yaml`（不含密钥，逐项注释），本地复制为 `config/default.yaml` 使用
- **文档全面对齐代码**：`docs/**` 中 6.5/7.5、评测产物路径、资源边界等与实际实现保持一致

