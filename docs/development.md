# Knowledge Graph Builder - 开发指南

## 项目简介

这是一个面向教育与学习场景的知识图谱构建系统。

## 本地开发

### 1. 克隆项目

```bash
git clone https://github.com/wzm110/knowledge-graph.git
cd knowledge-graph
```

### 2. 安装依赖

```bash
# 使用 Poetry（推荐）
poetry install

# 或使用 pip
pip install -r requirements.txt
```

### 3. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 填入你的 API Key
```

### 4. 启动 Neo4j

确保 Neo4j 5.x 已启动，或使用 Docker：

```bash
docker run -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=neo4j/your-password neo4j:5
```

### 5. 运行项目

```bash
poetry run python -m knowledge_graph
```

## 项目结构

```
knowledge-graph/
├── config/              # 配置文件
├── data/
│   ├── input/          # 输入教材数据
│   └── output/         # 输出的图谱数据
├── docs/               # 文档
├── examples/           # 示例代码
├── knowledge_graph/    # 主包
│   ├── steps/         # 处理步骤
│   └── utils/         # 工具模块
├── tests/             # 测试
└── prompts/           # LLM 提示词
```

## 核心模块

- `knowledge_graph/steps/extract.py`: 实体关系抽取
- `knowledge_graph/steps/calibrate.py`: 数据校准
- `knowledge_graph/steps/build.py`: 图谱构建
- `knowledge_graph/utils/`: 工具模块

## 测试

```bash
poetry run pytest tests/
```

## 代码规范

- 使用 Ruff 进行代码检查
- 使用 MyPy 进行类型检查
- 遵循 PEP 8 规范
