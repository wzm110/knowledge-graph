# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
