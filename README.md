# Knowledge Graph Builder

[English](./README.md) | [中文](./README_zh.md)

<div align="center">

![Knowledge Graph Builder](./docs/logo.svg)

[![Python Version](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](./LICENSE)
[![GitHub Stars](https://img.shields.io/github/stars/wzm110/knowledge-graph?style=social)](https://github.com/wzm110/knowledge-graph)

A knowledge graph construction system for education and learning scenarios. It supports multiple textbooks, prerequisite relationship inference, and learning path planning.

</div>

## Architecture

![Architecture](./docs/architecture.svg)

## Graph Database Schema

![Micro Node Schema](./docs/images/微观节点.png)

## Project Goal

In real teaching and learning processes, the same subject typically has various textbooks, courses, and teaching resources. Different textbooks have significant differences in chapter division, knowledge point sequence, and depth of explanation. However, what learners really need to master is the stable knowledge system, not the chapter structure of a specific textbook.

The core business goals of this system are:
- Decouple textbook structure from knowledge ontology to build a unified knowledge base
- Support intelligent learning and teaching applications
- Enable prerequisite relationship inference and learning path planning

## Features

- **Multi-textbook Support**: Decouples textbook structure from knowledge ontology
- **Hierarchical Knowledge Points**: L1 (top-level), L2, L3 (detailed) concept system
- **Prerequisite Inference**: Automatically infer learning prerequisite relationships using LLM
- **Learning Path Planning**: Build personalized learning paths based on knowledge graphs
- **Neo4j Integration**: Store and query knowledge graphs in Neo4j
- **Vector Similarity**: Support semantic similarity search using vector databases

## Build Pipeline

```
┌─────────────────────────────────────────────────────────────────────┐
│                     Knowledge Graph Build Pipeline                   │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────┐       │
│  │  Step 1     │     │  Step 1.5    │     │  Step 2      │       │
│  │  Extract L1  │ ──→ │  Validate   │ ──→ │  Extract     │       │
│  │              │     │  L1 (Opt)   │     │  Entities    │       │
│  └──────────────┘     └──────────────┘     └──────────────┘       │
│         │                                        │                  │
│         │                                        ▼                  │
│         │              ┌──────────────┐     ┌──────────────┐       │
│         │              │  Step 3      │     │  Step 4      │       │
│         │              │  Vectorize   │ ──→ │  Calibrate   │       │
│         │              └──────────────┘     └──────────────┘       │
│         │                    │                    │                  │
│         │                    └────────────┬───────┘                  │
│         │                             ▼                          │
│         │              ┌──────────────────────────────┐            │
│         │              │     Step 5: Graph Update   │            │
│         │              │  (Update Vector DB + Neo4j)│            │
│         │              └──────────────────────────────┘            │
│         │                             │                            │
│         └─────────────────────────────┘                            │
│                              ▼                                      │
│              ┌──────────────────────────────┐                     │
│              │       Step 6: Query          │                     │
│              │  (Vector Search + Neo4j)    │                     │
│              └──────────────────────────────┘                     │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### Step Details

1. **Step 1: Extract L1 Concepts**
   - Input: Table of contents from multiple textbooks
     - `data/input/动手学深度学习_章节目录.txt`
     - `data/input/深度学习DeepLearning_章节目录.txt`
     - `data/input/神经网络与深度学习_章节目录.txt`
   - Extract unified top-level knowledge points (L1 concepts) from multiple textbook TOCs using LLM
   - Output: L1 concepts list (unified knowledge system)

2. **Step 1.5: L1 Concept Validation (Optional)**
   - Input: L1 concepts list from Step 1
   - Use LLM to evaluate and score each L1 concept
   - Output: L1 concepts with scores and feedback

3. **Step 2: Extract Entities & Relations**
   - Input: Chunked CSV textbook data
   - Extract knowledge points (L2, L3), relationships, and resources
   - Output: Entities, Relations, Resources

4. **Step 3: Vectorization**
   - Vectorize extracted entities
   - Store in vector database

5. **Step 4: Data Calibration**
   - Deduplication, hierarchy assignment, validation

6. **Step 5: Graph Update**
   - Update vector database
   - Import to Neo4j

## Quick Start

### Prerequisites

- Python 3.10+
- Neo4j 5.x
- OpenAI API Key (or compatible API)

### Installation

```bash
# Clone repository
git clone https://github.com/wzm110/knowledge-graph.git
cd knowledge-graph

# Install dependencies
poetry install

# Copy environment configuration
cp .env.example .env
# Edit .env with your API Key
```

### Usage

```bash
# Full pipeline
poetry run python -m knowledge_graph

# Step by step
poetry run python -m knowledge_graph extract_l1     # Step 1: Extract L1
poetry run python -m knowledge_graph validate_l1    # Step 1.5: Validate L1 (Optional)
poetry run python -m knowledge_graph extract       # Step 2: Extract entities
poetry run python -m knowledge_graph calibrate     # Step 3-4: Calibration
poetry run python -m knowledge_graph build         # Step 5: Graph build
```

## Project Structure

```
knowledge-graph/
├── config/                    # Configuration files
├── data/
│   └── input/               # Input textbook data
│       ├── *_目录.txt        # Textbook table of contents (multiple)
│       └── *.csv            # Chunked textbook content
├── docs/                     # Documentation & images
├── knowledge_graph/          # Main package
│   ├── steps/              # Processing steps
│   │   ├── extract_l1.py   # Step 1: Extract L1
│   │   ├── extract.py       # Step 2: Extract entities
│   │   ├── calibrate.py     # Step 3-4: Calibration
│   │   └── build.py         # Step 5: Graph build
│   └── utils/              # Utilities
├── tests/                   # Tests
└── prompts/                 # LLM prompts
```

## Knowledge Hierarchy

| Level | Description | Example |
|-------|-------------|---------|
| L1 | Top-level concepts | Neural Network Basics, CNN |
| L2 | Sub-concepts | Backpropagation, Activation Functions |
| L3 | Detailed points | Sigmoid Gradient Computation |

## Relationship Types

| Type | Description |
|------|-------------|
| `contains` | Hierarchy (L1→L2→L3) |
| `prerequisite` | Learning prerequisites |
| `has_resource` | Linked resources |

## Data

The textbook data included in this project is **sample data** from [D2L (Dive into Deep Learning)](https://d2l.ai/).

## License

MIT License - see [LICENSE](./LICENSE) for details.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## Acknowledgments

- [D2L (Dive into Deep Learning)](https://d2l.ai/) - Sample textbook data
- [OpenAI](https://openai.com/) - LLM API
- [Neo4j](https://neo4j.com/) - Graph database
