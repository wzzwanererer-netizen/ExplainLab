# 十份设计文档交叉检查

| 文件 | 对齐内容 | 对照章节 |
|---|---|---|
| README.md | 整改版和待签发状态、权威顺序、R1.3 差异 | §3、§5–10 |
| architecture.md | 全局锁序、先物理后写、archive 保护、①/②、单部署 | §4–6 |
| storage-and-lock-contract.md | 根隔离、PG 批连接/顺序、token 及末次 fencing、文件语义 | §1、§3–7 |
| attachment-lifecycle.md | 上传受保护写、ZIP 单归属和重试、staging 所有权、Draft/Active promote | §2–4、§6–7 |
| active-review-integration.md | PENDING、预发布计划、共同决议锁、DB Hook、坏 envelope 的 reject | §2–8 |
| gc-and-orphan-recovery.md | 七态、旧槽/新代次、孤儿接手、创建与清扫共同锁 | §3–6 |
| api-contracts.md | 两种 JSON 行为、ZIP 整包失败、已有 warnings、错误语义 | §2–7、§9 |
| implementation-roadmap.md | B1 契约先行，B2–B5 按接口依赖实施，B6 真实取证 | B1-T01 至 B6 |
| acceptance-plan.md | 保留 53 条，补并发、恢复、继承映射 | §3–9 |
| risk-register.md | 状态为待实现验证，记录平台与残余窗口 | §2–6 |

## 横向时序

- 审核锁 → 来源锁 → 身份恢复与 guard → staging guard → storage guard → DB 写。只获取路径需要的锁。写完成/回滚后释放。GC claim 短事务已关闭后才取 storage guard。
- PG 的实际 advisory 身份排序和完整 key 的 token 顺序是不同的层。要获得可写 guard，两个层都需要成功。SQLite 使用完整 key 顺序和同业务 session 末次验证。
- 上传/新 Draft/approve 为文件先于业务写。Active 提交 pending 无正式引用。Reject 先提交状态，再清可信 staging。GC/ORP 处理跨文件系统与 DB 中间态。
- 归档前后按事务保护结果判定。单篇 JSON、批量 JSON、ZIP 的兼容/错误由 API §5 与生命周期 §3 一致定义。文档 Hash 投影、身份 Journal 与 schema 不变。
- Git/文件范围、候选前后及审计基线算法见 [SHA256SUMS.txt](SHA256SUMS.txt)。本报告为文档静态交叉检查，真实部署与故障取证仍按验收计划执行。
