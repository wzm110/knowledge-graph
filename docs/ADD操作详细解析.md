# ADD 操作详细解析（微调智能体）

本文面向 `knowledge_graph/agents/refinement.py` 中的 `ADD` 行为，说明其完整流程、输入输出约束、已加固的防护点与残余风险。

## 1. 目标与边界

`ADD` 的目标是：**仅对稀疏 L1 主题补充 L2 子节点**。

明确边界：

- 仅允许 `L1 -> L2`，不允许 `L2 -> L3` 自动补充。
- 仅允许命中“真实存在”的 L1 节点。
- 仅允许命中“当前图谱判定为稀疏”的 L1 节点（`L2 数量 < 10`）。

---

## 2. 执行链路总览

### 阶段 A：计划生成 `generate_refinement_plan`

1. 读取评估建议 `adjustment_suggestions`。
2. 输入裁剪：按 `priority` 排序后截断到 `max_input_suggestions`（代码默认 60，可配置为 `refinement.max_input_suggestions`）。
3. 对每条建议补充 `target_level`。
4. 对 `ADD` 做归一化：
   - 优先按 `target_id` 命中稀疏 L1；
   - 否则按 `target(name)` 命中稀疏 L1；
   - 否则按 `source` 中的 `L1簇:xxx` 推断；
   - 以上都失败则丢弃该 `ADD`。
5. 将“稀疏L1列表 + 约束规则”写入提示词，要求 LLM 仅输出 `ADD@L1`。
6. 解析 LLM 输出后再次过滤：
   - 只保留 `DELETE/ADD/MERGE`；
   - `ADD` 必须能解析到真实 L1；
   - 并且该 L1 必须属于“当前稀疏 L1 集合”。

### 阶段 B：动作执行 `execute`

1. 先计算一次当前稀疏 L1 集合（执行期快照）。
2. 处理 `ADD` 时按顺序解析父节点：
   - `target_id`（且必须是现存 L1）；
   - `source`（`L1簇:xxx`）；
   - `target` 作为 L1 名称。
3. 若解析失败，跳过。
4. 若解析成功但不是当前稀疏 L1，跳过。
5. 进入 `execute_add` 真正落图。

### 阶段 C：新增节点落图 `execute_add`

1. 再次校验父节点真实存在，且 `level=L1`。
2. 读取该 L1 已有 L2 列表，构造重名集合。
3. 调用 LLM 生成 `new_nodes`。
4. 对输出做强约束：
   - 非 list 跳过；
   - 单次最多 `max_add_nodes_per_action`（默认 10）；
   - 每项必须是 dict；
   - 节点名不能为空；
   - 与同父主题已有 L2 重名则跳过；
   - `id` 非法/冲突则重建 fallback id；
   - `difficulty` 不合法则回退 `中等`。
5. 追加 `contains` 关系（`L1 -> L2`）。

### 阶段 D：结构校验与回滚

每个动作执行后都会记录并比较结构指标：

- `kp_count`
- `rel_count`
- `isolated_count`

若 `isolated_count` 增加，则回滚该动作到执行前状态。

---

## 3. 关键防护点（当前版本）

### 3.1 计划级防护

- `ADD` 在进入 LLM 前已做“稀疏 L1 归一化”。
- LLM 输出后再次做“真实 L1 + 稀疏 L1”双重过滤。

### 3.2 执行级防护

- `ADD` 仅接受可解析为真实 L1 的目标。
- 执行前再次校验目标是否仍是“当前稀疏 L1”。
- `execute_add` 内部再次限制为 `L1 -> L2`，禁止 `L2 -> L3`。

### 3.3 数据质量防护

- 单次新增数量上限（避免超量写入）。
- 空名称过滤。
- 同父主题重名过滤（大小写不敏感）。
- `difficulty` 白名单归一化。
- ID 冲突自动回退生成。

### 3.4 结构健康防护

- 动作后孤立节点变多则自动回滚。

---

## 4. 仍需关注的残余风险

1. **语义近似重复**  
   当前只做“名称去重”，未做语义去重（如“领域迁移学习”与“迁移学习”）。

2. **并发一致性**  
   若未来并发执行多个 `ADD`，需引入更严格的事务或锁机制。

3. **LLM 超时与降级**  
   当前 `ADD` 逻辑已做输出裁剪，但若底层 LLM 请求长时间阻塞，仍建议在 `call_llm` 层补超时、重试与规则降级。

---

## 5. 配置项（与 ADD 直接相关）

- `refinement.max_input_suggestions`：计划生成输入裁剪上限。
- `refinement.max_actions`：计划输出动作上限。
- `refinement.max_add_nodes_per_action`：单次 `ADD` 新增节点上限（默认 10，代码提供默认值）。

---

## 6. 快速验收建议

1. 构造评估建议中包含 `ADD target=L2`，确认不会进入最终可执行计划。
2. 构造 `ADD target=非稀疏L1`，确认执行阶段被跳过。
3. 构造 `new_nodes` 含空名称/重名/超量，确认被过滤并正确记日志。
4. 观察动作前后日志，确认 `isolated_count` 不增或触发回滚。

