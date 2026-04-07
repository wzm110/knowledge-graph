# ADD 操作详细解析（微调智能体）

本文面向 `knowledge_graph/agents/refinement.py` 中的 `ADD` 行为，说明其完整流程、输入输出约束、防护点与残余风险；描述以**当前仓库代码**为准。

## 1. 目标与边界

`ADD` 的目标是：**在真实父节点下补充子知识点**。

- **L1 父节点**：补充 **L2**（`contains`：`L1 → L2`）。
- **L2 父节点**：补充 **L3**（`contains`：`L2 → L3`）。

明确边界：

- 父节点必须是图中**已存在**且层级为 **L1 或 L2**；`execute_add` 对其它层级直接跳过并打日志。
- **不允许**通过 ADD 自动生成 `L2 → L4` 等跨层结构；子层级由父节点 `level` 唯一决定。
- 稀疏 L1 列表（`find_sparse_topics`：`L2` 直连数量 `< 10`）写入计划提示词，并参与 `_resolve_add_parent` 的**同名歧义消解**；**执行阶段不再用「必须属于稀疏 L1」过滤 ADD**（与仅允许稀疏 L1 的旧描述不同）。

与 `prompts/Refinement_Plan_Prompt.txt` 一致：全局评测侧常见 **L1 父 id 补 L2**；簇评测侧常见 **L2 父 id 补 L3**。

---

## 2. 执行链路总览

整体动作顺序为 **MERGE → ADD → DELETE**（`_ACTION_ORDER`）。

### 阶段 A：计划生成 `generate_refinement_plan`

1. 读取 `evaluation_report.adjustment_suggestions`。
2. 输入裁剪：取 **字典项**，按 `priority`（`high` / `medium` / `low`）排序后截断到 `max_input_suggestions`（默认 60，配置键 `refinement.max_input_suggestions`）。
3. 对每条建议补充展示用字段（如 `_fmt_sugg` 中的 id 对齐）。
4. 对来自评测的 **`action == ADD`** 做归一化预填：
   - 调用 `_resolve_add_parent`（可解析到 **L1 或 L2**）得到 `parent_id` / `target_id`（二者在计划里会统一为父 id）与 `focus`；
   - 若仍无 `parent_id`，再尝试 `source` 中 **`L1簇:xxx`** 且该 L1 名在**稀疏 L1 表**中命中，则填入对应 L1 id。
5. 将 `sparse_json`、`l1_catalog_json`、`suggestion_nodes_catalog_json`、`overloaded_json`、`isolated_json` 等写入 `Refinement_Plan_Prompt.txt`，要求 LLM 输出 `actions`。
6. **有效动作上限 `effective_max`**：`refinement.max_actions`（默认 35）为基准；孤立节点数 `>20` 时 ×2，`>100` 时 ×3。仅 **MERGE + ADD** 计入该上限；**DELETE** 单独处理（批量孤立删除至多一条等逻辑见代码）。
7. 解析 LLM JSON 后过滤：
   - 仅保留 `MERGE` / `ADD` / `DELETE`；
   - **`ADD`**：再次 `_resolve_add_parent`；无法解析父节点则丢弃并打日志（**不要求**父 L1 必须稀疏）。

### 阶段 B：动作执行 `execute`

1. 加载图并先跑 `validate_relationships`（与 `CalibrationAgent.validate_and_calibrate_relationships` 一致）。
2. 处理 **`ADD`** 时：
   - 用 `_resolve_add_parent`（`target_id_raw` 在执行路径传空，主要依据 `parent_id` / 展示名 / `focus`）解析父节点；
   - 若仍失败，再尝试 `source` 中 **`L1簇:`** 解析为 L1 id（`_resolve_l1_parent_from_source`）。
3. 解析成功后调用 `execute_add(parent_id, parent_name, graph_data, focus_hint=...)`。
4. 每次 ADD 后再次 `validate_relationships`；并**刷新**稀疏 L1 相关缓存（供后续动作使用）。
5. **回滚条件（仅 ADD）**：若本动作确实新增了知识点，且**新增节点 id 出现在当前孤立节点集合中**，则整图回滚到该动作执行前快照（`ADD 回滚: 新增节点孤立`）。**不是**「任意 `isolated_count` 上升即回滚」。

### 阶段 C：新增节点落图 `execute_add`

1. 解析父节点 id（支持按 id 或按名称查找）。
2. **`parent_level == L1`**（补 L2）：
   - 统计该 L1 下已有 **L2**（经 `contains` + 子节点 `level==L2`）。
   - 若已有 L2 数量 **≥ 10**，直接跳过（硬上限 10）。
   - `allowed_add_nodes = min(max_add_nodes_per_action, remain_slots)`，`remain_slots = max(0, 10 - len(existing_l2_ids))`。
   - 调用 LLM 生成 `new_nodes`，经 `_normalize_added_node` 校验；写 `contains`（`L1 → L2`）。
3. **`parent_level == L2`**（补 L3）：
   - `max_l3_per_l2`（默认 **8**）、`max_l3_add_per_call`（默认 **3**），配置在 `refinement` 下。
   - `allowed_add_nodes = min(max_add_nodes_per_action, remain_slots, per_call_cap)`。
   - 提示词含 L3 粒度与去重说明（`_add_l3_granularity_rules`）；落图逻辑与 L2 分支类似，关系为 `L2 → L3`。

### 阶段 D：节点规范化 `_normalize_added_node`

- 每项须为 `dict`；`name` 为空或与**同父已有子节点**名称（大小写不敏感）重复则跳过。
- `id` 须以 `l2_` / `l3_` 开头（按子层级），否则或冲突时 **MD5 fallback** 生成新 id。
- `difficulty` 仅允许 `基础` / `中等` / `高`，否则回退 **`中等`**。
- 无 `description` 时用名称填充 `description` / `definition`；写入 `source: refinement` 等字段。

---

## 3. 关键防护点（当前版本）

### 3.1 计划级

- 评测建议按优先级排序并截断，控制提示规模。
- ADD 的父节点在计划过滤阶段必须能解析到真实 **L1 或 L2**。
- `effective_max` 随孤立节点规模放宽，避免大批量孤立时 MERGE/ADD 被压得过死。

### 3.2 执行级

- 父节点解析失败则跳过 ADD；可从 `source` 的 `L1簇:` 兜底到 L1。
- **L1 下 L2 数量上限 10**；**单 L2 下 L3 总数上限**由 `max_l3_per_l2` 控制；单次 L3 生成上限还受 `max_l3_add_per_call` 约束。
- ADD 后对关系做校准，减少非法边。

### 3.3 数据质量

- 单次新增数量上限（L2/L3 分别与槽位、`max_add_nodes_per_action` 取 min）。
- 同父主题子节点**名称**去重（大小写不敏感）；L3 提示词强调语义层面少而精（依赖 LLM 遵守）。

### 3.4 结构健康

- **仅当新增节点处于孤立状态**时回滚该次 ADD，避免写入无 `contains` 挂靠的节点。

---

## 4. 仍需关注的残余风险

1. **语义近似重复**  
   代码侧主要是**名称**去重；L3 的「语义不重复」依赖提示词与模型自觉，难以硬编码等价判定。

2. **同名多节点**  
   `_resolve_add_parent` 对 L1/L2 同名等情况有优先级规则（含稀疏 L1 id 提示、优先 L2 等），极端数据下仍可能不符合人工预期。

3. **并发一致性**  
   若未来并发执行多条流水线或同一 parquet，需事务或外部锁。

4. **LLM 超时与降级**  
   建议在 `call_llm` 层统一超时、重试；ADD 失败时当前多为跳过并打日志。

---

## 5. 配置项（与 ADD 直接相关）

| 配置键 | 含义 |
|--------|------|
| `refinement.max_input_suggestions` | 进入计划生成的建议条数上限 |
| `refinement.max_actions` | MERGE+ADD 的基准上限（再结合孤立节点数得到 `effective_max`） |
| `refinement.max_add_nodes_per_action` | 单次 `execute_add` 最多采纳的新节点数（默认 10），与槽位取 min |
| `refinement.max_l3_per_l2` | 每个 L2 下 L3 总数上限（默认 8） |
| `refinement.max_l3_add_per_call` | 单次调用最多生成的 L3 条数（默认 3） |

---

## 6. 快速验收建议

1. **L2 父补 L3**：在计划或评测建议中给出合法 L2 `parent_id`，确认 `execute_add` 走 L3 分支且受 `max_l3_per_l2` / `max_l3_add_per_call` 约束。
2. **L1 已满 10 个 L2**：对某 L1 执行 ADD，确认跳过并打「L2 已满 10」类日志。
3. **空名 / 重名 / 超量**：构造 LLM 返回的 `new_nodes`，确认被过滤且关系不重复追加。
4. **孤立回滚**：模拟新增节点未写入 `contains`（或校准后仍孤立），确认触发回滚且图中无残留新增 id。
5. **非稀疏 L1**：若父解析为某 L1 且该 L1 已有 ≥10 个 L2 会跳过；若 \<10，应仍可执行（不再要求「必须稀疏」才允许）。
