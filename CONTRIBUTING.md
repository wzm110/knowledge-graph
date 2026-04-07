# 参与贡献

感谢你愿意改进本仓库。以下为克隆后的最小闭环与约定。

## 环境与安装

- Python **3.10+**（与 CI 一致）
- [Poetry](https://python-poetry.org/) 管理依赖

```bash
git clone https://github.com/wzm110/knowledge-graph.git
cd knowledge-graph
poetry install
cp config/default.example.yaml config/default.yaml
# 编辑 config/default.yaml 或使用环境变量占位（见示例文件注释）
```

## 提交前自检（与 CI 对齐）

```bash
poetry run ruff check .
poetry run mypy knowledge_graph
poetry run pytest tests/
```

## 代码与文档

- 行为或 CLI 变更时，请同步更新 `docs/文档与代码对照表.md` 与相关 `README*.md`。
- 避免提交密钥：`config/default.yaml` 与 `.env` 已被忽略；仅 `config/default.example.yaml` 可作为无密钥模板提交。

## 可选维护脚本

- `knowledge_graph/tools/` 下为一次性数据清理等脚本，默认不参与主流程；使用前请阅读文件内说明。

## Pull Request

- 在 PR 描述中说明**动机**、**主要改动**与**如何验证**（例如跑过的命令）。
- 若涉及破坏性 CLI 或产物路径变更，请在 `CHANGELOG.md` 的未发布小节或新版本下补充说明。
