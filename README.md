# Knowledge Graph Builder

[English](./README.md) | [中文](./README_zh.md)

A knowledge graph construction system for education and learning scenarios. It supports multiple textbooks, prerequisite relationship inference, and learning path planning.

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
- **Vector Query**: Enable semantic similarity search through vector database

## Build Pipeline

```
┌─────────────────────────────────────────────────────────────────────┐
│                     Knowledge Graph Build Pipeline                   │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────┐       │
│  │  Step 1      │     │  Step 2       │     │  Step 3      │       │
│  │  Extract L1  │ ──→ │  Extract      │ ──→ │  Vectorize   │       │
│  │  (TOC Data)  │     │  Entities     │     │              │       │
│  └──────────────┘     └──────────────┘     └──────────────┘       │
│         │                    │                    │                  │
│         ↓                    ↓                    ↓                  │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                    Step 4: Calibration                      │   │
│  │         (Deduplication, Hierarchy, Merge, Validation)         │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                              │                                      │
│                              ↓                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                    Step 5: Graph Update                     │   │
│  │              (Update Vector DB + Import Neo4j)              │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                              │                                      │
│                              ↓                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                    Step 6: Query                             │   │
│  │         (Vector Semantic Search + Neo4j Query)              │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### Step Details

1. **Step 1: Extract L1 Concepts**
   - Input: Table of Contents data (`目录.csv`)
   - Extract top-level knowledge points (L1 concepts) from TOC using LLM
   - Output: L1 concepts list (`l1_concepts.yaml`)

2. **Step 2: Extract Entities & Relations**
   - Input: Chunked CSV textbook data
   - Extract from textbook content:
     - Knowledge points (L2, L3)
     - Relationships (contains, prerequisite)
     - Associated learning resources
   - Output: Entities list, Relations list, Resources list

3. **Step 3: Vectorization**
   - Vectorize extracted entities
   - Store in vector database (for semantic similarity search)

4. **Step 4: Data Calibration**
   - Entity deduplication (string similarity + semantic similarity)
   - Hierarchy assignment (L2→L1, L3→L2)
   - Entity merge and alias integration
   - Relationship validation and filtering

5. **Step 5: Graph Update**
   - Update vector database
   - Import to Neo4j graph database

6. **Step 6: Query**
   - Vector semantic search (similar concept recommendation)
   - Neo4j graph query (path analysis, learning path planning)

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

### Configuration

Edit `config/default.yaml` or set environment variables:

```bash
# Environment variables (recommended)
export OPENAI_API_KEY=your-api-key
export NEO4J_PASSWORD=your-password
```

### Usage

```bash
# Full pipeline (Step 1-6)
poetry run python -m knowledge_graph

# Or run step by step
poetry run python -m knowledge_graph steps.extract_l1    # Step 1
poetry run python -m knowledge_graph steps.extract       # Step 2
poetry run python -m knowledge_graph steps.calibrate      # Step 3-4
poetry run python -m knowledge_graph steps.build         # Step 5-6
```

### Query

```python
from knowledge_graph.utils.vector_db import VectorDBManager
from knowledge_graph.utils.neo4j_client import Neo4jClient

# Vector semantic search
vector_db = VectorDBManager(config)
results = vector_db.find_similar_entities("Neural Network", top_k=5)

# Neo4j graph query
neo4j = Neo4jClient(config)
results = neo4j.query("MATCH (k {name: 'Neural Network Basics'})-[r]->(n) RETURN k, r, n")
```

## Project Structure

```
knowledge-graph/
├── config/                    # Configuration files
├── data/
│   └── input/               # Input textbook data
│       ├── 目录.csv          # Table of contents
│       └── *.csv            # Chunked textbook content
├── docs/                     # Documentation
├── knowledge_graph/          # Main package
│   ├── steps/              # Processing steps
│   │   ├── extract_l1.py   # Step 1: Extract L1
│   │   ├── extract.py       # Step 2: Extract entities
│   │   ├── calibrate.py     # Step 3-4: Calibration
│   │   └── build.py        # Step 5-6: Graph build
│   └── utils/              # Utilities
├── tests/                   # Tests
└── prompts/                 # LLM prompts
```

## Data Format

### Input Data

**TOC Data** (`目录.csv`):
```csv
title,text
目录," 2. 预备知识 
     2.1. 数据操作 
     2.2. 数据预处理 
     ..."
```

**Textbook Content** (`*.csv`):
```csv
title,text,lecture_link,ppt_link,code_link,video_link
Chapter Title,Chapter Content,Video Link,PPT Link,Code Link,Video Link
```

### Output Data

- `data/output/l1_concepts.yaml`: L1 concepts definition
- `data/output/entities.csv`: All entities
- `data/output/relationships.csv`: All relationships
- `data/output/calibrated_entities.csv`: Calibrated entities
- `data/output/calibrated_relationships.csv`: Calibrated relationships

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

To use your own textbook data, place CSV files in `data/input/`.

## License

MIT License - see [LICENSE](./LICENSE) for details.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## Acknowledgments

- [D2L (Dive into Deep Learning)](https://d2l.ai/) - Sample textbook data
- [OpenAI](https://openai.com/) - LLM API
- [Neo4j](https://neo4j.com/) - Graph database
