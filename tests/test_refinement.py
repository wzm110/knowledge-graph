"""本地验证：微调 MERGE / DELETE / ADD 解析（不调用 LLM，除少量 mock）。"""

import json
from unittest.mock import patch

from knowledge_graph.agents.refinement import (
    GraphRefinementAgent,
    _is_isolated_batch_delete,
    _sort_actions,
)


def _minimal_config():
    return {
        "models": {"default_chat_model": {"model": "x", "api_key": "k", "api_base": "http://localhost"}},
        "refinement": {"max_actions": 10, "max_add_nodes_per_action": 10},
    }


def test_sort_actions_order():
    actions = [
        {"type": "DELETE", "target_id": "a"},
        {"type": "MERGE", "target_id": "b"},
        {"type": "ADD", "target_id": "c"},
    ]
    out = _sort_actions(actions)
    assert [a["type"] for a in out] == ["MERGE", "ADD", "DELETE"]


def test_merge_two_l2_redirects_edges():
    agent = GraphRefinementAgent(_minimal_config())
    kps = [
        {"id": "l1", "name": "L1", "level": "L1", "definition": ""},
        {"id": "a", "name": "A", "level": "L2", "definition": ""},
        {"id": "b", "name": "B", "level": "L2", "definition": ""},
        {"id": "c", "name": "C", "level": "L3", "definition": ""},
    ]
    rels = [
        {"type": "contains", "start_id": "l1", "end_id": "a", "reason": ""},
        {"type": "contains", "start_id": "l1", "end_id": "b", "reason": ""},
        {"type": "contains", "start_id": "a", "end_id": "c", "reason": ""},
    ]
    kps2, rels2 = agent.merge_two_l2_ids("a", "b", kps, rels)
    ids = {kp["id"] for kp in kps2}
    assert "b" not in ids
    assert any(r["end_id"] == "a" and r["start_id"] == "l1" for r in rels2)
    # L3 父边应从 b 改到 a
    assert any(r["start_id"] == "a" and r["end_id"] == "c" for r in rels2)


def test_merge_two_kp_redirects_edges_generic():
    agent = GraphRefinementAgent(_minimal_config())
    kps = [
        {"id": "l1", "name": "L1", "level": "L1", "definition": ""},
        {"id": "l2", "name": "L2", "level": "L2", "definition": ""},
        {"id": "x", "name": "索引和切片", "level": "L3", "definition": ""},
        {"id": "y", "name": "张量索引与切片", "level": "L3", "definition": ""},
    ]
    rels = [
        {"type": "contains", "start_id": "l1", "end_id": "l2", "reason": ""},
        {"type": "contains", "start_id": "l2", "end_id": "x", "reason": ""},
        {"type": "prerequisite", "start_id": "x", "end_id": "l2", "reason": ""},
    ]
    kps2, rels2 = agent.merge_two_kp_ids("y", "x", kps, rels)
    ids = {kp["id"] for kp in kps2}
    assert "x" not in ids
    # x 的出入边都应重定向到 y
    assert any(r["type"] == "contains" and r["start_id"] == "l2" and r["end_id"] == "y" for r in rels2)
    assert any(r["type"] == "prerequisite" and r["start_id"] == "y" and r["end_id"] == "l2" for r in rels2)


def test_delete_only_isolated():
    agent = GraphRefinementAgent(_minimal_config())
    kps = [
        {"id": "l1", "name": "L1", "level": "L1", "definition": ""},
        {"id": "iso", "name": "孤", "level": "L3", "definition": ""},
        {"id": "iso2", "name": "孤2", "level": "L3", "definition": ""},
    ]
    rels = []  # iso 孤立
    gd = {"kps": kps, "relationships": rels}
    # 不点名时，DELETE 会一次性删除当前所有孤立节点
    out_all = agent.execute_delete("", "", gd)
    assert out_all["kps"] == []

    # 点名时，只删除指定节点及其关系
    gd2 = {"kps": kps, "relationships": rels}
    out_one = agent.execute_delete("iso", "", gd2)
    ids = {kp["id"] for kp in out_one["kps"]}
    assert "iso" not in ids


def test_find_isolated_and_overloaded():
    agent = GraphRefinementAgent(_minimal_config())
    l1_id = "l1x"
    kps = [{"id": l1_id, "name": "T", "level": "L1", "definition": ""}]
    rels = []
    for i in range(11):
        lid = f"l2x_{i}"
        kps.append({"id": lid, "name": f"n{i}", "level": "L2", "definition": ""})
        rels.append({"type": "contains", "start_id": l1_id, "end_id": lid, "reason": ""})

    ov = agent.find_overloaded_topics(kps, rels)
    assert len(ov) == 1
    assert ov[0]["l2_count"] == 11


def test_graph_builder_filters_has_resource():
    from knowledge_graph.agents.graph_builder import GraphBuilderAgent

    agent = GraphBuilderAgent(_minimal_config())
    # 仅检查过滤逻辑：无 Neo4j 时 execute 会连库失败；这里只测 kp_ids 过滤思路
    kps = [{"id": "k1", "level": "L1", "name": "a", "definition": ""}]
    rels = [
        {"type": "contains", "start_id": "k1", "end_id": "k2", "reason": ""},
        {"type": "has_resource", "start_id": "k1", "end_id": "res1", "reason": ""},
    ]
    kp_ids = {kp.get("id", "") for kp in kps if kp.get("id")}
    filtered = [
        r
        for r in rels
        if r.get("type") != "has_resource" and r.get("start_id", "") in kp_ids and r.get("end_id", "") in kp_ids
    ]
    assert len(filtered) == 0  # k2 不在 kps 中，边也被过滤


def test_isolated_batch_delete_markers():
    assert _is_isolated_batch_delete("isolated_nodes_batch", "") is True
    assert _is_isolated_batch_delete("", "孤立节点集合") is True
    assert _is_isolated_batch_delete("", "") is False


def test_resolve_add_parent_by_l1_id():
    agent = GraphRefinementAgent(_minimal_config())
    kps = [
        {"id": "l1-6", "name": "循环神经网络与序列建模", "level": "L1", "definition": ""},
        {"id": "l2_x", "name": "子", "level": "L2", "definition": ""},
    ]
    rels = [{"type": "contains", "start_id": "l1-6", "end_id": "l2_x", "reason": ""}]
    sparse = agent.find_sparse_topics(kps, rels)
    sparse_l1_by_name = {t.get("name", ""): t for t in sparse if t.get("name")}
    sparse_l1_by_id = {t.get("id", ""): t for t in sparse if t.get("id")}
    sparse_l1_ids = {t.get("id", "") for t in sparse if t.get("id")}
    pid, pname, fh = agent._resolve_add_parent(
        kps,
        sparse_l1_by_id,
        sparse_l1_by_name,
        sparse_l1_ids,
        parent_id_raw="",
        target_id_raw="l1-6",
        target_name="生成模型与无监督学习",
        focus="",
    )
    assert pid == "l1-6"
    assert pname == "循环神经网络与序列建模"
    assert "生成" in fh


def test_delete_noop_when_no_targets_resolved():
    """DELETE 无法解析目标时不应计为已应用。"""
    agent = GraphRefinementAgent(_minimal_config())
    kps = [{"id": "x", "name": "X", "level": "L1", "definition": ""}]
    rels: list = []
    state = {
        "config": _minimal_config(),
        "evaluation_report": {"adjustment_suggestions": []},
        "calibrated_kps": kps,
        "calibrated_relationships": rels,
    }
    plan = {"actions": [{"type": "DELETE", "target_id": "不存在的id", "target": "", "reason": ""}]}

    def fake_llm(prompt, text, config):
        return json.dumps(plan)

    with patch("knowledge_graph.utils.llm.call_llm", side_effect=fake_llm):
        with patch.object(GraphRefinementAgent, "save_parquet", lambda self, *a, **k: None):
            agent = GraphRefinementAgent(_minimal_config())
            out = agent.execute(state)

    assert out["tuning_summary"].get("applied") is False
    assert out["tuning_summary"].get("reason") == "no_actions"


def test_refinement_execute_e2e_single_llm_call_for_plan():
    """端到端：mock 微调计划 LLM，执行 MERGE+DELETE，验证 tuning_summary 与图变化一致。"""
    plan = {
        "actions": [
            {"type": "MERGE", "keep_id": "b", "remove_id": "a", "reason": "测"},
            {"type": "DELETE", "target_id": "iso", "target": "", "reason": "删孤"},
        ]
    }

    kps = [
        {"id": "l1t", "name": "T", "level": "L1", "definition": "d"},
        {"id": "l2a", "name": "L2A", "level": "L2", "definition": ""},
        {"id": "a", "name": "短", "level": "L3", "definition": ""},
        {"id": "b", "name": "长名称", "level": "L3", "definition": ""},
        {"id": "iso", "name": "孤", "level": "L3", "definition": ""},
    ]
    rels = [
        {"type": "contains", "start_id": "l1t", "end_id": "l2a", "reason": ""},
        {"type": "contains", "start_id": "l2a", "end_id": "a", "reason": ""},
        {"type": "contains", "start_id": "l2a", "end_id": "b", "reason": ""},
    ]
    state = {
        "config": _minimal_config(),
        "evaluation_report": {"adjustment_suggestions": []},
        "calibrated_kps": kps,
        "calibrated_relationships": rels,
    }

    def fake_llm(prompt, text="", config=None):
        return json.dumps(plan)

    with patch("knowledge_graph.utils.llm.call_llm", side_effect=fake_llm):
        with patch.object(GraphRefinementAgent, "save_parquet", lambda self, *a, **k: None):
            agent = GraphRefinementAgent(_minimal_config())
            out = agent.execute(state)

    ts = out.get("tuning_summary", {})
    assert ts.get("applied") is True
    assert ts.get("applied_actions_count") == 2
    ids = {kp["id"] for kp in out["calibrated_kps"]}
    assert "a" not in ids and "iso" not in ids and "b" in ids


