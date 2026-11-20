"""链接重建并发控制（K2 整改）：方言分派的写锁，封装在 backend 数据库适配层。

门禁 A/B/C 关闭「计划生成 → 应用重读」窗口（窗口①），但**重读 → 提交**之间
（窗口②）的跨事务互斥须由数据库锁/隔离保证。本模块按方言分派，Core 纯函数、
端口签名、迁移**零改动**（AGENTS.md §5/§11）：

- **PostgreSQL**（默认 READ COMMITTED，SELECT 不锁行）：``LOCK TABLE knowledge_link
  IN SHARE ROW EXCLUSIVE MODE`` 阻塞并发 INSERT/UPDATE/DELETE（含 phantom 新键），
  持锁至事务提交；辅以 ``SELECT … FOR UPDATE`` 显式锁既有行。重建写者被串行化，
  窗口②（含步 8 写后复核 → 步 9 提交间隙）完全关闭。允许并发只读（ACCESS SHARE）。
- **SQLite**（默认 rollback-journal，isolation_level=None）：**实测**读阶段
  （步 2/3 重读 SELECT）**不持阻塞写者的锁**——并发连接在重建写之前可写并提交。
  因此窗口②「重读 → 写」在 SQLite 上**不由锁保护**，而由步 7 的 P2 乐观前置
  （``old_key``/``old_version`` + rowcount 校验）兜底：并发漂移使 rowcount=0 →
  抛 ``LinkRebuildPostWriteError`` 整体回滚零写入（见 test_links_concurrency.py
  的 P2 故障注入与读阶段语义固化测试）。一旦进入写阶段（步 7 UPDATE 持 RESERVED），
  并发写者提交被阻（EXCLUSIVE 冲突）；写升级争用（SQLITE_BUSY）属活性问题，由引擎
  ``busy_timeout``（session.py connect 事件）降低即失败概率，争用下重建以零写入
  回滚告终须重试。**诚实限制**：未启用 BEGIN IMMEDIATE（需全局事务控制管线改动，
  本轮不做），不宣称读阶段已锁保护，亦不宣称已消除 BUSY；SQLite 窗口②安全由 P2 保证。

锁仅在重建独占事务内获取（``apply_link_key_plan`` 步 1 之后、步 2 之前），
不影响常规 CRUD 事务。任一方言不支持时显式报错，不静默降级。
"""

from __future__ import annotations

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models import KnowledgeLinkORM


def acquire_rebuild_write_lock(session: Session) -> None:
    """在重建独占事务内获取写锁（持锁至提交），关闭门禁 C 重读 → 提交窗口。

    调用方须已 ``session.begin()``（事务内）；本函数只执行锁语句，不开/提交事务。
    """
    dialect = session.get_bind().dialect.name
    if dialect == "postgresql":
        # 表级锁：阻并发写（含 INSERT phantom），与自身以外的写锁冲突，串行化重建。
        session.execute(
            text("LOCK TABLE knowledge_link IN SHARE ROW EXCLUSIVE MODE")
        )
        # 行级锁：显式锁既有行（表锁已覆盖，FOR UPDATE 明确行锁意图，纵深防御）。
        session.execute(select(KnowledgeLinkORM.id).with_for_update())
    elif dialect == "sqlite":
        # 实测读阶段不持阻塞写者的锁（见模块 docstring）；窗口②由步 7 P2 乐观前置兜底，
        # 写阶段 RESERVED 锁 + 引擎 busy_timeout 补充。SQLite 不支持 FOR UPDATE /
        # LOCK TABLE，此处无需额外语句（不伪称读阶段已锁保护）。
        return
    else:
        raise ValueError(f"不支持的数据库方言: {dialect}")