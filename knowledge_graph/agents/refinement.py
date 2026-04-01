#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Node 7.5: 图谱微调智能体
基于评估建议执行微调：支持 ADD、DELETE、MERGE（资源不入图，此处不处理资源）。
"""

import difflib
import hashlib
import json
import copy
from typing import List, Dict, Any, Tuple, Optional, Set

from knowledge_graph.agents.base_agent import LLMAgent, AgentState


# 动作执行顺序：先压 L2 上限，再补点，最后删孤立
_ACTION_ORDER = {"MERGE": 0, "ADD": 1, "DELETE": 2}

# DELETE：批量删除孤立节点时 LLM/评估可能使用的占位 target_id / target 文案（勿含空串，避免与「未填 id」混淆）
_ISOLATED_BATCH_IDS: Set[str] = {
    "isolated_nodes_batch",
    "isolated_batch",
    "isolated_all",
    "all_isolated",
    "batch_isolated",
    "__isolated_batch__",
}
_ISOLATED_BATCH_NAMES: Set[str] = {
    "孤立节点集合",
    "孤立节点",
    "全部孤立节点",
    "批量孤立节点",
}

def _norm_key(s: str) -> str:
    return (s or "").strip().lower()


def _build_graph_indices(kps: List[dict]) -> Dict[str, Any]:
    """id / 名称 多路索引，供 ADD/MERGE/DELETE 解析。"""
    id_to_kp: Dict[str, dict] = {}
    id_lower_to_canon: Dict[str, str] = {}
    name_to_kps: Dict[str, List[dict]] = {}
    for kp in kps:
        kid = (kp.get("id") or "").strip()
        if not kid:
            continue
        id_to_kp[kid] = kp
        id_lower_to_canon[kid.lower()] = kid
        n = (kp.get("name") or "").strip()
        if n:
            name_to_kps.setdefault(n, []).append(kp)
    return {
        "id_to_kp": id_to_kp,
        "id_lower_to_canon": id_lower_to_canon,
        "name_to_kps": name_to_kps,
    }


def _resolve_existing_id(raw: str, indices: Dict[str, Any]) -> str:
    """将 LLM 输出的 id 对齐到图中真实 id（大小写、空白）。"""
    s = (raw or "").strip()
    if not s:
        return ""
    id_to_kp = indices["id_to_kp"]
    id_lower = indices["id_lower_to_canon"]
    if s in id_to_kp:
        return s
    return id_lower.get(s.lower(), "")


def _best_name_match(
    name: str,
    kps: List[dict],
    *,
    levels: Optional[Tuple[str, ...]] = None,
    cutoff: float = 0.72,
) -> str:
    """名称模糊匹配到唯一节点 id；levels 限制层级顺序（先试 L2 再 L1 等）。"""
    name = (name or "").strip()
    if not name:
        return ""
    pool = kps
    if levels:
        order = {lv: i for i, lv in enumerate(levels)}
        pool = sorted(
            [kp for kp in kps if (kp.get("level") or "") in levels],
            key=lambda x: order.get(x.get("level", ""), 99),
        )
    names = [(kp.get("name") or "").strip() for kp in pool if kp.get("id")]
    matches = difflib.get_close_matches(name, names, n=1, cutoff=cutoff)
    if not matches:
        return ""
    hit = matches[0]
    cands = [kp for kp in pool if (kp.get("name") or "").strip() == hit]
    if len(cands) != 1:
        return ""
    return cands[0].get("id", "")


def _pick_id_by_name_preferring_level(
    name: str,
    name_to_kps: Dict[str, List[dict]],
    level_order: Tuple[str, ...] = ("L3", "L2", "L1"),
) -> str:
    """同名多节点时按 level_order 优先。"""
    cands = name_to_kps.get(name, [])
    if not cands:
        return ""
    if len(cands) == 1:
        return cands[0].get("id", "")
    order = {lv: i for i, lv in enumerate(level_order)}
    cands = sorted(
        cands,
        key=lambda x: (order.get(x.get("level", ""), 9), -len(x.get("name", "") or ""), x.get("id", "")),
    )
    return cands[0].get("id", "")


def _is_isolated_batch_delete(target_id: str, target: str) -> bool:
    raw_id = (target_id or "").strip()
    tname = (target or "").strip()
    if raw_id and raw_id in _ISOLATED_BATCH_IDS:
        return True
    if raw_id and raw_id.lower() in {m.lower() for m in _ISOLATED_BATCH_IDS}:
        return True
    if tname in _ISOLATED_BATCH_NAMES:
        return True
    if "孤立" in tname and ("批量" in tname or "集合" in tname or "全部" in tname):
        return True
    return False


def _sort_actions(actions: List[dict]) -> List[dict]:
    items = [(i, a) for i, a in enumerate(actions) if isinstance(a, dict)]
    items.sort(key=lambda x: (_ACTION_ORDER.get(str(x[1].get("type", "")).upper(), 99), x[0]))
    return [x[1] for x in items]


class GraphRefinementAgent(LLMAgent):
    """图谱微调智能体：ADD / DELETE / MERGE"""

    def __init__(self, config: dict):
        super().__init__(
            name="GraphRefinement",
            config=config,
            prompt_path="prompts/Refinement_Prompt.txt",
        )

    def load_current_graph(self, state: AgentState = None) -> dict:
        """加载当前图谱（知识点+关系）；资源后续独立入图，此处不加载。"""
        kps = self.load_parquet("data/output/calibrated_entities.parquet")
        relationships = self.load_parquet("data/output/calibrated_relationships.parquet")

        if state and state.get("calibrated_kps"):
            kps = state.get("calibrated_kps", kps or [])
        if state and state.get("calibrated_relationships"):
            relationships = state.get("calibrated_relationships", relationships or [])

        return {"kps": kps or [], "relationships": relationships or []}

    def find_isolated_nodes(self, kps: list, relationships: list) -> List[Dict]:
        connected_ids = set()
        for rel in relationships:
            connected_ids.add(rel.get("start_id", ""))
            connected_ids.add(rel.get("end_id", ""))

        isolated = []
        for kp in kps:
            kid = kp.get("id", "")
            if kid and kid not in connected_ids:
                isolated.append({"id": kid, "name": kp.get("name", ""), "level": kp.get("level", "")})
        return isolated

    def find_sparse_topics(self, kps: list, relationships: list) -> List[Dict]:
        l1_kps = [kp for kp in kps if kp.get("level") == "L1"]
        sparse = []
        for l1 in l1_kps:
            l1_id = l1.get("id", "")
            l2_ids = [
                r.get("end_id")
                for r in relationships
                if r.get("start_id") == l1_id and r.get("type") == "contains"
            ]
            kp_level = {kp.get("id", ""): kp.get("level", "") for kp in kps if kp.get("id")}
            l2_ids = [x for x in l2_ids if kp_level.get(x) == "L2"]
            if len(l2_ids) < 10:
                l2_kps = [kp for kp in kps if kp.get("id") in l2_ids]
                sparse.append(
                    {
                        "id": l1_id,
                        "name": l1.get("name", ""),
                        "l2_count": len(l2_ids),
                        "existing_l2": [kp.get("name", "") for kp in l2_kps],
                    }
                )
        return sparse

    def find_overloaded_topics(self, kps: list, relationships: list) -> List[Dict]:
        l1_kps = [kp for kp in kps if kp.get("level") == "L1"]
        kp_level = {kp.get("id", ""): kp.get("level", "") for kp in kps if kp.get("id")}
        overloaded = []
        for l1 in l1_kps:
            l1_id = l1.get("id", "")
            l2_ids = [
                r.get("end_id")
                for r in relationships
                if r.get("start_id") == l1_id and r.get("type") == "contains"
            ]
            l2_ids = [x for x in l2_ids if kp_level.get(x) == "L2"]
            if len(l2_ids) > 10:
                l2_kps = [kp for kp in kps if kp.get("id") in l2_ids]
                overloaded.append(
                    {
                        "id": l1_id,
                        "name": l1.get("name", ""),
                        "l2_count": len(l2_ids),
                        "existing_l2": [kp.get("name", "") for kp in l2_kps],
                    }
                )
        return overloaded

    def _catalog_for_prompt(self, kps: list, relationships: list) -> Tuple[list, list]:
        """(L1 列表, L2 列表) 供微调计划 LLM 复制真实 parent_id。"""
        l1_entries = []
        for kp in kps:
            if kp.get("level") == "L1" and kp.get("id"):
                l1_entries.append({"id": kp.get("id"), "name": (kp.get("name") or "").strip()})
        kp_by_id = {kp.get("id"): kp for kp in kps if kp.get("id")}
        l2_entries = []
        for r in relationships:
            if r.get("type") != "contains":
                continue
            pid, cid = r.get("start_id"), r.get("end_id")
            child = kp_by_id.get(cid)
            if not child or child.get("level") != "L2":
                continue
            parent = kp_by_id.get(pid)
            l1_name = ""
            l1_id = ""
            if parent and parent.get("level") == "L1":
                l1_name = (parent.get("name") or "").strip()
                l1_id = parent.get("id", "")
            l2_entries.append(
                {
                    "id": cid,
                    "name": (child.get("name") or "").strip(),
                    "l1_id": l1_id,
                    "l1_name": l1_name,
                }
            )
        return l1_entries, l2_entries

    def _collect_suggestion_node_ids(self, sugg_lines: List[dict]) -> Set[str]:
        """从已归一的建议条目中收集所有在图中应解析的节点 id。"""
        ids: Set[str] = set()
        for s in sugg_lines:
            action = str(s.get("action", "")).upper()
            for key in ("parent_id", "keep_id", "remove_id", "target_id"):
                v = (s.get(key) or "").strip()
                if not v:
                    continue
                if action == "DELETE" and v in _ISOLATED_BATCH_IDS:
                    continue
                if v.lower() in {m.lower() for m in _ISOLATED_BATCH_NAMES}:
                    continue
                ids.add(v)
        return ids

    def _nodes_catalog_for_prompt(
        self,
        kps: list,
        relationships: list,
        referenced_ids: Set[str],
    ) -> List[dict]:
        """仅包含本批建议涉及的节点：id + name + level（及 L3 的父 L2），不全量列出 L2。"""
        kp_by_id = {kp.get("id"): kp for kp in kps if kp.get("id")}
        # end_id -> start_id for contains
        parent_by_child: Dict[str, str] = {}
        for r in relationships:
            if r.get("type") != "contains":
                continue
            eid = r.get("end_id", "")
            sid = r.get("start_id", "")
            if eid and sid:
                parent_by_child[eid] = sid

        rows: List[dict] = []
        for iid in sorted(referenced_ids):
            kp = kp_by_id.get(iid)
            if not kp:
                rows.append({"id": iid, "name": "", "level": "", "note": "当前图中未找到该 id"})
                continue
            row: Dict[str, Any] = {
                "id": iid,
                "name": (kp.get("name") or "").strip(),
                "level": (kp.get("level") or "").strip(),
            }
            pid = parent_by_child.get(iid, "")
            parent_kp = kp_by_id.get(pid)
            if parent_kp:
                row["parent_id"] = pid
                row["parent_name"] = (parent_kp.get("name") or "").strip()
                row["parent_level"] = (parent_kp.get("level") or "").strip()
            rows.append(row)
        return rows

    def _resolve_add_parent(
        self,
        kps: list,
        sparse_l1_by_id: Dict[str, dict],
        sparse_l1_by_name: Dict[str, dict],
        sparse_l1_ids: Set[str],
        *,
        parent_id_raw: str,
        target_id_raw: str,
        target_name: str,
        focus: str,
    ) -> Tuple[str, str, str]:
        """
        解析 ADD 的父节点（L1 补 L2 / L2 补 L3）。
        返回 (parent_id, parent_display_name, focus_hint)。
        """
        indices = _build_graph_indices(kps)
        id_to_kp = indices["id_to_kp"]
        name_to_kps = indices["name_to_kps"]

        def _name_of(pid: str) -> str:
            kp = id_to_kp.get(pid)
            return (kp.get("name") or "").strip() if kp else ""

        # 1) 显式 parent_id / target_id（兼容字段）
        for raw in (parent_id_raw, target_id_raw):
            rid = _resolve_existing_id(raw, indices)
            if rid and rid in id_to_kp:
                lv = id_to_kp[rid].get("level", "")
                if lv in ("L1", "L2"):
                    pname = _name_of(rid)
                    fh = (focus or "").strip()
                    if not fh and target_name and target_name.strip() != pname:
                        fh = target_name.strip()
                    return rid, pname, fh

        # 2) 名称精确命中（唯一 L1 或 唯一 L2）
        tn = (target_name or "").strip()
        if tn:
            cands = name_to_kps.get(tn, [])
            l1_only = [x for x in cands if x.get("level") == "L1"]
            l2_only = [x for x in cands if x.get("level") == "L2"]
            if len(l1_only) == 1 and not l2_only:
                pid = l1_only[0].get("id", "")
                return pid, tn, (focus or "").strip()
            if len(l2_only) == 1 and not l1_only:
                pid = l2_only[0].get("id", "")
                return pid, tn, (focus or "").strip()
            if len(l1_only) == 1 and len(l2_only) >= 1:
                # 同名歧义：优先把稀疏 L1 的 target_id 当作父级提示
                tid = _resolve_existing_id(target_id_raw, indices)
                if tid in sparse_l1_ids:
                    for x in l1_only:
                        if x.get("id") == tid:
                            return tid, tn, (focus or "").strip()
                # 否则优先 L2（补 L3 更常见且名称冲突时更具体）
                pid = l2_only[0].get("id", "")
                return pid, tn, (focus or "").strip()

        # 3) 稀疏 L1 表（旧逻辑）
        if tn and tn in sparse_l1_by_name:
            d = sparse_l1_by_name[tn]
            pid = (d.get("id") or "").strip()
            if pid:
                return pid, tn, (focus or "").strip()

        # 4) 模糊匹配：先 L1 再 L2
        if tn:
            pid = _best_name_match(tn, kps, levels=("L1",), cutoff=0.75)
            if pid:
                return pid, _name_of(pid), (focus or "").strip()
            pid = _best_name_match(tn, kps, levels=("L2",), cutoff=0.75)
            if pid:
                return pid, _name_of(pid), (focus or "").strip()

        # 5) target 不是图中节点名时：视为「待补充概念」提示，父节点仅靠 id / focus
        fh = (focus or "").strip()
        for raw in (parent_id_raw, target_id_raw):
            rid = _resolve_existing_id(raw, indices)
            if rid and rid in id_to_kp and id_to_kp[rid].get("level") in ("L1", "L2"):
                pname = _name_of(rid)
                if not fh and tn:
                    fh = tn
                return rid, pname, fh

        return "", "", (focus or tn or "").strip()

    def _l2_ids_under_l1(self, l1_id: str, kps: list, relationships: list) -> List[str]:
        kp_level = {kp.get("id", ""): kp.get("level", "") for kp in kps if kp.get("id")}
        out = []
        for r in relationships:
            if r.get("type") == "contains" and r.get("start_id") == l1_id:
                eid = r.get("end_id", "")
                if kp_level.get(eid) == "L2":
                    out.append(eid)
        return out

    def _dedupe_relationships(self, relationships: list) -> list:
        seen = set()
        out = []
        for rel in relationships:
            key = (rel.get("type", ""), rel.get("start_id", ""), rel.get("end_id", ""))
            if key in seen:
                continue
            seen.add(key)
            out.append(rel)
        return out

    def _redirect_id_in_relationships(self, relationships: list, old_id: str, new_id: str) -> None:
        for rel in relationships:
            if rel.get("start_id") == old_id:
                rel["start_id"] = new_id
                rel["reason"] = (rel.get("reason", "") or "") + ";微调合并"
            if rel.get("end_id") == old_id:
                rel["end_id"] = new_id
                rel["reason"] = (rel.get("reason", "") or "") + ";微调合并"

    def _remove_self_loop_rels(self, relationships: list) -> list:
        return [
            r
            for r in relationships
            if not (r.get("start_id") and r.get("end_id") and r.get("start_id") == r.get("end_id"))
        ]

    def merge_two_l2_ids(
        self, keep_id: str, remove_id: str, kps: list, relationships: list
    ) -> Tuple[list, list]:
        """将 remove_id 合并进 keep_id：边重写、删除被合并节点。"""
        if keep_id == remove_id:
            return kps, relationships
        self._redirect_id_in_relationships(relationships, remove_id, keep_id)
        kps = [kp for kp in kps if kp.get("id") != remove_id]
        relationships = self._remove_self_loop_rels(relationships)
        relationships = self._dedupe_relationships(relationships)
        return kps, relationships

    def merge_two_kp_ids(
        self, keep_id: str, remove_id: str, kps: list, relationships: list
    ) -> Tuple[list, list]:
        """通用 MERGE：将 remove_id 合并进 keep_id，并重定向所有关系（start/end）。"""
        if not keep_id or not remove_id or keep_id == remove_id:
            return kps, relationships
        kp_ids = {kp.get("id", "") for kp in kps if kp.get("id")}
        if keep_id not in kp_ids or remove_id not in kp_ids:
            return kps, relationships

        self._redirect_id_in_relationships(relationships, remove_id, keep_id)
        kps = [kp for kp in kps if kp.get("id") != remove_id]
        relationships = self._remove_self_loop_rels(relationships)
        relationships = self._dedupe_relationships(relationships)
        return kps, relationships

    def generate_refinement_plan(self, evaluation_report: dict, graph_data: dict) -> dict:
        """基于评估建议生成微调计划（ADD / DELETE / MERGE）。"""
        kps = graph_data["kps"]
        relationships = graph_data["relationships"]

        max_input_suggestions = int(self.config.get("refinement", {}).get("max_input_suggestions", 60))
        max_actions = int(self.config.get("refinement", {}).get("max_actions", 35))

        sparse_topics = self.find_sparse_topics(kps, relationships)
        sparse_l1_by_name = {t.get("name", ""): t for t in sparse_topics if t.get("name")}
        sparse_l1_by_id = {t.get("id", ""): t for t in sparse_topics if t.get("id")}
        sparse_l1_ids = {t.get("id", "") for t in sparse_topics if t.get("id")}

        overloaded = self.find_overloaded_topics(kps, relationships)

        adjustment_suggestions = evaluation_report.get("adjustment_suggestions", [])
        high_list: List[dict] = []
        if isinstance(adjustment_suggestions, list) and adjustment_suggestions:
            # 接入所有优先级的建议（high/medium/low），按优先级排序后截断
            def _prio(s: dict) -> int:
                p = str((s or {}).get("priority", "")).lower()
                order = {"high": 0, "medium": 1, "low": 2}
                return order.get(p, 3)

            all_dict_suggs = [s for s in adjustment_suggestions if isinstance(s, dict)]
            all_dict_suggs.sort(key=_prio)
            high_list = all_dict_suggs[:max_input_suggestions]

        def infer_l1_from_source(s: dict) -> str:
            source = (s.get("source") or "").strip()
            marker = "L1簇:"
            idx = source.find(marker)
            if idx < 0:
                return ""
            return source[idx + len(marker) :].strip()

        normalized_lines = []
        for s in high_list:
            action = str(s.get("action", "")).upper()
            if action == "ADD":
                pid, pname, fh = self._resolve_add_parent(
                    kps,
                    sparse_l1_by_id,
                    sparse_l1_by_name,
                    sparse_l1_ids,
                    parent_id_raw=(s.get("parent_id") or s.get("target_id") or "").strip(),
                    target_id_raw="",
                    target_name=(s.get("target") or "").strip(),
                    focus=(s.get("focus") or "").strip(),
                )
                if not pid:
                    l1n = infer_l1_from_source(s)
                    if l1n and l1n in sparse_l1_by_name:
                        pid = sparse_l1_by_name[l1n].get("id", "")
                        pname = l1n
                if pid:
                    normalized_lines.append(
                        {
                            **s,
                            "parent_id": pid,
                            "target_id": pid,
                            "target": pname,
                            "focus": fh or (s.get("focus") or ""),
                        }
                    )
                else:
                    normalized_lines.append(s)
            elif action in ("MERGE", "DELETE"):
                normalized_lines.append(s)

        indices_ctx = _build_graph_indices(kps)
        id_to_kp_ctx = indices_ctx["id_to_kp"]

        def _nid(raw: str) -> str:
            return _resolve_existing_id((raw or "").strip(), indices_ctx)

        def _nm(pid: str) -> str:
            kp = id_to_kp_ctx.get(pid)
            return (kp.get("name") or "").strip() if kp else ""

        def _label(pid: str, explicit: str) -> str:
            g = _nm(pid)
            ex = (explicit or "").strip()
            if ex and g and ex != g:
                return f"{g} | 评测标注:{ex}"
            return ex or g

        # 将建议格式化为「id 与 name 共存」，供计划 LLM 对照目录逐字复制 id
        def _fmt_sugg(s: dict) -> str:
            action = s.get("action", "")
            parts = [
                f"action={action}",
                f"source={s.get('source', '')}",
            ]
            pp = _nid(str(s.get("parent_id", "")))
            if pp:
                parts.append(f"parent_id={pp} (name={_label(pp, str(s.get('parent_name') or ''))})")
            else:
                parts.append("parent_id=")
            rk = _nid(str(s.get("keep_id", "")))
            rr = _nid(str(s.get("remove_id", "")))
            if rk:
                parts.append(f"keep_id={rk} (name={_label(rk, str(s.get('keep_name') or ''))})")
            else:
                parts.append("keep_id=")
            if rr:
                parts.append(f"remove_id={rr} (name={_label(rr, str(s.get('remove_name') or ''))})")
            else:
                parts.append("remove_id=")
            td = (s.get("target_id") or "").strip()
            if td and td not in _ISOLATED_BATCH_IDS:
                tdr = _nid(td)
                tn = str(s.get("target_name") or "")
                parts.append(
                    f"target_id={tdr or td} (name={_label(tdr if tdr else td, tn)})"
                )
            else:
                parts.append(f"target_id={td}, delete_mode={s.get('delete_mode', '')}")
            parts.append(f"focus={s.get('focus', '')}")
            parts.append(f"reason={str(s.get('reason', ''))[:200]}")
            return "- " + ", ".join(parts)

        sugg_str = "\n".join(_fmt_sugg(s) for s in normalized_lines) or "无"

        # 计算基于图规模的有效动作上限（孤立节点越多，上限越高）
        isolated_nodes = self.find_isolated_nodes(kps, relationships)
        iso_count = len(isolated_nodes)
        base_max = max_actions
        if iso_count <= 20:
            effective_max = base_max
        elif iso_count <= 100:
            effective_max = base_max * 2
        else:
            effective_max = base_max * 3

        l1_catalog, _full_l2 = self._catalog_for_prompt(kps, relationships)
        ref_ids = self._collect_suggestion_node_ids(normalized_lines)
        suggestion_nodes = self._nodes_catalog_for_prompt(kps, relationships, ref_ids)
        template = self.load_prompt("prompts/Refinement_Plan_Prompt.txt")
        prompt = (
            template
            .replace("{high_level_suggestions}", sugg_str)
            .replace("{overloaded_json}", json.dumps(overloaded, ensure_ascii=False, indent=2))
            .replace("{sparse_json}", json.dumps(sparse_topics, ensure_ascii=False, indent=2))
            .replace(
                "{isolated_json}",
                json.dumps(isolated_nodes[:30], ensure_ascii=False, indent=2),
            )
            .replace("{l1_catalog_json}", json.dumps(l1_catalog, ensure_ascii=False, indent=2))
            .replace(
                "{suggestion_nodes_catalog_json}",
                json.dumps(suggestion_nodes, ensure_ascii=False, indent=2),
            )
            .replace("{max_actions}", str(effective_max))
        )

        try:
            response = self.call_llm(prompt, "")
            result = json.loads(response) if response else {}
            actions = result.get("actions", [])
            if not isinstance(actions, list):
                actions = []
        except Exception as e:
            self.log(f"生成微调计划失败: {e}", "warning")
            actions = []

        filtered: List[dict] = []
        isolated_ids = {n.get("id", "") for n in isolated_nodes if n.get("id")}

        name_to_kps: Dict[str, List[dict]] = {}
        for kp in kps:
            n = kp.get("name", "")
            kid = kp.get("id", "")
            if not n or not kid:
                continue
            name_to_kps.setdefault(n, []).append(kp)

        non_delete_kept = 0
        delete_added = False
        for a in actions[: effective_max * 2]:
            if not isinstance(a, dict):
                continue
            t = str(a.get("type", "")).upper()
            tid = (a.get("target_id") or "").strip()
            tname = (a.get("target") or "").strip()
            sid = (a.get("source_id") or "").strip()
            sname = (a.get("source") or "").strip()
            focus = (a.get("focus") or a.get("child_hint") or a.get("focus_topic") or "").strip()
            parent_id_in = (a.get("parent_id") or "").strip()

            if t == "MERGE":
                indices = _build_graph_indices(kps)
                id_to_kp = indices["id_to_kp"]
                rk = _resolve_existing_id((a.get("keep_id") or a.get("retain_id") or "").strip(), indices)
                rr = _resolve_existing_id((a.get("remove_id") or "").strip(), indices)
                if not rk or not rr:
                    tid_r = _resolve_existing_id(tid, indices)
                    sid_r = _resolve_existing_id(sid, indices)
                    if tid_r and sid_r and tid_r != sid_r:
                        rk, rr = tid_r, sid_r
                if rk and rr and rk != rr:
                    kp_r = id_to_kp.get(rk, {})
                    kp_m = id_to_kp.get(rr, {})
                    kn_r = (a.get("keep_name") or "").strip() or (kp_r.get("name") or "")
                    kn_m = (a.get("remove_name") or "").strip() or (kp_m.get("name") or "")
                    filtered.append(
                        {
                            "type": "MERGE",
                            "keep_id": rk,
                            "keep_name": kn_r,
                            "remove_id": rr,
                            "remove_name": kn_m,
                            "source_id": rr,
                            "source": kn_m,
                            "target_id": rk,
                            "target": kn_r,
                            "reason": a.get("reason", ""),
                        }
                    )
                    non_delete_kept += 1
                else:
                    self.log(
                        f"MERGE 计划跳过: 缺少有效 keep_id/remove_id (keep_id={rk}, remove_id={rr})",
                        "warning",
                    )
            elif t == "ADD":
                pid, pname, fh = self._resolve_add_parent(
                    kps,
                    sparse_l1_by_id,
                    sparse_l1_by_name,
                    sparse_l1_ids,
                    parent_id_raw=parent_id_in,
                    target_id_raw=tid,
                    target_name=tname,
                    focus=focus,
                )
                if pid:
                    merged_focus = (fh or focus or "").strip()
                    pname_out = (a.get("parent_name") or "").strip() or pname
                    filtered.append(
                        {
                            "type": "ADD",
                            "parent_id": pid,
                            "parent_name": pname_out,
                            "target_id": pid,
                            "target": pname_out,
                            "focus": merged_focus,
                            "reason": a.get("reason", ""),
                        }
                    )
                    non_delete_kept += 1
                else:
                    self.log(
                        f"ADD 计划跳过: 无法解析父节点 (parent_id={parent_id_in}, target_id={tid}, target={tname})",
                        "warning",
                    )
            elif t == "DELETE":
                dm = str(a.get("delete_mode") or a.get("mode") or "").strip().lower()
                no_target = not (tid or tname)
                batch = (
                    _is_isolated_batch_delete(tid, tname)
                    or dm
                    in (
                        "isolated",
                        "isolated_all",
                        "isolated_batch",
                        "batch",
                        "all_isolated",
                    )
                    or no_target
                )
                if batch:
                    if delete_added:
                        continue
                    if isolated_ids:
                        filtered.append(
                            {
                                "type": "DELETE",
                                "target_id": "",
                                "target": "",
                                "delete_mode": "isolated_batch",
                                "reason": a.get("reason", ""),
                            }
                        )
                        delete_added = True
                    continue
                # 点名删除
                indices = _build_graph_indices(kps)
                del_id = _resolve_existing_id(tid, indices)
                if not del_id and tname:
                    del_id = _pick_id_by_name_preferring_level(tname, name_to_kps)
                if not del_id and tname:
                    del_id = _best_name_match(tname, kps, levels=("L3", "L2", "L1"))
                if del_id:
                    filtered.append(
                        {
                            "type": "DELETE",
                            "target_id": del_id,
                            "target": tname,
                            "delete_mode": "single",
                            "reason": a.get("reason", ""),
                        }
                    )
                else:
                    self.log(f"DELETE 计划跳过: 无法解析目标 (target_id={tid}, target={tname})", "warning")

            # 只对 MERGE/ADD 应用上限，DELETE 不受 effective_max 限制
            if non_delete_kept >= effective_max:
                break

        result = {"actions": _sort_actions(filtered)}
        self.log(f"微调计划: {len(result['actions'])} 个操作(上限{effective_max})")
        return result

    def execute_delete(self, target_id: str, target_name: str, graph_data: dict) -> dict:
        kps = graph_data["kps"]
        relationships = graph_data["relationships"]
        isolated = self.find_isolated_nodes(kps, relationships)
        isolated_ids = {n.get("id", "") for n in isolated if n.get("id")}

        # 1) 如果点名了具体节点 id/name，则删除该节点及其所有关联关系
        to_remove: List[str] = []
        if target_id:
            to_remove = [target_id]
        elif target_name:
            for kp in kps:
                if kp.get("name") == target_name and kp.get("id"):
                    to_remove = [kp.get("id", "")]
                    break
        else:
            # 2) 未点名时，一次性删除当前所有孤立节点
            to_remove = [n.get("id", "") for n in isolated if n.get("id")]

        to_remove = [tid for tid in to_remove if tid]
        if not to_remove:
            self.log("DELETE: 无合法目标，跳过", "warning")
            return graph_data

        remove_set = set(to_remove)
        new_kps = [kp for kp in kps if kp.get("id", "") not in remove_set]
        # 同时移除涉及这些节点的所有关系
        new_rels = [
            r
            for r in relationships
            if r.get("start_id") not in remove_set and r.get("end_id") not in remove_set
        ]

        if target_id or target_name:
            self.log(f"DELETE: 删除指定节点 {len(remove_set)} 个（含其关联关系）")
        else:
            self.log(f"DELETE: 删除孤立节点 {len(remove_set)} 个")

        return {"kps": new_kps, "relationships": new_rels}

    def _add_prompt_peer_lines(self, peer_kps: List[dict], max_n: int = 5) -> str:
        """从同级已有知识点抽几行 id/name，供 LLM 对齐风格。"""
        lines: List[str] = []
        for kp in peer_kps[:max_n]:
            kid = (kp.get("id") or "").strip()
            kn = (kp.get("name") or "").strip()
            if kid or kn:
                lines.append(f'  - id="{kid}" name="{kn}"')
        if not lines:
            return "（当前无同级知识点示例，请严格按下方 id/name 规则生成。）"
        return "同级知识点结构参考（**id 与 name 风格须与现网一致**）：\n" + "\n".join(lines)

    def _add_node_schema_rules(self, child_level: str) -> str:
        """说明新增节点与全图 L1/L2/L3 知识点 schema 一致。"""
        lv = (child_level or "L2").upper()
        prefix = lv.lower()
        return f"""### 节点类型与命名（必须与图中已有知识点结构一致）
- **层级语义**：L1、L2、L3 均为课程内的**知识点**；本批生成的是 **{lv} 级知识点**（比父级更细的可教、可考概念）。
- **id**：必须以小写 `{prefix}_` 开头；后面为**英文 snake_case**，用英文关键词概括概念核心（例如 `{prefix}_domain_adaptation`）。仅使用 `a-z`、`0-9`、下划线；**全图唯一**，不得与已有 id 重复。
- **name**：使用**规范、简短的中文知识点名称**（教材或领域通用称谓，可作目录/大纲条目）；避免口语长句，完整解释写在 `description`（可与 name 相同或更详）。
- **level**：必须为 `"{lv}"`；**difficulty** 为「基础」「中等」「高」之一；**aliases** 为字符串列表（同义词，可空列表）。
- **description**：该知识点的定义或说明，与 `definition` 语义一致时可同义填写。"""

    def _add_l3_granularity_rules(self) -> str:
        """L3 专用：控制过细拆分与同义重复（与提示词强约束）。"""
        return """### L3 粒度与去重（仅 L3，必须遵守）
- **粒度**：L3 仍是「知识点」级条目，**不要**拆成过细的数学工具/步骤清单（例如与当前 L2 主题弱相关、更适合作为某条 L3 的 `description` 或 `aliases` 的内容，不要单独占一个节点）。
- **去重**：与「现有 L3 名称列表」**语义同义、包含或只差别名**的，**不要新建**（同义请用 `aliases`，不要再造节点）；与「优先补充方向」若已被现有某条 L3 覆盖，则输出 **`new_nodes` 为空数组**。
- **数量**：**宁少勿滥**，只补**明显缺口**；若无法确定是否重复，**宁可少输出**。
"""

    def execute_add(self, parent_id: str, parent_name: str, graph_data: dict, focus_hint: str = "") -> dict:
        kps = graph_data["kps"]
        relationships = graph_data["relationships"]
        focus_text = (focus_hint or "").strip()
        parent_found = False

        if not parent_id or parent_id == parent_name:
            parent_id = None
            for kp in kps:
                if kp.get("name") == parent_name:
                    parent_id = kp.get("id", "")
                    parent_found = True
                    parent_name = kp.get("name", parent_name)
                    break
        else:
            for kp in kps:
                if kp.get("id") == parent_id:
                    parent_found = True
                    parent_name = kp.get("name", parent_name)
                    break

        if not parent_id or not parent_found:
            self.log(f"ADD: 未找到父节点: {parent_name}", "warning")
            return graph_data

        parent_level = ""
        for kp in kps:
            if kp.get("id") == parent_id:
                parent_level = kp.get("level", "")
                break

        kp_level_map = {kp.get("id", ""): kp.get("level", "") for kp in kps if kp.get("id")}
        existing_ids = {kp["id"] for kp in kps if kp.get("id")}
        max_add_nodes = int(self.config.get("refinement", {}).get("max_add_nodes_per_action", 10))

        # 针对 L1：补 L2
        if parent_level == "L1":
            existing_l2_ids = [
                r.get("end_id")
                for r in relationships
                if r.get("start_id") == parent_id
                and r.get("type") == "contains"
                and kp_level_map.get(r.get("end_id", "")) == "L2"
            ]
            existing_l2_kps = [kp for kp in kps if kp.get("id") in existing_l2_ids]
            existing_l2_names = [kp.get("name", "") for kp in existing_l2_kps]
            existing_l2_name_set = {
                n.strip().lower() for n in existing_l2_names if isinstance(n, str) and n.strip()
            }
            remain_slots = max(0, 10 - len(existing_l2_ids))
            if remain_slots <= 0:
                self.log(f"ADD跳过: L2 已满 10", "warning")
                return graph_data
            allowed_add_nodes = min(max_add_nodes, remain_slots)

            focus_block = ""
            if focus_text:
                focus_block = f"\n优先补充方向: {focus_text}\n"

            peer_block = self._add_prompt_peer_lines(existing_l2_kps)
            rules_block = self._add_node_schema_rules("L2")

            prompt = f"""你是知识图谱专家。请为以下 L1 主题补充 **L2 级知识点**（每个节点表示该主题下的一个子知识主题）。

{rules_block}

{peer_block}

L1主题（父知识点）: {parent_name}
现有 L2 名称列表: {', '.join(existing_l2_names) if existing_l2_names else '无'}
{focus_block}

输出 JSON（只输出 JSON，不要其它文字）：
{{
  "new_nodes": [
    {{"id": "l2_english_snake_case", "name": "规范中文知识点名", "level": "L2", "description": "定义或说明", "difficulty": "中等", "aliases": []}}
  ]
}}
补充数量不超过 {allowed_add_nodes} 个；**name** 不得与上列现有 L2 名称重复（忽略大小写）。"""
            try:
                response = self.call_llm(prompt, "")
                result = json.loads(response) if response else {}
                new_nodes = result.get("new_nodes", [])
                if not isinstance(new_nodes, list):
                    new_nodes = []
                new_nodes = new_nodes[:allowed_add_nodes]
                existing_contains = {
                    (r.get("start_id", ""), r.get("end_id", ""), r.get("type", "")) for r in relationships
                }
                applied_count = 0

                for node in new_nodes:
                    if not isinstance(node, dict):
                        continue
                    normalized = self._normalize_added_node(node, "L2", existing_ids)
                    child_id = normalized["id"]
                    child_name = (normalized.get("name") or "").strip()
                    if not child_name or child_name.lower() in existing_l2_name_set:
                        continue
                    if child_id in existing_ids:
                        continue
                    if not normalized.get("description"):
                        normalized["description"] = child_name
                        normalized["definition"] = child_name
                    normalized["parent_id"] = parent_id
                    normalized["parent_name"] = parent_name
                    kps.append(normalized)
                    existing_ids.add(child_id)
                    existing_l2_name_set.add(child_name.lower())
                    applied_count += 1
                    ck = (parent_id, child_id, "contains")
                    if ck not in existing_contains:
                        relationships.append(
                            {
                                "start_id": parent_id,
                                "end_id": child_id,
                                "type": "contains",
                                "reason": "微调补充",
                            }
                        )
                        existing_contains.add(ck)
                self.log(f"ADD: 为 L1[{parent_name}] 新增 {applied_count} 个 L2")
            except Exception as e:
                self.log(f"ADD 失败: {e}", "warning")

            return {"kps": kps, "relationships": relationships}

        # 针对 L2：补 L3
        if parent_level == "L2":
            existing_l3_ids = [
                r.get("end_id")
                for r in relationships
                if r.get("start_id") == parent_id
                and r.get("type") == "contains"
                and kp_level_map.get(r.get("end_id", "")) == "L3"
            ]
            existing_l3_kps = [kp for kp in kps if kp.get("id") in existing_l3_ids]
            existing_l3_names = [kp.get("name", "") for kp in existing_l3_kps]
            existing_l3_name_set = {
                n.strip().lower() for n in existing_l3_names if isinstance(n, str) and n.strip()
            }
            ref_cfg = self.config.get("refinement", {}) or {}
            max_l3_per_l2 = int(ref_cfg.get("max_l3_per_l2", 8))
            per_call_cap = int(ref_cfg.get("max_l3_add_per_call", 3))
            n_l3 = len(existing_l3_ids)
            remain_slots = max(0, max_l3_per_l2 - n_l3)
            allowed_add_nodes = min(max_add_nodes, remain_slots, per_call_cap)
            if allowed_add_nodes <= 0:
                self.log(
                    f"ADD跳过: L2[{parent_name}] 下 L3 已达上限({max_l3_per_l2})或无可补槽位(已有{n_l3})",
                    "warning",
                )
                return {"kps": kps, "relationships": relationships}

            focus_block = ""
            if focus_text:
                focus_block = f"\n优先补充方向: {focus_text}\n"

            peer_block = self._add_prompt_peer_lines(existing_l3_kps)
            rules_block = self._add_node_schema_rules("L3")
            gran_block = self._add_l3_granularity_rules()

            prompt = f"""你是知识图谱专家。请为以下 L2 主题补充 **L3 级知识点**（每个节点表示更细粒度的可教概念）。

{rules_block}

{gran_block}

{peer_block}

L2主题（父知识点）: {parent_name}
当前该 L2 下已有 **{n_l3}** 个 L3；**全图约定**该 L2 下 L3 总数不超过 **{max_l3_per_l2}** 个（剩余可补槽位 **{remain_slots}** 个）。
现有 L3 名称列表: {', '.join(existing_l3_names) if existing_l3_names else '无'}
{focus_block}

输出 JSON（只输出 JSON，不要其它文字）：
{{
  "new_nodes": [
    {{"id": "l3_english_snake_case", "name": "规范中文知识点名", "level": "L3", "description": "定义或说明", "difficulty": "中等", "aliases": []}}
  ]
}}
**本次调用最多输出 {allowed_add_nodes} 条**（宁少勿滥；若无可补缺口可输出 `{{"new_nodes": []}}`）。
**name** 不得与上列现有 L3 名称重复（忽略大小写），且不得与现有 L3 语义重复（见上文「L3 粒度与去重」）。"""
            try:
                response = self.call_llm(prompt, "")
                result = json.loads(response) if response else {}
                new_nodes = result.get("new_nodes", [])
                if not isinstance(new_nodes, list):
                    new_nodes = []
                new_nodes = new_nodes[:allowed_add_nodes]
                existing_contains = {
                    (r.get("start_id", ""), r.get("end_id", ""), r.get("type", "")) for r in relationships
                }
                applied_count = 0

                for node in new_nodes:
                    if not isinstance(node, dict):
                        continue
                    normalized = self._normalize_added_node(node, "L3", existing_ids)
                    child_id = normalized["id"]
                    child_name = (normalized.get("name") or "").strip()
                    if not child_name or child_name.lower() in existing_l3_name_set:
                        continue
                    if child_id in existing_ids:
                        continue
                    if not normalized.get("description"):
                        normalized["description"] = child_name
                        normalized["definition"] = child_name
                    normalized["parent_id"] = parent_id
                    normalized["parent_name"] = parent_name
                    kps.append(normalized)
                    existing_ids.add(child_id)
                    existing_l3_name_set.add(child_name.lower())
                    applied_count += 1
                    ck = (parent_id, child_id, "contains")
                    if ck not in existing_contains:
                        relationships.append(
                            {
                                "start_id": parent_id,
                                "end_id": child_id,
                                "type": "contains",
                                "reason": "微调补充",
                            }
                        )
                        existing_contains.add(ck)
                self.log(f"ADD: 为 L2[{parent_name}] 新增 {applied_count} 个 L3")
            except Exception as e:
                self.log(f"ADD 失败: {e}", "warning")

            return {"kps": kps, "relationships": relationships}

        self.log(f"ADD跳过: 父节点既不是 L1 也不是 L2", "warning")
        return graph_data

    def _build_fallback_node_id(self, level: str, name: str, existing_ids: set) -> str:
        prefix = level.lower()
        raw = (name or "node").strip()
        digest = hashlib.md5(raw.encode("utf-8")).hexdigest()[:12]
        candidate = f"{prefix}_{digest}"
        idx = 1
        while candidate in existing_ids:
            candidate = f"{prefix}_{digest}_{idx}"
            idx += 1
        return candidate

    def _normalize_added_node(self, node: dict, child_level: str, existing_ids: set) -> dict:
        name = (node.get("name") or "").strip()
        description = (node.get("description") or node.get("definition") or "").strip()
        difficulty = node.get("difficulty", "中等")
        if difficulty not in {"基础", "中等", "高"}:
            difficulty = "中等"
        aliases = node.get("aliases", [])
        if not isinstance(aliases, list):
            aliases = []
        candidate_id = (node.get("id") or "").strip()
        if not candidate_id or not candidate_id.startswith(f"{child_level.lower()}_"):
            candidate_id = self._build_fallback_node_id(child_level, name, existing_ids)
        elif candidate_id in existing_ids:
            candidate_id = self._build_fallback_node_id(child_level, name, existing_ids)
        return {
            "id": candidate_id,
            "name": name,
            "level": child_level,
            "description": description,
            "definition": description,
            "difficulty": difficulty,
            "aliases": aliases,
            "source": "refinement",
        }

    def validate_relationships(self, kps: list, relationships: list) -> list:
        from knowledge_graph.agents.calibration import CalibrationAgent

        agent = CalibrationAgent(self.config)
        return agent.validate_and_calibrate_relationships(kps, relationships)

    def _resolve_existing_l1_id(self, kp_id: str, kps: List[Dict]) -> str:
        kp_id = (kp_id or "").strip()
        if not kp_id:
            return ""
        for kp in kps:
            if kp.get("id") == kp_id and kp.get("level") == "L1":
                return kp_id
        return ""

    def _resolve_l1_parent_from_name(self, name: str, kps: List[Dict]) -> str:
        name = (name or "").strip()
        if not name:
            return ""
        for kp in kps:
            if kp.get("level") == "L1" and kp.get("name") == name:
                return kp.get("id", "")
        return ""

    def _resolve_l1_parent_from_source(self, source: str, kps: List[Dict]) -> str:
        source = (source or "").strip()
        marker = "L1簇:"
        idx = source.find(marker)
        if idx < 0:
            return ""
        l1_name = source[idx + len(marker) :].strip()
        for kp in kps:
            if kp.get("level") == "L1" and kp.get("name") == l1_name:
                return kp.get("id", "")
        return ""

    def _graph_metrics(self, graph_data: dict) -> Dict[str, int]:
        kps = graph_data.get("kps", [])
        relationships = graph_data.get("relationships", [])
        return {
            "kp_count": len(kps),
            "rel_count": len(relationships),
            "isolated_count": len(self.find_isolated_nodes(kps, relationships)),
        }

    def _isolated_id_set(self, graph_data: dict) -> set:
        isolated = self.find_isolated_nodes(graph_data.get("kps", []), graph_data.get("relationships", []))
        return {n.get("id", "") for n in isolated if n.get("id")}

    def execute(self, state: AgentState) -> AgentState:
        self.log("开始图谱微调（ADD / DELETE / MERGE）")

        evaluation_report = state.get("evaluation_report", {})
        if not evaluation_report:
            self.log("无评估报告，跳过微调", "warning")
            return state

        graph_data = self.load_current_graph(state)
        graph_data["relationships"] = self.validate_relationships(graph_data["kps"], graph_data["relationships"])

        sparse_topics = self.find_sparse_topics(graph_data["kps"], graph_data["relationships"])
        current_sparse_l1_ids = {t.get("id", "") for t in sparse_topics if t.get("id")}
        sparse_l1_by_name = {t.get("name", ""): t for t in sparse_topics if t.get("name")}
        sparse_l1_by_id = {t.get("id", ""): t for t in sparse_topics if t.get("id")}

        plan = self.generate_refinement_plan(evaluation_report, graph_data)
        actions = plan.get("actions", [])
        if not actions:
            self.log("无微调操作")
            state["tuning_summary"] = {"applied": False, "reason": "no_actions"}
            return state

        applied_actions = 0
        actions = _sort_actions(actions)
        applied_detail: List[Dict[str, Any]] = []

        for action in actions:
            action_type = str(action.get("type", "")).upper()
            target_id = (action.get("target_id") or "").strip()
            target_name = (action.get("target") or "").strip()
            source = (action.get("source") or "").strip()
            source_id = (action.get("source_id") or "").strip()
            before_graph = copy.deepcopy(graph_data)
            before_kp_ids = {kp.get("id", "") for kp in before_graph.get("kps", []) if kp.get("id")}
            action_applied = False

            if action_type == "MERGE":
                keep_id = (action.get("keep_id") or target_id or "").strip()
                remove_id = (action.get("remove_id") or source_id or "").strip()
                if keep_id and remove_id and keep_id != remove_id:
                    kps_before = len(graph_data.get("kps", []))
                    graph_data["kps"], graph_data["relationships"] = self.merge_two_kp_ids(
                        keep_id, remove_id, graph_data.get("kps", []), graph_data.get("relationships", [])
                    )
                    graph_data["relationships"] = self.validate_relationships(
                        graph_data["kps"], graph_data["relationships"]
                    )
                    self.log(
                        f"MERGE: 合并节点 {remove_id} -> {keep_id} (kps {kps_before}->{len(graph_data.get('kps', []))})"
                    )
                    action_applied = len(graph_data.get("kps", [])) < kps_before
                else:
                    self.log("MERGE 跳过: 缺少 keep_id/remove_id（或与 target_id/source_id 等价字段）", "warning")

            elif action_type == "ADD":
                focus = (action.get("focus") or "").strip()
                parent_id_in = (action.get("parent_id") or action.get("target_id") or "").strip()
                parent_display = (action.get("parent_name") or target_name or "").strip()
                pid, pname, fh = self._resolve_add_parent(
                    graph_data["kps"],
                    sparse_l1_by_id,
                    sparse_l1_by_name,
                    current_sparse_l1_ids,
                    parent_id_raw=parent_id_in,
                    target_id_raw="",
                    target_name=parent_display,
                    focus=focus,
                )
                if not pid:
                    l1_from_source = self._resolve_l1_parent_from_source(source, graph_data["kps"])
                    if l1_from_source:
                        for kp in graph_data["kps"]:
                            if kp.get("id") == l1_from_source:
                                pid = l1_from_source
                                pname = kp.get("name", "")
                                break
                if not pid:
                    self.log(
                        f"ADD 跳过: 无法解析父节点（parent_id={parent_id_in}, target_id={target_id}, parent_name/target={parent_display}）",
                        "warning",
                    )
                else:
                    merged_focus = (fh or focus).strip()
                    kps_before_add = len(graph_data.get("kps", []))
                    graph_data = self.execute_add(pid, pname, graph_data, focus_hint=merged_focus)
                    graph_data["relationships"] = self.validate_relationships(
                        graph_data["kps"], graph_data["relationships"]
                    )
                    action_applied = len(graph_data.get("kps", [])) > kps_before_add
                    sparse_topics = self.find_sparse_topics(graph_data["kps"], graph_data["relationships"])
                    current_sparse_l1_ids = {t.get("id", "") for t in sparse_topics if t.get("id")}
                    sparse_l1_by_name = {t.get("name", ""): t for t in sparse_topics if t.get("name")}
                    sparse_l1_by_id = {t.get("id", ""): t for t in sparse_topics if t.get("id")}

            elif action_type == "DELETE":
                kps_before_del = len(graph_data.get("kps", []))
                del_display_name = (action.get("target_name") or target_name or "").strip()
                graph_data = self.execute_delete(target_id, del_display_name, graph_data)
                graph_data["relationships"] = self.validate_relationships(
                    graph_data["kps"], graph_data["relationships"]
                )
                action_applied = len(graph_data.get("kps", [])) < kps_before_del

            else:
                self.log(f"未知动作: {action_type}", "warning")
                continue

            if action_applied and action_type == "ADD":
                after_kp_ids = {kp.get("id", "") for kp in graph_data.get("kps", []) if kp.get("id")}
                added_ids = after_kp_ids - before_kp_ids
                added_isolated = added_ids & self._isolated_id_set(graph_data)
                if added_isolated:
                    self.log(f"ADD 回滚: 新增节点孤立", "warning")
                    graph_data = before_graph
                    continue

            if action_applied:
                applied_actions += 1
                applied_detail.append(
                    {
                        "type": action_type,
                        "source_id": source_id,
                        "target_id": target_id,
                        "target": target_name,
                        "source": source,
                    }
                )

        state["calibrated_kps"] = graph_data["kps"]
        state["calibrated_relationships"] = graph_data["relationships"]
        state["calibrated_resources"] = []

        self.save_parquet(graph_data["kps"], "data/output/calibrated_entities.parquet")
        self.save_parquet(graph_data["relationships"], "data/output/calibrated_relationships.parquet")

        self.log(f"微调完成: 知识点={len(graph_data['kps'])}, 关系={len(graph_data['relationships'])}")

        state["tuning_summary"] = {
            "applied": applied_actions > 0,
            "actions_count": len(actions),
            "applied_actions_count": applied_actions,
            "actions": applied_detail,
            "new_kps": len(graph_data["kps"]),
            "new_relationships": len(graph_data["relationships"]),
        }
        return state


def create_refinement_agent(config: dict) -> GraphRefinementAgent:
    return GraphRefinementAgent(config)
