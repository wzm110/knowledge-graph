"""
Knowledge Graph Builder using LangGraph
Each step is encapsulated as a node/agent with unified state management
"""

from typing import TypedDict, List, Optional
from langgraph.graph import StateGraph, END
from pydantic import BaseModel, Field

from knowledge_graph.utils.llm import call_llm
from knowledge_graph.utils.logger import get_logger

logger = get_logger(__name__)


class KnowledgeGraphState(TypedDict):
    """Unified state for the knowledge graph building pipeline."""
    # Input
    toc_files: List[dict]
    textbook_data: List[dict]
    
    # Step 1: L1 Extraction
    l1_concepts: List[dict]
    l1_extraction_feedback: Optional[str]
    
    # Step 2: L1 Validation
    validated_l1_concepts: List[dict]
    validation_summary: dict
    validation_feedback: str
    
    # Step 3: L1 Prerequisite Relationships
    l1_prerequisites: List[dict]
    
    # Step 4: Entity/Relation Extraction
    knowledge_points: List[dict]
    resources: List[dict]
    relationships: List[dict]
    
    # Step 5: Vectorization
    vector_db_updated: bool
    
    # Step 6: Calibration
    calibrated_kps: List[dict]
    calibrated_resources: List[dict]
    calibrated_relationships: List[dict]
    
    # Step 7: LLM Evaluation
    evaluation_report: dict
    
    # Step 8: Graph Build
    neo4j_imported: bool
    
    # Error handling
    errors: List[str]
    current_step: str
