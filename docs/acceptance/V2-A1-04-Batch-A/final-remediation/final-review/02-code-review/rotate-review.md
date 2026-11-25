# 02-C · ROTATE 与状态 3/4 复核（P1-03）

- 实现：`backend/app/services/source_identity.py:941–1012`
- 本轮性质：**未修改 ROTATE 语义**；仅新增共存场景测试来证明既有行为符合冻结要求。
- P1-03 结论：状态 3 不物化、不重写、不认领；状态 4 阻断整次轮换；其他 2a 正常物化；仅 exporter 实例被替换。

## 1. 代码路径

| 行号 | 动作 |
| --- | --- |
| 942–943 | 持 Journal 锁并先执行恢复门 |
| 944 | `old = self._store.ensure()`（读取/确保当前实例 ID） |
| 945–949 | 生成/校验目标 UUIDv4，拒绝等于旧值 |
| 951–969 | 第一遍：遍历全部条目并分类 |
| 957–959 | 状态 2a → `self.materialize(raw_id)`，记入 `pre_materialized` |
| 960–962 | 状态 3 → `continue`（不物化、不改写、不认领） |
| 963–967 | 状态 4 → 抛 `SOURCE_IDENTITY_INCONSISTENT`，整次轮换中止 |
| 971–994 | 第二遍：只把 `pre_materialized` 作为 ROTATE 的 `materialization_items`，写 PREPARED Journal |
| 995–1004 | 审计校验 → `store.replace(target)` → 回读校验 → 记录校验 → COMMITTED + 归档 |
| 1005–1010 | 返回 `RotateReport(old, target, operation_id, pre_materialized)` |

状态 1/2b 在循环中不做任何分支动作，保持原身份与记录。

## 2. 状态 3 的“不物化 / 不覆盖 / 不认领”

- 不物化：960–962 直接跳过；不会为状态 3 生成新的 MATERIALIZE 记录。
- 不覆盖：状态 3 条目的 `knowledge_item.source_instance_id` 与 ImportOrigin 均不写。
- 不认领：`classify` 对状态 3 返回 `None` 身份（654），导出不会把冲突条目的来源写成当前实例。
- 已存在的 MATERIALIZE 证明记录保留原样：测试对比轮换前后 `(operation_id, item_id)` 集合完全相等（`test_markdown_batch_a_identity.py:1017–1022`）。
- 审计摘要不变：冲突条目的 ImportOrigin 与 DB 投影均未变，`identity_audit_digest` 前后一致（1005、1009、1014）。
- 重复轮换仍保持状态 3 与原值（1030–1038）。

## 3. 状态 4 的阻断

- 963–967：任一文档为状态 4，`rotate()` 在**写 PREPARED 之前**抛出；ID 文件保持旧值（`TestRotate.test_rotate_blocks_on_state_4`，747–757）。
- 该行为是既有设计：状态 4 表示“孤儿/无法解释的原生实例字段”，轮换不能猜测其归属。

## 4. 其他 2a 的物化与 coexistence

- `test_rotate_materializes_2a_keeps_imported_identity_and_exporter`（691–745）：
  - 2a 本地文档被物化为旧实例，轮换后分类为 2b，DB 实例仍为 `old`；
  - 状态 1 导入文档保持 `X`，不被改为 `old`/`target`；
  - 状态 3（残缺 ImportOrigin）保持原实例、原快照；
  - 导出头：本地文档 `Source-Instance=old`、`Exporter=target`；导入文档 `Source-Instance=X`、`Exporter=target`；
  - 第二次轮换以 `target` 为旧值，归档累计 ≥2。
- `test_rotate_conflict_does_not_block_other_2a_materialization`（1040–1063）：
  - 冲突 + 合法 2a 并存时，`materialized_items` 只含合法 2a；
  - 冲突条目分类、DB 值、快照均不变；
  - ROTATE 记录只含该 2a，审计摘要等于 DB 计算值。

## 5. exporter 与审计摘要的边界

- exporter 实例只写在传输层/ID 文件，不进入 `build_identity_snapshots`，也不进入 `identity_audit_digest`。测试在同一次轮换后断言 `rotate_record.identity_audit_digest == _digest()`（1014、1060），证明替换 exporter 未污染审计。
- `rotate()` 自身的 `materialization_items` 使用**旧实例**（977），因为 ROTATE 是对“旧实例下已物化文档”的证明；目标实例仅体现在 `target_instance_id` 与 ID 文件。

## 6. 测试清单

| 测试 | 覆盖 |
| --- | --- |
| `TestRotate.test_rotate_materializes_2a_keeps_imported_identity_and_exporter` | 2a 物化、1/3 共存、导出头、二次轮换 |
| `TestRotate.test_rotate_blocks_on_state_4` | 状态 4 阻断且不换 ID |
| `TestRotate.test_prepared_rotate_old_id_recovery_completes_replace` | PREPARED 且 ID 仍旧 → 恢复完成 replace |
| `TestRotate.test_prepared_rotate_new_id_recovery_only_commits` | PREPARED 且 ID 已新 → 恢复只提交归档 |
| `TestRotateMaterializeOriginConflict.test_rotate_conflict_only_keeps_audit_and_replaces_exporter` | 冲突零改写、无新增 MATERIALIZE、审计不变、导出器替换 |
| `TestRotateMaterializeOriginConflict.test_rotate_conflict_does_not_block_other_2a_materialization` | 冲突不阻塞其他 2a |

以上均使用真实 SQLite 与真实文件系统。

## 7. 未验证

- 真实 PostgreSQL 上的 ROTATE：未连真实 PG；ROTATE 主要操作文件系统与 DB 身份列，PG 路径未实测。
- 轮换期间进程崩溃：只覆盖 PREPARED 两个恢复分支；未做断电级注入。
- 多进程同时 ROTATE：由单实例 `ProcessLock` 排除，未压测。