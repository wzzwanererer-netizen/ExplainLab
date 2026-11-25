# ExplainLab V2 · As-Built Architecture

本报告描述本任务实现的 Batch B B3–B5 运行边界。运行入口为 FastAPI，持久化使用既有 SQLAlchemy 适配与 Alembic 迁移链。Python Knowledge Core 继续负责审核业务策略和 Markdown 核心模型。

## 接口与数据流

| 入口 | 事务与数据 |
| --- | --- |
| POST /api/knowledge/{item_id}/attachments | B2 验证请求与文件签名，按 SHA-256 发布正式 blob，然后提交正式附件引用。 |
| GET /api/knowledge/{item_id}/attachments | 返回该条目的附件元数据。 |
| GET /api/knowledge/{item_id}/attachments/{attachment_id} | 验证条目归属与正式文件；通过已验证的文件句柄输出。 |
| DELETE /api/knowledge/{item_id}/attachments/{attachment_id} | 删除引用；最后一条引用消失时在同一事务安排任务。 |
| POST /api/knowledge/import 或 /import/batch | Markdown 原有入口继续使用既有报告。单文档 ZIP 附件按内容地址生成 manifest，持 staging guard 创建目录。Draft 直接发布并写引用，Active 有正文变更时建立 pending。 |
| POST /api/reviews/{review_id}/approve | 验证已存 envelope，先发布后开启新业务事务，Core 决议和 Hook 写入在一次业务提交内完成。索引事务独立执行。 |
| POST /api/reviews/{review_id}/reject | 拒绝状态提交后清理可证实归属的 staging。 |
| Markdown 导出 | 保留现有 Markdown 和 ZIP 文档导出以及附件导出禁用契约。 |

## 数据库与文件布局

迁移链截至 0006_v2_markdown_kb。本轮沿用 attachment、storage_lock、gc_task、review_request、knowledge_item 及 Batch A 的来源和链接存储。attachment 的 item 外键和 content hash 支持正式元数据与共享引用。review_request 的 JSON payload 存放由摘要覆盖的 ImportEnvelope 和物理 manifest；临时状态和正式引用在数据库中有独立所有权。

正式文件按 key 的前两级十六进制分片保存。staging 使用 UUIDv4、服务端 ordinal 文件名和 .creating、.activity、.complete 标记。GC 隔离槽按 key 和 task UUID 构造。staging 隔离目录使用 staging UUID 与 UTC 隔离时刻。ops 存最近 30 份脱敏一致性报告。

## 锁序与失败恢复

审核决议按 review、来源、identity、staging、storage 的顺序进入。D23 恢复完成并关闭事务后进入存储锁。发布发生在业务写事务前。提交前以同一个业务 Session 验证 fencing，事务结束后释放存储锁。SQLite 对既有条目执行条件同值更新，PostgreSQL 使用行锁。PostgreSQL 的 key 锁权威来自会话 advisory lock，ORP 扫描领导权走独立物理连接与单 bigint 命名空间。

GC 先提交任务认领，再取 key 锁。认领递增 token 和 attempts；任务心跳与存储锁心跳独立。每次关键物理变更复核任务租约、key fence 与引用。隔离成功的任务等待安全期；旧隔离代次到期只清自己的槽。新发布的正式代次由后继任务处理。进程死在移动后、状态写回前，接管者验证隔离文件并从接管时刻重新计时。文件系统与数据库的边界由回滚、保守保留和 ORP 收敛。

ORP 只从正式根的规范位置发现候选；临时文件只统计。仍被引用的缺失正式文件可从可信隔离槽恢复。损坏的 envelope 使 staging 清理停止，可信 pending 优先保留。未知物理路径和不可验证副本保留证据。数据库不可用时停止当前扫描。

## 安全与平台边界

ZIP 请求做路径、媒体格式、数量、解压预算、SHA-256 和 manifest 校验。正式目录和 staging 禁止路径穿越、重解析点和跨卷。用户给定的文件名只用于元数据与下载呈现。报告仅包含计数、稳定代码和服务端标识。生产进程保持单 Backend 和单 worker；PG 双连接用例只负责验证锁语义。

POSIX 正式目录同步覆盖相关父链，Linux staging 的无覆盖目录移动依赖 renameat2。Windows 使用平台原子移动语义和共享冲突退避。Windows 的目录断电耐久性沿用冻结设计的边界。超出已验证平台的扩展支持待独立审计。
