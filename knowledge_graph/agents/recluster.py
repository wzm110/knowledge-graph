#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Node 6.5: L2重聚合智能体
在校准后对每个L1簇执行重聚合：
- 原L2下沉为L3（保留ID）
- 原L3下沉为L4（保留ID）
- 新建不超过10个聚合L2并挂载到L1
"""

import copy
import json
from typing import Dict, List, Set

from knowledge_graph.agents.base_agent import LLMAgent, AgentState


class GraphReclusterAgent(LLMAgent):
    """校准后L2重聚合智能体"""

    def __init__(self, config: dict):
        # 初始化重聚合智能体并绑定统一提示词模板。
        super().__init__(name="GraphRecluster", config=config, prompt_path="prompts/Recluster_Prompt.txt")

    def _kp_map(self, kps: List[Dict]) -> Dict[str, Dict]:
        # 构建实体ID到实体对象的快速索引表。
        return {kp.get('id', ''): kp for kp in kps if kp.get('id')}

    def _dedupe_relationships(self, relationships: List[Dict]) -> List[Dict]:
        # 对关系按(type,start_id,end_id)去重，避免重复边。
        seen = set()
        out = []
        for rel in relationships:
            key = (rel.get('type', ''), rel.get('start_id', ''), rel.get('end_id', ''))
            if key in seen:
                continue
            seen.add(key)
            out.append(rel)
        return out

    def _strip_one_level_prefix(self, node_id: str) -> str:
        body = node_id or ""
        for p in ("l4_", "l3_", "l2_", "l1_"):
            if body.startswith(p):
                return body[len(p) :]
        return body

    def _allocate_prefixed_id(self, oid: str, prefix: str, reserved: Set[str]) -> str:
        body = self._strip_one_level_prefix(oid)
        if not body:
            body = oid or "node"
        cand = prefix + body
        if cand not in reserved:
            return cand
        i = 1
        while f"{cand}_{i}" in reserved:
            i += 1
        return f"{cand}_{i}"

    def _apply_sink_id_renames(
        self,
        kps: List[Dict],
        relationships: List[Dict],
        old_l2_ids: Set[str],
        old_l3_ids: Set[str],
    ) -> None:
        """原 L2 下沉为 L3、原 L3 下沉为 L4 后，将 id 前缀规范为 l3_/l4_，并同步全图引用。"""
        reserved: Set[str] = {kp.get("id", "") for kp in kps if kp.get("id")}
        renames: Dict[str, str] = {}

        for oid in sorted(old_l2_ids):
            if oid not in reserved:
                continue
            nid = self._allocate_prefixed_id(oid, "l3_", reserved)
            if nid != oid:
                renames[oid] = nid
                reserved.discard(oid)
                reserved.add(nid)

        for oid in sorted(old_l3_ids):
            if oid not in reserved:
                continue
            nid = self._allocate_prefixed_id(oid, "l4_", reserved)
            if nid != oid:
                renames[oid] = nid
                reserved.discard(oid)
                reserved.add(nid)

        if not renames:
            return

        for kp in kps:
            rid = kp.get("id", "")
            if rid in renames:
                kp["id"] = renames[rid]
            pid = kp.get("parent_id", "")
            if pid in renames:
                kp["parent_id"] = renames[pid]
        for rel in relationships:
            s, e = rel.get("start_id", ""), rel.get("end_id", "")
            if s in renames:
                rel["start_id"] = renames[s]
            if e in renames:
                rel["end_id"] = renames[e]

        self.log(f"下沉节点 id 前缀规范化: 共重命名 {len(renames)} 个 id")

    def _build_cluster_prompt(self, l1: Dict, old_l2_nodes: List[Dict]) -> str:
        # 使用外置提示词模板组装本次L1簇聚合请求。
        max_l2_per_l1 = int(self.config.get('recluster', {}).get('max_l2_per_l1', 10))
        l2_payload = [
            {
                "id": n.get("id", ""),
                "name": n.get("name", ""),
                "definition": n.get("definition", "")[:200],
                "aliases": n.get("aliases", []) if isinstance(n.get("aliases", []), list) else []
            }
            for n in old_l2_nodes
        ]
        template = self.load_prompt()
        if not template:
            return ""
        prompt = template.replace("{max_l2_per_l1}", str(max_l2_per_l1))
        prompt = prompt.replace("{l1_json}", json.dumps({"id": l1.get("id", ""), "name": l1.get("name", "")}, ensure_ascii=False, indent=2))
        prompt = prompt.replace("{old_l2_json}", json.dumps(l2_payload, ensure_ascii=False, indent=2))
        return prompt

    def _fallback_clusters(self, old_l2_nodes: List[Dict], l1_name: str) -> Dict:
        # 当LLM不可用或结果非法时，构造可执行的兜底聚合结果。
        max_l2_per_l1 = int(self.config.get('recluster', {}).get('max_l2_per_l1', 10))
        total = len(old_l2_nodes)
        bucket_count = min(max_l2_per_l1, max(1, total))
        buckets: List[List[Dict]] = [[] for _ in range(bucket_count)]
        for idx, node in enumerate(old_l2_nodes):
            buckets[idx % bucket_count].append(node)

        new_l2_nodes = []
        mapping = []
        for idx, bucket in enumerate(buckets, start=1):
            cluster_id = f"l2_cluster_{l1_name}_{idx}".replace(" ", "_")
            new_l2_nodes.append({
                "id": cluster_id,
                "name": f"{l1_name}-聚合主题{idx}",
                "level": "L2",
                "definition": f"{l1_name}的聚合主题簇{idx}",
                "difficulty": "中等",
                "aliases": []
            })
            mapping.append({
                "new_l2_id": cluster_id,
                "old_l2_ids": [n.get("id", "") for n in bucket if n.get("id")]
            })
        return {
            "new_l2_nodes": new_l2_nodes,
            "mapping": mapping,
            "new_l2_prerequisites": []
        }

    def _parse_cluster_result(self, response: str, old_l2_ids: List[str], l1_name: str, old_l2_nodes: List[Dict]) -> Dict:
        # 解析并规范化LLM聚合结果，强制old_l2_id单归属。
        try:
            result = json.loads(response or "{}")
        except Exception:
            result = self._fallback_clusters(old_l2_nodes, l1_name)

        new_l2_nodes = result.get("new_l2_nodes", [])
        mapping = result.get("mapping", [])
        prereqs = result.get("new_l2_prerequisites", [])

        if not isinstance(new_l2_nodes, list) or not new_l2_nodes:
            return self._fallback_clusters(old_l2_nodes, l1_name)
        if not isinstance(mapping, list):
            mapping = []
        if not isinstance(prereqs, list):
            prereqs = []

        max_l2_per_l1 = int(self.config.get('recluster', {}).get('max_l2_per_l1', 10))
        new_l2_nodes = new_l2_nodes[:max_l2_per_l1]
        valid_new_ids = set()
        normalized_new = []
        for idx, node in enumerate(new_l2_nodes, start=1):
            if not isinstance(node, dict):
                continue
            nid = (node.get("id") or f"l2_cluster_{l1_name}_{idx}").strip()
            nname = (node.get("name") or f"{l1_name}-聚合主题{idx}").strip()
            if not nid:
                continue
            valid_new_ids.add(nid)
            normalized_new.append({
                "id": nid,
                "name": nname,
                "level": "L2",
                "definition": (node.get("definition") or node.get("description") or nname).strip(),
                "difficulty": node.get("difficulty") if node.get("difficulty") in {"基础", "中等", "高"} else "中等",
                "aliases": node.get("aliases") if isinstance(node.get("aliases"), list) else [],
                "source": "recluster"
            })

        owner: Dict[str, str] = {}
        for item in mapping:
            if not isinstance(item, dict):
                continue
            nid = (item.get("new_l2_id") or "").strip()
            if nid not in valid_new_ids:
                continue
            old_ids = item.get("old_l2_ids", [])
            if not isinstance(old_ids, list):
                continue
            for old_id in old_ids:
                if old_id in old_l2_ids and old_id not in owner:
                    owner[old_id] = nid

        if normalized_new and len(owner) < len(old_l2_ids):
            default_id = normalized_new[0]["id"]
            for old_id in old_l2_ids:
                if old_id not in owner:
                    owner[old_id] = default_id

        normalized_mapping = {}
        for old_id, nid in owner.items():
            normalized_mapping.setdefault(nid, []).append(old_id)

        normalized_prereq = []
        for rel in prereqs:
            if not isinstance(rel, dict):
                continue
            sid = (rel.get("start_id") or "").strip()
            eid = (rel.get("end_id") or "").strip()
            if sid in valid_new_ids and eid in valid_new_ids and sid != eid:
                normalized_prereq.append({
                    "type": "prerequisite",
                    "start_id": sid,
                    "end_id": eid,
                    "reason": rel.get("reason", "重聚合前置关系")
                })

        return {
            "new_l2_nodes": normalized_new,
            "mapping": normalized_mapping,
            "new_l2_prerequisites": normalized_prereq
        }

    def _apply_one_l1_recluster(self, l1: Dict, graph_data: Dict) -> Dict:
        # 对单个L1簇执行一次完整重聚合与层级下沉。
        kps = graph_data["kps"]
        relationships = graph_data["relationships"]
        l1_id = l1.get("id", "")
        l1_name = l1.get("name", "")
        if not l1_id:
            return graph_data

        kp_map = self._kp_map(kps)
        old_l2_ids = [
            r.get("end_id", "")
            for r in relationships
            if r.get("type") == "contains" and r.get("start_id") == l1_id and kp_map.get(r.get("end_id", ""), {}).get("level") == "L2"
        ]
        old_l2_ids = [x for x in old_l2_ids if x]
        if not old_l2_ids:
            return graph_data

        old_l2_nodes = [kp_map[l2id] for l2id in old_l2_ids if l2id in kp_map]
        prompt = self._build_cluster_prompt(l1, old_l2_nodes)
        if not prompt.strip():
            self.log("重聚合提示词为空，使用兜底聚合", "warning")
            parsed = self._fallback_clusters(old_l2_nodes, l1_name or "l1")
        else:
            response = self.call_llm(prompt, "")
            parsed = self._parse_cluster_result(response, old_l2_ids, l1_name or "l1", old_l2_nodes)

        new_l2_nodes = parsed["new_l2_nodes"]
        mapping = parsed["mapping"]  # Dict[new_l2_id, List[old_l2_id]]
        new_l2_prereq = parsed["new_l2_prerequisites"]

        if not new_l2_nodes:
            return graph_data

        existing_ids = {kp.get("id", "") for kp in kps if kp.get("id")}
        for node in new_l2_nodes:
            nid = node["id"]
            if nid in existing_ids:
                idx = 1
                while f"{nid}_{idx}" in existing_ids:
                    idx += 1
                node["id"] = f"{nid}_{idx}"
            existing_ids.add(node["id"])

        mapping_fixed = {}
        for node in new_l2_nodes:
            nid = node["id"]
            if nid in mapping:
                mapping_fixed[nid] = mapping[nid]
        if not mapping_fixed:
            # fallback：全部挂到第一个新L2
            mapping_fixed[new_l2_nodes[0]["id"]] = old_l2_ids

        # 1) 下沉层级：old L2 -> L3
        old_l2_set = set(old_l2_ids)
        old_l3_set = {
            r.get("end_id", "")
            for r in relationships
            if r.get("type") == "contains" and r.get("start_id") in old_l2_set
        }
        old_l3_set = {x for x in old_l3_set if x and kp_map.get(x, {}).get("level") == "L3"}

        for kp in kps:
            kid = kp.get("id", "")
            if kid in old_l2_set:
                kp["level"] = "L3"
            elif kid in old_l3_set:
                kp["level"] = "L4"

        # 2) 删除旧 L1->oldL2 contains
        relationships = [
            r for r in relationships
            if not (r.get("type") == "contains" and r.get("start_id") == l1_id and r.get("end_id") in old_l2_set)
        ]

        # 3) 添加新L2节点
        for node in new_l2_nodes:
            kps.append({
                "id": node["id"],
                "name": node["name"],
                "level": "L2",
                "definition": node["definition"],
                "difficulty": node.get("difficulty", "中等"),
                "aliases": node.get("aliases", []),
                "source": "recluster",
                "parent_id": l1_id,
                "parent_name": l1_name
            })

        # 4) 建立 L1->newL2 contains
        for node in new_l2_nodes:
            relationships.append({
                "type": "contains",
                "start_id": l1_id,
                "end_id": node["id"],
                "reason": "L2重聚合"
            })

        # 5) 建立 newL2 -> oldL2(now L3) contains
        owner_of_old = {}
        for new_l2_id, old_ids in mapping_fixed.items():
            for old_id in old_ids:
                if old_id in old_l2_set and old_id not in owner_of_old:
                    owner_of_old[old_id] = new_l2_id
                    relationships.append({
                        "type": "contains",
                        "start_id": new_l2_id,
                        "end_id": old_id,
                        "reason": "L2重聚合下沉"
                    })

        # 6) 设置 oldL2 的父信息
        kp_lookup = self._kp_map(kps)
        for old_id, new_l2_id in owner_of_old.items():
            if old_id in kp_lookup:
                kp_lookup[old_id]["parent_id"] = new_l2_id
                kp_lookup[old_id]["parent_name"] = kp_lookup.get(new_l2_id, {}).get("name", "")

        # 7) 新L2之间前置关系
        relationships.extend(new_l2_prereq)
        relationships = self._dedupe_relationships(relationships)

        # 8) 下沉完成后统一 id 前缀（l3_/l4_），避免仍保留 l2_ 前缀的「假 L3/L4」
        self._apply_sink_id_renames(kps, relationships, old_l2_set, old_l3_set)

        self.log(
            f"重聚合[{l1_name}]: 原L2={len(old_l2_set)} -> 新L2={len(new_l2_nodes)}, "
            f"L3下沉={len(old_l2_set)}, L4下沉={len(old_l3_set)}"
        )

        return {
            "kps": kps,
            "relationships": relationships,
            "resources": graph_data.get("resources", [])
        }

    def execute(self, state: AgentState) -> AgentState:
        # 在校准后执行一次全图重聚合，并回写calibrated产物。
        if state.get("recluster_applied", False):
            self.log("重聚合已执行过，本轮跳过（防重复下沉）")
            return state

        self.log("开始校准后L2重聚合")
        kps = state.get("calibrated_kps", []) or self.load_parquet("data/output/calibrated_entities.parquet")
        rels = state.get("calibrated_relationships", []) or self.load_parquet("data/output/calibrated_relationships.parquet")
        # 资源不入图；勿用「[] or parquet」以免空列表误读旧 calibrated_resources.parquet
        resources = []

        if not kps or not rels:
            self.log("重聚合跳过：缺少校准后实体或关系", "warning")
            return state

        graph_data = {"kps": copy.deepcopy(kps), "relationships": copy.deepcopy(rels), "resources": copy.deepcopy(resources)}
        l1_list = [kp for kp in graph_data["kps"] if kp.get("level") == "L1"]

        for l1 in l1_list:
            before = copy.deepcopy(graph_data)
            try:
                graph_data = self._apply_one_l1_recluster(l1, graph_data)
            except Exception as e:
                self.log(f"重聚合失败，回滚该L1簇: {l1.get('name', '')}, error={e}", "warning")
                graph_data = before

        state["calibrated_kps"] = graph_data["kps"]
        state["calibrated_relationships"] = graph_data["relationships"]
        state["calibrated_resources"] = graph_data["resources"]
        state["current_step"] = "recluster"
        state["recluster_applied"] = True

        self.save_parquet(graph_data["kps"], "data/output/calibrated_entities.parquet")
        self.save_parquet(graph_data["relationships"], "data/output/calibrated_relationships.parquet")

        self.log(
            f"重聚合完成: 知识点={len(graph_data['kps'])}, 关系={len(graph_data['relationships'])}"
        )
        return state


def create_recluster_agent(config: dict) -> GraphReclusterAgent:
    """工厂函数：创建重聚合智能体"""
    # 统一创建并返回重聚合智能体实例。
    return GraphReclusterAgent(config)

