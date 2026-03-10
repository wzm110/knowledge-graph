#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Node 8: 图构建智能体
构建Neo4j知识图谱
"""

from knowledge_graph.agents.base_agent import BaseAgent, AgentState


class GraphBuilderAgent(BaseAgent):
    """构建Neo4j知识图谱的智能体"""

    def __init__(self, config: dict):
        super().__init__(name="GraphBuilder", config=config)

    def execute(self, state: AgentState) -> AgentState:
        """执行图构建"""
        self.log("开始构建Neo4j图谱")
        
        kps = state.get('calibrated_kps', [])
        resources = state.get('calibrated_resources', [])
        relationships = state.get('calibrated_relationships', [])
        
        if not kps and not relationships:
            self.log("没有数据用于构建图谱", "warning")
            state['errors'].append("没有数据用于构建图谱")
            return state
        
        try:
            from neo4j import GraphDatabase
            
            neo4j_config = self.config.get('neo4j', {})
            uri = neo4j_config.get('uri', 'neo4j://127.0.0.1:7687')
            user = neo4j_config.get('user', 'neo4j')
            password = neo4j_config.get('password', '12345678')
            
            self.log(f"正在连接Neo4j: {uri}")
            
            driver = GraphDatabase.driver(uri, auth=(user, password))
            
            with driver.session() as session:
                session.run("MATCH (n) DETACH DELETE n")
                self.log("已清除现有数据")
                
                l1_kps = [kp for kp in kps if kp.get('level') == 'L1']
                for kp in l1_kps:
                    session.run(
                        "CREATE (k:KnowledgePoint {id: $id, name: $name, definition: $definition, level: $level})",
                        id=kp.get('id', ''),
                        name=kp.get('name', ''),
                        definition=kp.get('definition', ''),
                        level=kp.get('level', 'L1')
                    )
                self.log(f"已创建 {len(l1_kps)} 个L1节点")
                
                l2_kps = [kp for kp in kps if kp.get('level') == 'L2']
                for kp in l2_kps:
                    session.run(
                        "CREATE (k:KnowledgePoint {id: $id, name: $name, definition: $definition, level: $level, parent_id: $parent_id})",
                        id=kp.get('id', ''),
                        name=kp.get('name', ''),
                        definition=kp.get('definition', ''),
                        level=kp.get('level', 'L2'),
                        parent_id=kp.get('parent_id', '')
                    )
                self.log(f"已创建 {len(l2_kps)} 个L2节点")
                
                l3_kps = [kp for kp in kps if kp.get('level') == 'L3']
                for kp in l3_kps:
                    session.run(
                        "CREATE (k:KnowledgePoint {id: $id, name: $name, definition: $definition, level: $level})",
                        id=kp.get('id', ''),
                        name=kp.get('name', ''),
                        definition=kp.get('definition', ''),
                        level=kp.get('level', 'L3')
                    )
                self.log(f"已创建 {len(l3_kps)} 个L3节点")
                
                for res in resources:
                    session.run(
                        "CREATE (r:Resource {id: $id, type: $type, title: $title, url: $url})",
                        id=res.get('id', ''),
                        type=res.get('type', ''),
                        title=res.get('title', ''),
                        url=res.get('url', '')
                    )
                self.log(f"已创建 {len(resources)} 个资源节点")
                
                for rel in relationships:
                    rel_type = rel.get('type', 'contains')
                    session.run(
                        f"MATCH (a), (b) WHERE a.id = $start_id AND b.id = $end_id CREATE (a)-[r:{rel_type} {{reason: $reason}}]->(b)",
                        start_id=rel.get('start_id', ''),
                        end_id=rel.get('end_id', ''),
                        reason=rel.get('reason', '')
                    )
                self.log(f"已创建 {len(relationships)} 条关系")
            
            driver.close()
            
            state['neo4j_imported'] = True
            state['current_step'] = 'build_graph'
            
            self.log("Neo4j图谱构建成功")
            
        except Exception as e:
            self.log(f"图构建错误: {e}", "error")
            state['errors'].append(str(e))
            state['neo4j_imported'] = False
        
        return state


def create_graph_builder_agent(config: dict) -> GraphBuilderAgent:
    """工厂函数：创建图构建智能体"""
    return GraphBuilderAgent(config)
