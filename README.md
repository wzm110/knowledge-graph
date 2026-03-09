# Knowledge Graph Builder

English | [中文](./README_zh.md)

A knowledge graph construction system for education and learning scenarios. It supports multiple textbooks, prerequisite relationship inference, and learning path planning.

## Features

- **Multi-textbook Support**: Decouples textbook structure from knowledge ontology
- **Hierarchical Knowledge Points**: L1 (top-level), L2, L3 (detailed) concepts
- **Prerequisite Inference**: Automatically infer learning prerequisite relationships using LLM
- **Learning Path Planning**: Build personalized learning paths based on knowledge graphs
- **Neo4j Integration**: Store and query knowledge graphs in Neo4j
- **Vector Similarity**: Support semantic similarity search using vector databases

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Knowledge Graph Builder                   │
├─────────────────────────────────────────────────────────────┤
│  Input (Textbooks)                                         │
│    ↓                                                       │
│  ┌─────────────────┐    ┌─────────────────┐                │
│  │  LLM Extraction │ → │  Data Calibration│                │
│  │  (Entities/     │    │  (Deduplication,│                │
│  │   Relations)    │    │   Hierarchy)     │                │
│  └─────────────────┘    └─────────────────┘                │
│    ↓                                                       │
│  ┌─────────────────┐    ┌─────────────────┐                │
│  │ L1 Prerequisite │ → │  Neo4j Storage │                │
│  │    Inference    │    │                 │                │
│  └─────────────────┘    └─────────────────┘                │
└─────────────────────────────────────────────────────────────┘
```

## Installation

### Prerequisites

- Python 3.10+
- Neo4j 5.x
- OpenAI API Key (or compatible API)

### Using Poetry (Recommended)

```bash
# Clone the repository
git clone https://github.com/wzm110/knowledge-graph.git
cd knowledge-graph

# Install dependencies
poetry install

# Activate virtual environment
poetry shell
```

### Using pip

```bash
pip install -r requirements.txt
```

## Configuration

Edit `config/default.yaml`:

```yaml
models:
  default_chat_model:
    api_key: your-api-key
    model: qwen3-max
    api_base: https://dashscope.aliyuncs.com/compatible-mode/v1

neo4j:
  uri: neo4j://127.0.0.1:7687
  user: neo4j
  password: your-password
  database: knowledge-graph
```

## Usage

### Build Knowledge Graph

```bash
poetry run kg-build
```

### Query Knowledge Graph

```python
from knowledge_graph.utils.vector_db import VectorDBManager
from knowledge_graph.steps.build import query_graph

# Query similar concepts
results = query_graph("神经网络", top_k=5)
```

## Project Structure

```
knowledge-graph/
├── config/              # Configuration files
├── data/               # Data directory
│   ├── input/         # Input textbooks
│   └── output/        # Generated graphs
├── docs/              # Documentation
├── examples/          # Example scripts
├── knowledge_graph/   # Main package
│   ├── steps/        # Processing steps
│   └── utils/        # Utilities
├── tests/             # Test suite
└── prompts/          # LLM prompts
```

## Knowledge Hierarchy

- **L1**: Top-level concepts (e.g., "Neural Network Basics", "Convolutional Neural Networks")
- **L2**: Sub-concepts (e.g., "Backpropagation", "Activation Functions")
- **L3**: Detailed knowledge points (e.g., "Sigmoid Gradient Computation")

## Relationship Types

- **contains**: Hierarchical containment (L1→L2→L3)
- **prerequisite**: Learning prerequisite relationships
- **has_resource**: Associated learning resources

## Data

The textbook data included in this project is **sample data** from [D2L (Dive into Deep Learning)](https://d2l.ai/).

To use your own textbook data, place CSV files in `data/input/` with the following format:

```csv
title,text,lecture_link,ppt_link,code_link,video_link
Chapter Title,Chapter Content,Video Link,PPT Link,Code Link,Video Link
```

## License

MIT License - see [LICENSE](./LICENSE) for details.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## Acknowledgments

- [D2L (Dive into Deep Learning)](https://d2l.ai/) - Textbook data source
- [OpenAI](https://openai.com/) - LLM API
- [Neo4j](https://neo4j.com/) - Graph database
