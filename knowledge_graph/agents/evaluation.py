#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Node 7: 评测智能体
使用LLM评估知识图谱质量，并给出可执行修复建议
"""

import json
import os
from datetime import datetime
from typing import Any, Dict, List

import networkx as nx
from collections import Counter

from knowledge_graph.agents.base_agent import LLMAgent, AgentState


class EvaluationAgent(LLMAgent):
    """评估知识图谱质量的智能体"""

    def __init__(self, config: dict):
        super().__init__(
            name="Evaluation",
            config=config,
            prompt_path="prompts/Evaluation_Prompt.txt"
        )

    def analyze_graph_structure(self, kps, relationships):
        """分析图谱结构，计算结构指标"""
        if not kps or not relationships:
            return {}
        
        G = nx.DiGraph()
        
        for kp in kps:
            kp_id = kp.get('id', '')
            if kp_id:
                G.add_node(kp_id, level=kp.get('level', ''), name=kp.get('name', ''))
        
        for rel in relationships:
            start = rel.get('start_id', '')
            end = rel.get('end_id', '')
            if start and end:
                G.add_edge(start, end, rel_type=rel.get('type', ''))
        
        if G.number_of_nodes() == 0:
            return {}
        
        try:
            undirected = G.to_undirected()
            
            connected_components = list(nx.connected_components(undirected))
            largest_cc = max(connected_components, key=len) if connected_components else set()
            
            in_degrees = dict(G.in_degree())
            out_degrees = dict(G.out_degree())
            all_degrees = {n: in_degrees.get(n, 0) + out_degrees.get(n, 0) for n in G.nodes()}
            
            degree_values = list(all_degrees.values())
            avg_degree = sum(degree_values) / len(degree_values) if degree_values else 0
            
            level_counts = Counter()
            for kp in kps:
                level = kp.get('level', 'Unknown')
                level_counts[level] += 1
            
            rel_type_counts = Counter()
            for rel in relationships:
                rel_type = rel.get('type', 'unknown')
                rel_type_counts[rel_type] += 1
            
            l1_ids = {kp['id'] for kp in kps if kp.get('level') == 'L1'}
            l2_ids = {kp['id'] for kp in kps if kp.get('level') == 'L2'}
            l3_ids = {kp['id'] for kp in kps if kp.get('level') == 'L3'}
            
            l1_to_l2 = sum(1 for r in relationships if r.get('start_id') in l1_ids and r.get('end_id') in l2_ids)
            l2_to_l3 = sum(1 for r in relationships if r.get('start_id') in l2_ids and r.get('end_id') in l3_ids)
            
            return {
                'node_count': G.number_of_nodes(),
                'edge_count': G.number_of_edges(),
                'connected_components': len(connected_components),
                'largest_component_size': len(largest_cc),
                'largest_component_ratio': len(largest_cc) / G.number_of_nodes() if G.number_of_nodes() > 0 else 0,
                'avg_degree': round(avg_degree, 2),
                'max_degree': max(degree_values) if degree_values else 0,
                'min_degree': min(degree_values) if degree_values else 0,
                'level_distribution': dict(level_counts),
                'rel_type_distribution': dict(rel_type_counts),
                'l1_to_l2_relations': l1_to_l2,
                'l2_to_l3_relations': l2_to_l3,
                'isolated_nodes': sum(1 for d in all_degrees.values() if d == 0)
            }
        except Exception as e:
            self.log(f"图结构分析错误: {e}", "warning")
            return {}

    def analyze_hierarchy_quality(self, kps, relationships):
        """分析层级结构质量"""
        if not kps:
            return {}
        
        l1_kps = [kp for kp in kps if kp.get('level') == 'L1']
        l2_kps = [kp for kp in kps if kp.get('level') == 'L2']
        l3_kps = [kp for kp in kps if kp.get('level') == 'L3']
        
        l1_ids = {kp['id'] for kp in l1_kps}
        l2_ids = {kp['id'] for kp in l2_kps}
        l3_ids = {kp['id'] for kp in l3_kps}
        
        l2_with_parent = 0
        l3_with_parent = 0
        
        for rel in relationships:
            if rel.get('type') == 'contains':
                if rel.get('end_id') in l2_ids and rel.get('start_id') in l1_ids:
                    l2_with_parent += 1
                if rel.get('end_id') in l3_ids and rel.get('start_id') in l2_ids:
                    l3_with_parent += 1
        
        l2_with_parent_ratio = l2_with_parent / len(l2_kps) if l2_kps else 0
        l3_with_parent_ratio = l3_with_parent / len(l3_kps) if l3_kps else 0
        
        return {
            'l1_count': len(l1_kps),
            'l2_count': len(l2_kps),
            'l3_count': len(l3_kps),
            'l2_with_parent_ratio': round(l2_with_parent_ratio, 2),
            'l3_with_parent_ratio': round(l3_with_parent_ratio, 2),
            'avg_l2_per_l1': len(l2_kps) / len(l1_kps) if l1_kps else 0,
            'avg_l3_per_l2': len(l3_kps) / len(l2_kps) if l2_kps else 0
        }

    def analyze_relation_quality(self, relationships):
        """分析关系质量"""
        if not relationships:
            return {}
        
        rel_types = Counter()
        for rel in relationships:
            rel_type = rel.get('type', 'unknown')
            rel_types[rel_type] += 1
        
        prerequisite_count = rel_types.get('prerequisite', 0)
        contains_count = rel_types.get('contains', 0)
        
        total = len(relationships)
        
        return {
            'total_relations': total,
            'prerequisite_ratio': prerequisite_count / total if total > 0 else 0,
            'contains_ratio': contains_count / total if total > 0 else 0,
            'prerequisite_count': prerequisite_count,
            'contains_count': contains_count
        }

    def analyze_source_coverage(self, state: AgentState, l1_distribution: dict) -> dict:
        """分析源数据覆盖，帮助LLM区分'数据缺失'与'抽取/校准问题'"""
        textbook_data = state.get('textbook_data', []) or []
        chapter_titles = [item.get('chapter_title', '') for item in textbook_data if item.get('chapter_title')]
        all_titles = "\n".join(chapter_titles).lower()

        # 针对稀疏主题提供关键词命中证据（轻量启发式）
        coverage_keywords = {
            "生成模型与无监督学习": ["生成", "扩散", "gan", "vae", "无监督", "自监督"],
            "迁移学习与元学习": ["迁移", "微调", "元学习", "few-shot", "小样本"]
        }

        sparse_l1_coverage = {}
        for l1_name, counts in l1_distribution.items():
            total = counts.get('total', 0)
            if total <= 5:
                keywords = coverage_keywords.get(l1_name, [])
                hits = {}
                for kw in keywords:
                    hits[kw] = all_titles.count(kw.lower())
                sparse_l1_coverage[l1_name] = {
                    'topic_total_nodes': total,
                    'keywords': keywords,
                    'title_keyword_hits': hits,
                    'chapter_count': len(chapter_titles)
                }

        return {
            'chapter_count': len(chapter_titles),
            'sparse_l1_coverage': sparse_l1_coverage
        }

    def _normalize_evaluation_result(self, result: dict) -> dict:
        """兼容旧响应结构并补齐关键字段"""
        if not isinstance(result, dict):
            return {}

        result.setdefault('overall_score', 0)
        result.setdefault('dimensions', {})
        result.setdefault('strengths', [])
        result.setdefault('weaknesses', [])
        result.setdefault('improvement_suggestions', [])
        result.setdefault('root_cause_analysis', [])
        result.setdefault('adjustment_suggestions', [])
        result.setdefault('blocking_issues', [])

        # is_passed 先留空，后续结合簇评测结果一起决定
        return result

        return result

    def _collect_over_limit_l1_topics(self, data: dict, kps: list) -> list:
        """收集超过L2上限的L1主题（L2数量>10）及其ID。"""
        over_limit_topics = []
        try:
            l1_distribution = json.loads(data.get('l1_distribution', '{}'))
        except Exception:
            l1_distribution = {}

        name_to_id = {
            kp.get('name', ''): kp.get('id', '')
            for kp in kps
            if kp.get('level') == 'L1' and kp.get('name')
        }

        for l1_name, counts in l1_distribution.items():
            l2_count = int((counts or {}).get('l2_count', 0) or 0)
            if l2_count > 10:
                over_limit_topics.append({
                    'name': l1_name,
                    'id': name_to_id.get(l1_name, ''),
                    'l2_count': l2_count
                })

        return over_limit_topics

    def _enforce_l2_cap_gate(self, result: dict, over_limit_topics: list) -> dict:
        """L2上限硬门槛：存在L2>10的L1主题时必须评测不通过（不自动注入 MERGE 建议）。"""
        if not over_limit_topics:
            return result

        result['is_passed'] = False

        blocking_issues = result.get('blocking_issues', [])
        if not isinstance(blocking_issues, list):
            blocking_issues = [str(blocking_issues)]
        blocking_msg = (
            f"存在 {len(over_limit_topics)} 个L1主题超过L2上限（>10），"
            "必须先执行聚合/合并后再评测通过"
        )
        if blocking_msg not in blocking_issues:
            blocking_issues.append(blocking_msg)
        result['blocking_issues'] = blocking_issues

        result['pass_reason'] = "存在L1主题超过L2上限（>10），已强制不通过并要求先聚合"

        # 不再自动注入 MERGE 建议；超限时需人工或其它流程调整图结构

        return result

    def _parse_llm_result(self, response: str) -> dict:
        """解析评估LLM输出，失败时尝试自动修复JSON"""
        try:
            return json.loads(response)
        except Exception:
            repair_prompt = (
                "你是JSON修复助手。请将下面内容修复为严格合法JSON，"
                "不得新增字段、不得删减语义、不得输出解释，只输出JSON对象。"
            )
            repaired = self.call_llm(repair_prompt, response or "")
            if not repaired:
                raise
            return json.loads(repaired)

    def _generate_markdown_report(self, result: dict, data: dict) -> str:
        """生成 Markdown 格式的评测报告"""
        md = "# 知识图谱评测报告\n\n"
        final_score = result.get("final_score", result.get("overall_score", "N/A"))
        md += f"**最终评分**: {final_score}/10\n\n"
        md += f"**全局评分（LLM）**: {result.get('overall_score', 'N/A')}/10\n\n"
        md += f"**是否通过**: {'通过' if result.get('is_passed', False) else '未通过'}\n\n"
        md += f"**通过说明**: {result.get('pass_reason', 'N/A')}\n\n"
        
        md += "## L1主题层级分布\n\n"
        md += "| 主题 | L2数量 | L3数量 | 总计 |\n"
        md += "|-------|--------|--------|------|\n"
        
        import json
        l1_dist = json.loads(data.get('l1_distribution', '{}'))
        for name, counts in l1_dist.items():
            md += f"| {name} | {counts.get('l2_count', 0)} | {counts.get('l3_count', 0)} | {counts.get('total', 0)} |\n"
        
        md += "\n## 实体统计\n\n"
        md += f"- 知识点总数：{data.get('kp_count', 0)}\n"
        md += f"- L1知识点：{data.get('l1_count', 0)}\n"
        md += f"- L2知识点：{data.get('l2_count', 0)}\n"
        md += f"- L3知识点：{data.get('l3_count', 0)}\n"
        md += f"- 关系总数：{data.get('rel_count', 0)}\n"
        
        md += "\n## 维度评分\n\n"
        dimensions = result.get('dimensions', {})
        for dim_name, dim_data in dimensions.items():
            md += f"### {dim_name}\n"
            md += f"- **评分**: {dim_data.get('score', 'N/A')}/10\n"
            md += f"- **评价**: {dim_data.get('feedback', 'N/A')}\n\n"
        
        md += "## 优点\n\n"
        for strength in result.get('strengths', []):
            md += f"- {strength}\n"
        
        md += "\n## 问题\n\n"
        for weakness in result.get('weaknesses', []):
            md += f"- {weakness}\n"
        
        md += "\n## 改进建议\n\n"
        for suggestion in result.get('improvement_suggestions', []):
            md += f"- {suggestion}\n"
        
        md += "\n## 阻断问题\n\n"
        blocking = result.get('blocking_issues', [])
        if blocking:
            for issue in blocking:
                md += f"- {issue}\n"
        else:
            md += "- 无\n"

        md += "\n## 根因分析\n\n"
        root_causes = result.get('root_cause_analysis', [])
        if root_causes:
            for item in root_causes:
                md += (
                    f"- 问题: {item.get('issue', 'N/A')} | "
                    f"根因: {item.get('cause_type', 'unknown')} | "
                    f"证据: {item.get('evidence', 'N/A')}\n"
                )
        else:
            md += "- 无\n"

        md += "\n## 自动调整建议\n\n"
        adjustments = result.get('adjustment_suggestions', [])
        if adjustments:
            for item in adjustments:
                md += f"- {self._format_suggestion_line_for_md(item)}\n"
        else:
            md += "- 无\n"

        return md

    def _format_suggestion_line_for_md(self, s: Dict[str, Any]) -> str:
        """将单条 adjustment_suggestions 格式化为 Markdown 一行（id 与 name 同框）。"""
        if not isinstance(s, dict):
            return str(s)
        act = str(s.get("action", "") or "").upper()
        pr = s.get("priority", "low")
        rs = s.get("reason", "")
        if act == "ADD":
            return (
                f"ADD parent_id={s.get('parent_id', '')} parent_name={s.get('parent_name', '')} "
                f"focus={s.get('focus', '')} priority={pr} reason={rs}"
            )
        if act == "MERGE":
            return (
                f"MERGE keep_id={s.get('keep_id', '')} keep_name={s.get('keep_name', '')} "
                f"remove_id={s.get('remove_id', '')} remove_name={s.get('remove_name', '')} "
                f"priority={pr} reason={rs}"
            )
        if act == "DELETE":
            return (
                f"DELETE target_id={s.get('target_id', '')} target_name={s.get('target_name', '')} "
                f"delete_mode={s.get('delete_mode', '')} priority={pr} reason={rs}"
            )
        return f"action={s.get('action', '')} priority={pr} reason={rs}"

    def _save_evaluation_artifacts(self, result: dict, data: dict, cluster_details: list) -> None:
        """将评测数据保存到专用目录，便于回溯每轮评测细节。"""
        base_dir = 'data/output/evaluation'
        run_id = datetime.now().strftime('%Y%m%d_%H%M%S')
        run_dir = os.path.join(base_dir, run_id)
        os.makedirs(run_dir, exist_ok=True)

        bundle = {
            'run_id': run_id,
            'generated_at': datetime.now().isoformat(),
            'overall_result': result,
            'prepared_data': data,
            'cluster_results': cluster_details
        }

        # 历史快照
        latest_path = os.path.join(base_dir, 'latest.json')
        run_bundle_path = os.path.join(run_dir, 'bundle.json')
        run_result_path = os.path.join(run_dir, 'overall_result.json')
        run_data_path = os.path.join(run_dir, 'prepared_data.json')
        run_cluster_path = os.path.join(run_dir, 'cluster_results.json')
        run_md_path = os.path.join(run_dir, 'evaluation_report.md')
        clusters_md_dir = os.path.join(run_dir, "clusters")

        with open(latest_path, 'w', encoding='utf-8') as f:
            json.dump(bundle, f, ensure_ascii=False, indent=2)
        with open(run_bundle_path, 'w', encoding='utf-8') as f:
            json.dump(bundle, f, ensure_ascii=False, indent=2)
        with open(run_result_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        with open(run_data_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        with open(run_cluster_path, 'w', encoding='utf-8') as f:
            json.dump(cluster_details, f, ensure_ascii=False, indent=2)
        with open(run_md_path, 'w', encoding='utf-8') as f:
            f.write(self._generate_markdown_report(result, data))

        os.makedirs(clusters_md_dir, exist_ok=True)
        for c in cluster_details:
            if not isinstance(c, dict):
                continue
            l1_name = c.get("l1_name", "")
            if not l1_name:
                continue
            safe_name = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in l1_name)
            cluster_path = os.path.join(clusters_md_dir, f"{safe_name}.md")
            lines: List[str] = []
            lines.append(f"# L1 主题簇评测报告 - {l1_name}\n")
            lines.append(f"- **L1 ID**: {c.get('l1_id', '')}")
            lines.append(f"- **overall_score**: {c.get('overall_score', 'N/A')}")
            lines.append(f"- **L2 数量**: {c.get('l2_count', 'N/A')}\n")

            issues = c.get("issues", [])
            if issues:
                lines.append("## 发现的问题\n")
                for i in issues:
                    lines.append(
                        f"- [{i.get('severity', 'N/A')}] ({i.get('type', 'N/A')}) "
                        f"{i.get('description', '')} 建议: {i.get('suggestion', '')}"
                    )
                lines.append("")
            else:
                lines.append("## 发现的问题\n- 无\n")

            suggs = c.get("adjustment_suggestions", [])
            if suggs:
                lines.append("## 调整建议\n")
                for s in suggs:
                    lines.append(f"- {self._format_suggestion_line_for_md(s)}")
                lines.append("")
            else:
                lines.append("## 调整建议\n- 无\n")

            with open(cluster_path, "w", encoding="utf-8") as cf:
                cf.write("\n".join(lines))

        latest_dir = os.path.join("data/output", "final_evaluation")
        latest_clusters_dir = os.path.join(latest_dir, "clusters")
        os.makedirs(latest_dir, exist_ok=True)
        os.makedirs(latest_clusters_dir, exist_ok=True)

        with open(os.path.join(latest_dir, "overall_result.json"), "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        with open(os.path.join(latest_dir, "prepared_data.json"), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        with open(os.path.join(latest_dir, "cluster_results.json"), "w", encoding="utf-8") as f:
            json.dump(cluster_details, f, ensure_ascii=False, indent=2)
        with open(os.path.join(latest_dir, "evaluation_report.md"), "w", encoding="utf-8") as f:
            f.write(self._generate_markdown_report(result, data))

        for fname in os.listdir(latest_clusters_dir):
            if fname.lower().endswith(".md"):
                try:
                    os.remove(os.path.join(latest_clusters_dir, fname))
                except OSError:
                    pass
        for c in cluster_details:
            if not isinstance(c, dict):
                continue
            l1_name = c.get("l1_name", "")
            if not l1_name:
                continue
            safe_name = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in l1_name)
            cluster_path = os.path.join(latest_clusters_dir, f"{safe_name}.md")
            lines = [
                f"# L1 主题簇评测报告 - {l1_name}\n",
                f"- **L1 ID**: {c.get('l1_id', '')}",
                f"- **overall_score**: {c.get('overall_score', 'N/A')}",
                f"- **L2 数量**: {c.get('l2_count', 'N/A')}\n",
            ]
            issues = c.get("issues", [])
            if issues:
                lines.append("## 发现的问题\n")
                for i in issues:
                    lines.append(
                        f"- [{i.get('severity', 'N/A')}] ({i.get('type', 'N/A')}) "
                        f"{i.get('description', '')} 建议: {i.get('suggestion', '')}"
                    )
                lines.append("")
            else:
                lines.append("## 发现的问题\n- 无\n")
            suggs = c.get("adjustment_suggestions", [])
            if suggs:
                lines.append("## 调整建议\n")
                for s in suggs:
                    lines.append(f"- {self._format_suggestion_line_for_md(s)}")
                lines.append("")
            else:
                lines.append("## 调整建议\n- 无\n")
            with open(cluster_path, "w", encoding="utf-8") as cf:
                cf.write("\n".join(lines))

        self.log(
            f"评测数据已保存到目录: {run_dir}（最新评估输出同步于 data/output/final_evaluation）"
        )

    def _attach_ids_to_suggestions(self, suggestions: list, kps: list) -> list:
        """
        规范化 adjustment_suggestions：
        - 按名称补全唯一 target_id / parent_id（兼容旧字段 target）；
        - 按图中节点为 ADD/MERGE/DELETE 补齐 parent_name、keep_name、remove_name、target_name（若模型漏写）。
        """
        if not isinstance(suggestions, list) or not suggestions:
            return suggestions

        name_to_ids: Dict[str, list] = {}
        for kp in kps:
            name = kp.get("name")
            kp_id = kp.get("id")
            if not name or not kp_id:
                continue
            name_to_ids.setdefault(name, []).append(kp_id)

        for s in suggestions:
            if not isinstance(s, dict):
                continue
            action = str(s.get("action", "")).upper()
            tid = str(s.get("target_id") or "").strip()
            tname = str(s.get("target") or "").strip()

            # ADD：仅有 target_id、未填 parent_id 时对齐（与图谱微调操作规范一致）
            if action == "ADD" and tid and not str(s.get("parent_id") or "").strip():
                s["parent_id"] = tid

            if tid or not tname:
                continue
            if " 与 " in tname:
                continue
            ids = [i for i in name_to_ids.get(tname, []) if i]
            if len(ids) != 1:
                continue
            s["target_id"] = ids[0]
            if action == "ADD" and not str(s.get("parent_id") or "").strip():
                s["parent_id"] = ids[0]

        id_to_name = {
            kp.get("id"): (kp.get("name") or "").strip()
            for kp in kps
            if kp.get("id")
        }
        _batch_delete_ids = frozenset(
            {
                "isolated_nodes_batch",
                "isolated_batch",
                "isolated_all",
                "all_isolated",
                "batch_isolated",
                "__isolated_batch__",
            }
        )
        for s in suggestions:
            if not isinstance(s, dict):
                continue
            action = str(s.get("action", "")).upper()
            if action == "ADD":
                pid = str(s.get("parent_id") or "").strip()
                if pid and not str(s.get("parent_name") or "").strip():
                    s["parent_name"] = id_to_name.get(pid, "")
            elif action == "MERGE":
                kid = str(s.get("keep_id") or "").strip()
                rid = str(s.get("remove_id") or "").strip()
                if kid and not str(s.get("keep_name") or "").strip():
                    s["keep_name"] = id_to_name.get(kid, "")
                if rid and not str(s.get("remove_name") or "").strip():
                    s["remove_name"] = id_to_name.get(rid, "")
            elif action == "DELETE":
                tid = str(s.get("target_id") or "").strip()
                if tid and tid not in _batch_delete_ids and not str(s.get("target_name") or "").strip():
                    s["target_name"] = id_to_name.get(tid, "")

        return suggestions

    def prepare_evaluation_data(self, state: AgentState) -> dict:
        """准备评估数据"""
        kps = state.get('calibrated_kps', [])
        raw_relationships = state.get('calibrated_relationships', [])
        # 评测阶段不包含资源（资源后续独立入图），同时过滤掉 has_resource 边，
        # 避免出现“资源数为 0 但仍存在 has_resource 关系”的矛盾输入
        relationships = [
            r for r in raw_relationships
            if r.get('type') != 'has_resource'
        ]
        resources = []
        
        l1_kps = [kp for kp in kps if kp.get('level') == 'L1']
        l2_kps = [kp for kp in kps if kp.get('level') == 'L2']
        l3_kps = [kp for kp in kps if kp.get('level') == 'L3']
        
        l1_distribution = {}
        for l1 in l1_kps:
            l1_id = l1.get('id', '')
            l1_name = l1.get('name', '')
            
            l2_ids = [r.get('end_id') for r in relationships 
                      if r.get('start_id') == l1_id and r.get('type') == 'contains']
            
            l3_count = 0
            for l2_id in l2_ids:
                l3_count += sum(1 for r in relationships 
                              if r.get('start_id') == l2_id and r.get('type') == 'contains')
            
            l1_distribution[l1_name] = {
                'l2_count': len(l2_ids),
                'l3_count': l3_count,
                'total': 1 + len(l2_ids) + l3_count
            }
        
        rel_types = {}
        for rel in relationships:
            rel_type = rel.get('type', 'unknown')
            rel_types[rel_type] = rel_types.get(rel_type, 0) + 1
        
        graph_structure = self.analyze_graph_structure(kps, relationships)
        hierarchy_quality = self.analyze_hierarchy_quality(kps, relationships)
        relation_quality = self.analyze_relation_quality(relationships)
        source_coverage = self.analyze_source_coverage(state, l1_distribution)
        
        connected_ids = set()
        for rel in relationships:
            connected_ids.add(rel.get('start_id', ''))
            connected_ids.add(rel.get('end_id', ''))
        isolated_count = sum(1 for kp in kps if kp.get('id', '') and kp.get('id', '') not in connected_ids)
        
        l1_id_catalog = [
            {"id": kp.get("id", ""), "name": (kp.get("name") or "").strip()}
            for kp in l1_kps
            if kp.get("id")
        ]

        return {
            'l1_list': [kp['name'] for kp in l1_kps],
            'l1_id_catalog': l1_id_catalog,
            'l1_distribution': json.dumps(l1_distribution, ensure_ascii=False, indent=2),
            'kp_count': len(kps),
            'l1_count': len(l1_kps),
            'l2_count': len(l2_kps),
            'l3_count': len(l3_kps),
            'rel_count': len(relationships),
            'isolated_count': isolated_count,
            'rel_types': json.dumps(rel_types, ensure_ascii=False),
            'graph_structure': json.dumps(graph_structure, ensure_ascii=False, indent=2),
            'hierarchy_quality': json.dumps(hierarchy_quality, ensure_ascii=False, indent=2),
            'relation_quality': json.dumps(relation_quality, ensure_ascii=False, indent=2),
            'source_coverage': json.dumps(source_coverage, ensure_ascii=False, indent=2)
        }

    def execute(self, state: AgentState) -> AgentState:
        """执行评估"""
        self.log("开始知识图谱评估")
        
        data = self.prepare_evaluation_data(state)
        
        prompt_template = self.load_prompt()
        
        prompt = prompt_template.replace("{l1_list}", json.dumps(data['l1_list'], ensure_ascii=False, indent=2))
        prompt = prompt.replace(
            "{l1_id_catalog}",
            json.dumps(data.get("l1_id_catalog", []), ensure_ascii=False, indent=2),
        )
        prompt = prompt.replace("{l1_distribution}", data['l1_distribution'])
        prompt = prompt.replace("{kp_count}", str(data['kp_count']))
        prompt = prompt.replace("{l1_count}", str(data['l1_count']))
        prompt = prompt.replace("{l2_count}", str(data['l2_count']))
        prompt = prompt.replace("{l3_count}", str(data['l3_count']))
        prompt = prompt.replace("{isolated_count}", str(data['isolated_count']))
        prompt = prompt.replace("{rel_count}", str(data['rel_count']))
        prompt = prompt.replace("{rel_types}", data['rel_types'])
        prompt = prompt.replace("{graph_structure}", data['graph_structure'])
        prompt = prompt.replace("{hierarchy_quality}", data['hierarchy_quality'])
        prompt = prompt.replace("{relation_quality}", data['relation_quality'])
        prompt = prompt.replace("{source_coverage}", data['source_coverage'])
        
        try:
            response = self.call_llm(prompt, "")
            result = self._normalize_evaluation_result(self._parse_llm_result(response))
            
            all_suggestions = list(result.get('adjustment_suggestions', []))
            all_issues = []
            cluster_details = []
            
            l1_names = data.get('l1_list', [])
            self.log(f"开始L1簇评估，共 {len(l1_names)} 个L1")
            
            cluster_prompt_template = self.load_prompt("prompts/Cluster_Evaluation_Prompt.txt")
            subject = str(self.config.get('pipeline', {}).get('subject', ''))
            
            kps = state.get('calibrated_kps', [])
            relationships = state.get('calibrated_relationships', [])
            
            for l1_name in l1_names:
                try:
                    l1_kp = next((kp for kp in kps if kp.get('name') == l1_name and kp.get('level') == 'L1'), None)
                    if not l1_kp:
                        continue
                    
                    l1_id = l1_kp.get('id', '')
                    
                    l2_ids = [r.get('end_id') for r in relationships 
                             if r.get('start_id') == l1_id and r.get('type') == 'contains']
                    l2_kps = [kp for kp in kps if kp.get('id') in l2_ids]
                    
                    tree_obj = {
                        "l1": {"id": l1_id, "name": l1_name},
                        "children": [],
                    }
                    for l2 in l2_kps:
                        l2_name = l2.get("name", "")
                        l2_id = l2.get("id", "")
                        l3_ids = [
                            r.get("end_id")
                            for r in relationships
                            if r.get("start_id") == l2_id and r.get("type") == "contains"
                        ]
                        l3_kps = [kp for kp in kps if kp.get("id") in l3_ids]
                        l2_node = {
                            "id": l2_id,
                            "name": l2_name,
                            "level": "L2",
                            "children": [
                                {
                                    "id": kp.get("id", ""),
                                    "name": kp.get("name", ""),
                                    "level": kp.get("level") or "L3",
                                    "children": [],
                                }
                                for kp in l3_kps
                            ],
                        }
                        tree_obj["children"].append(l2_node)

                    l2_l3_tree = json.dumps(tree_obj, ensure_ascii=False, indent=2)
                    
                    cluster_prompt = cluster_prompt_template.replace("{l1_name}", l1_name)
                    cluster_prompt = cluster_prompt.replace("{l2_l3_tree}", l2_l3_tree)
                    cluster_prompt = cluster_prompt.replace("{subject}", subject)
                    
                    cluster_response = self.call_llm(cluster_prompt, f"cluster_{l1_name}")
                    cluster_result = json.loads(cluster_response)
                    cluster_score = cluster_result.get('overall_score', 0)
                    
                    cluster_suggestions = cluster_result.get('adjustment_suggestions', [])
                    for s in cluster_suggestions:
                        s['source'] = f"L1簇:{l1_name}"
                    all_suggestions.extend(cluster_suggestions)
                    
                    issues = cluster_result.get('issues', [])
                    for i in issues:
                        i['source'] = f"L1簇:{l1_name}"
                    all_issues.extend(issues)

                    cluster_details.append({
                        'l1_name': l1_name,
                        'l1_id': l1_id,
                        'overall_score': cluster_score,
                        'issues': issues,
                        'adjustment_suggestions': cluster_suggestions,
                        'l2_count': len(l2_ids)
                    })

                    self.log(f"  簇评估 [{l1_name}]: score={cluster_score}")
                    
                except Exception as e:
                    self.log(f"  簇评估失败 [{l1_name}]: {e}", "warning")
                    cluster_details.append({
                        'l1_name': l1_name,
                        'error': str(e)
                    })
            
            # 汇总全局与各簇的调整建议/问题
            result['adjustment_suggestions'] = all_suggestions
            result['cluster_issues'] = all_issues
            result['cluster_count'] = len(l1_names)

            # 在评测阶段尽量为建议补齐 target_id（基于当前图中的唯一名称匹配）
            result['adjustment_suggestions'] = self._attach_ids_to_suggestions(
                result['adjustment_suggestions'], kps
            )
            for c in cluster_details:
                if isinstance(c, dict) and "adjustment_suggestions" in c:
                    c["adjustment_suggestions"] = self._attach_ids_to_suggestions(
                        c.get("adjustment_suggestions") or [], kps
                    )

            # === 融合全局评分与各 L1 簇评分 ===
            try:
                global_score = float(result.get("overall_score", 0) or 0)
            except Exception:
                global_score = 0.0
            cluster_scores = [
                float(c.get("overall_score", 0) or 0)
                for c in cluster_details
                if isinstance(c, dict) and "overall_score" in c
            ]
            if cluster_scores:
                c_avg = sum(cluster_scores) / len(cluster_scores)
                c_min = min(cluster_scores)
            else:
                c_avg = global_score
                c_min = global_score

            base_score = 0.7 * global_score + 0.3 * c_avg
            bad_threshold = 6.0
            penalty = 0.0
            if c_min < bad_threshold:
                penalty = 0.5 * (bad_threshold - c_min)
            final_score = max(0.0, base_score - penalty)

            result["cluster_scores"] = {
                "global_score": global_score,
                "cluster_avg": c_avg,
                "cluster_min": c_min,
                "base_score": base_score,
                "penalty": penalty,
            }
            result["final_score"] = round(final_score, 2)

            # 结合阻断问题与最低簇分，给出通过判定
            blocking_issues = result.get("blocking_issues", [])
            pass_threshold = 8.5  # 通过阈值（最终评分）
            is_passed = (
                final_score > pass_threshold
                and len(blocking_issues) == 0
                and c_min >= 6.0
            )
            result["is_passed"] = is_passed
            if not is_passed and c_min < 6.0:
                msg = f"存在评分较低的 L1 主题簇（最低簇分={c_min:.1f}），需优先修复后再通过。"
                if msg not in blocking_issues:
                    blocking_issues.append(msg)
                result["blocking_issues"] = blocking_issues

            result.setdefault(
                "pass_reason",
                "最终评分达到阈值且各 L1 簇无明显短板"
                if is_passed
                else "存在需优先处理的问题或部分 L1 簇评分偏低",
            )

            # 不再对 L2 数量设置硬门槛；仅依赖模型综合评分与 blocking_issues
            over_limit_topics = self._collect_over_limit_l1_topics(data, kps)
            if over_limit_topics:
                topic_names = ", ".join([t.get('name', '') for t in over_limit_topics])
                self.log(f"检测到 L2 数量超过 10 的主题: {topic_names}", "warning")
            
            state['evaluation_report'] = result
            state['evaluation_passed'] = result.get('is_passed', False)
            state['current_step'] = 'evaluate'

            # 统一由 _save_evaluation_artifacts 负责历史快照和“最新评估输出”落盘
            self._save_evaluation_artifacts(result, data, cluster_details)

            # 在日志中完整展示最终评分决策所用变量与结果
            cs = result.get("cluster_scores", {}) or {}
            self.log(
                "评估打分明细："
                f" global_score={cs.get('global_score', 'N/A')},"
                f" cluster_avg={cs.get('cluster_avg', 'N/A')},"
                f" cluster_min={cs.get('cluster_min', 'N/A')},"
                f" base_score={cs.get('base_score', 'N/A')},"
                f" penalty={cs.get('penalty', 'N/A')},"
                f" final_score={result.get('final_score', 'N/A')},"
                f" is_passed={result.get('is_passed', 'N/A')}"
            )
            self.log(f"评估完成。LLM全局评分: {result.get('overall_score', 'N/A')}/10，最终评分: {result.get('final_score', 'N/A')}/10")
            
        except json.JSONDecodeError as e:
            self.log(f"JSON解析错误: {e}", "error")
            state['errors'].append(f"解析评估结果失败: {e}")
        except Exception as e:
            self.log(f"评估错误: {e}", "error")
            state['errors'].append(str(e))
        
        return state


def create_evaluation_agent(config: dict) -> EvaluationAgent:
    """工厂函数：创建评测智能体"""
    return EvaluationAgent(config)
