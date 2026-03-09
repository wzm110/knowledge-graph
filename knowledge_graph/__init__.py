"""
Knowledge Graph Builder
======================

A knowledge graph construction system for education and learning scenarios.
Supports multiple textbooks, prerequisite relationship inference, and learning path planning.

Usage:
    poetry run kg-build
"""

__version__ = "0.1.0"
__author__ = "wzm110"

from knowledge_graph.steps.extract import extract_entities_relations
from knowledge_graph.steps.calibrate import calibrate_data
from knowledge_graph.steps.build import build_graph

__all__ = [
    "extract_entities_relations",
    "calibrate_data",
    "build_graph",
]
