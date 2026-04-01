"""
端到端流水线冒烟测试：mock 各步骤，不调用真实 LLM / Neo4j / Embedding。
验证 run_full_pipeline 编排与 state 收尾字段。
"""

from unittest.mock import patch

from knowledge_graph.pipeline import run_full_pipeline


def _minimal_config():
    return {
        "models": {
            "default_chat_model": {
                "model": "stub",
                "api_key": "stub",
                "api_base": "http://127.0.0.1:1",
            },
            "default_embedding_model": {
                "model": "stub",
                "api_key": "stub",
                "api_base": "http://127.0.0.1:1",
                "batch_size": 10,
            },
        },
        "neo4j": {
            "uri": "neo4j://127.0.0.1:7687",
            "user": "neo4j",
            "password": "stub",
            "database": "neo4j",
        },
        "pipeline": {"subject": "测试学科"},
        "calibration": {},
        "refinement": {},
        "recluster": {},
    }


def _fake_extract_l1(state):
    state["l1_concepts"] = [
        {
            "id": "l1-1",
            "name": "测试L1",
            "definition": "定义",
            "level": "L1",
            "source_chapters": [],
        }
    ]
    return state


def _fake_validate_l1(state):
    state["validated_l1_concepts"] = [
        {
            **state["l1_concepts"][0],
            "validation": {"is_valid": True, "overall_score": 8, "overall_feedback": ""},
        }
    ]
    state["validation_errors"] = []
    state["validation_summary"] = {"total": 1, "valid": 1, "invalid": 0}
    return state


def _fake_extract_prerequisites(state):
    state["l1_prerequisites"] = []
    return state


def _fake_extract_entities(state):
    state["knowledge_points"] = [
        {
            "id": "l2-1",
            "name": "测试L2",
            "level": "L2",
            "definition": "子知识点",
        }
    ]
    state["relationships"] = [
        {"type": "contains", "start_id": "l1-1", "end_id": "l2-1", "reason": ""},
    ]
    state["resources"] = []
    return state


def _fake_vectorize(state):
    state["vector_db_updated"] = True
    return state


def _fake_calibrate(state):
    l1 = state.get("validated_l1_concepts", [])
    kps = list(l1) + list(state.get("knowledge_points", []))
    state["calibrated_kps"] = kps
    state["calibrated_relationships"] = list(state.get("relationships", []))
    state["calibrated_resources"] = []
    return state


def _fake_regroup_graph(state):
    return state


def _fake_evaluate(state):
    state["evaluation_report"] = {
        "overall_score": 8.0,
        "is_passed": True,
        "dimensions": {},
        "adjustment_suggestions": [],
    }
    state["evaluation_passed"] = True
    return state


def _fake_tune_graph(state):
    state["tuning_summary"] = {"applied": False}
    return state


def _fake_build_graph(state):
    state["neo4j_imported"] = True
    return state


@patch("knowledge_graph.pipeline.build_graph", side_effect=_fake_build_graph)
@patch("knowledge_graph.pipeline.tune_graph", side_effect=_fake_tune_graph)
@patch("knowledge_graph.pipeline.evaluate", side_effect=_fake_evaluate)
@patch("knowledge_graph.pipeline.regroup_graph", side_effect=_fake_regroup_graph)
@patch("knowledge_graph.pipeline.calibrate", side_effect=_fake_calibrate)
@patch("knowledge_graph.pipeline.vectorize", side_effect=_fake_vectorize)
@patch("knowledge_graph.pipeline.extract_entities", side_effect=_fake_extract_entities)
@patch("knowledge_graph.pipeline.extract_prerequisites", side_effect=_fake_extract_prerequisites)
@patch("knowledge_graph.pipeline.validate_l1", side_effect=_fake_validate_l1)
@patch("knowledge_graph.pipeline.extract_l1", side_effect=_fake_extract_l1)
def test_run_full_pipeline_smoke_with_mocks(
    _mock_e1,
    _mock_v1,
    _mock_ep,
    _mock_ee,
    _mock_vec,
    _mock_cal,
    _mock_reg,
    _mock_eval,
    _mock_tune,
    _mock_build,
):
    state = run_full_pipeline(
        _minimal_config(),
        max_loops=1,
        max_eval_loops=1,
        test_mode=True,
        max_chapters=2,
        skip_l1_if_exists=False,
    )
    assert not state.get("errors") or state["errors"] == []
    assert len(state.get("validated_l1_concepts", [])) >= 1
    assert len(state.get("calibrated_kps", [])) >= 1
    assert state.get("vector_db_updated") is True
    assert state.get("neo4j_imported") is True
    assert state.get("evaluation_report", {}).get("is_passed") is True
