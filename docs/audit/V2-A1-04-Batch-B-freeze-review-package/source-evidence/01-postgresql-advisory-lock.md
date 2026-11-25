# PostgreSQL advisory lock、连接与 fencing

## 状态

基线已有双方言引擎、锁表和协议。Batch B 的 int32 二元组取自完整 Hash 的前两段、按实际冲突域去重排序、单 guard 专用物理会话、完整 key 独立 token、最后提交区间锁行、断连关闭和独立 ORP bigint 命名空间均为设计要求。基线源码无此 advisory 完整实现；LCK-02/03/06/10、R1-LOCK-08 真实 PG 取证待验证。

## 对应基线源码

[打开带原始行号的源码索引](README.md)

- `backend/app/db/session.py`：19–56，应用引擎及业务会话工厂。
- `backend/app/models.py`：438–451，完整 key 主键、租约与 token。
- `backend/alembic/versions/0006_v2_markdown_kb.py`：190–201，storage_lock DDL。
- `knowledge-core/src/knowledge_core/ports.py`：437–464，StorageKeyLock 协议。

针对基线限定路径执行只读 `git grep`，检查 advisory 函数及重解析点标识。结果：无命中。

候选附件/staging 路径名匹配：无。

## 当前候选设计原文（限定章节）

完整设计文件见 `design-documents/`。行号对应打包时源文件。

### storage-and-lock-contract.md · §4 StorageKeyLock，含 §4.3–4.6（104–180）

~~~text
 104: ## 4. StorageKeyLock 双方言契约
 105: 
 106: ### 4.1 参数与语义
 107: 
 108: - TTL：60s；心跳：15s；获取等待：10s（决策 5）。
 109: - `StorageLease = {storage_key, owner, lease_token, lease_expires_at}`。
 110: - `owner`：进程内唯一字符串，建议 `"<hostname[:16]>:<pid>:<uuid4hex[:12]>"`，最长 64 字符；不得含密钥/用户信息。
 111: - `lease_token`：单调递增；每次成功获取/接管 +1；同一 key 永不回退。
 112: - **不重入**：owner 标识一次 guard 获取，进程标识仅作前缀。同一 owner 对同一完整 key 嵌套 acquire 返回 None；批内输入先去重。
 113: - `acquire` 只在“无锁”或“租约已过期”时成功；等待上限 10s，超时返回 `None`。
 114: - `renew`/`verify`/`release` 仅在 owner+token 匹配且未过期时成功；否则 `False`，调用方**立即中止**不可逆操作。
 115: - `release` 不删除 `storage_lock` 行，只清 owner 并将 `lease_expires_at` 置为当前时间；token 保留以保证单调性。PG 额外 `pg_advisory_unlock` 并物理关闭。即使行已过期，也必须释放本 guard 自己的会话锁。
 116: - 旧 worker 持过期 token 的任何 `update_task`/文件操作必须被拒绝（fencing）。
 117: 
 118: ### 4.2 SQLite：`storage_lock` 租约
 119: 
 120: 表结构沿用 `StorageLockORM`：`storage_key` PK、`owner`、`lease_token`、`lease_expires_at`、`locked_at`。
 121: 
 122: 获取（单条原子语句 + 插入竞争）：
 123: 
 124: ```sql
 125: -- 已存在且过期；owner 相同视为不重入，必须失败返回 None
 126: UPDATE storage_lock
 127: SET owner=:owner, lease_token=lease_token+1,
 128:     lease_expires_at=:expires_at, locked_at=:now
 129: WHERE storage_key=:key
 130:   AND lease_expires_at <= :now
 131:   AND owner <> :owner;
 132: 
 133: -- 不存在（INSERT 的 UNIQUE 冲突视为竞争失败，重试至等待上限）
 134: INSERT INTO storage_lock(storage_key, owner, lease_token, lease_expires_at, locked_at)
 135: VALUES(:key, :owner, 1, :expires_at, :now);
 136: ```
 137: 
 138: - 先 UPDATE；`rowcount==1` 即成功。`rowcount==0` 时尝试 INSERT；`IntegrityError` 说明他人刚插入，进入等待重试。
 139: - `renew`：`UPDATE ... SET lease_expires_at=:new WHERE storage_key=:key AND owner=:owner AND lease_token=:token AND lease_expires_at > :now`；`rowcount==1` 为成功。
 140: - `verify`：`SELECT 1 ... WHERE storage_key/owner/token/expires_at > now`。
 141: - `release`：`UPDATE ... SET owner='', lease_expires_at=:now WHERE ... owner/token`；不 DELETE。
 142: - **诚实限制**：SQLite 租约是逻辑锁，降低而非消除 TOCTOU；物理步骤前必须再次 `verify`。不得宣称严格并发安全。
 143: 
 144: ### 4.3 PostgreSQL：每 guard 一个专用会话
 145: 
 146: - D-B02 保留：会话 advisory lock 是互斥权威，`storage_lock` 按完整 key 维护 token 与租约。有效租约还须 owner/token/expiry 匹配。行 TTL 过期不能授权其他会话接管；原会话解除锁或物理断开后，获得实际锁者才可递增 token。
 147: - 将每个完整 key 前两段 8 hex 转有符号 int32，取二元组作为实际锁身份。整批建立 **一个独占的物理连接**，按二元组有符号字典序获取去重后的身份，同一身份只调用一次 `pg_try_advisory_lock(classid,objid)`。完整 key 不合并，取得全部物理锁后在该连接的一笔短事务按完整 key 排序 UPSERT 与递增 token；提交成功才交付 guard。一至 100 个 key 均只用一个该类连接，业务 session 另计。
 148: - 单 key 也走同一协议。获取入口拒绝同一 owner 嵌套或重复持有同一完整 key；不能用旧 owner 行代替会话归属判断。各 key 的持有关系由 guard 记录，检查连接仍为同一物理会话、该会话仍持有对应二元组锁、完整 key 行仍匹配与未过期；校验失败即失效。禁用自动重连复活旧 guard。
 149: - 同一会话的上锁、token 短事务、heartbeat、verify、release 串行执行，一个 guard 一个心跳调度。心跳按完整 owner/token/未过期条件批量续约，部分失败则整 guard 失效。短事务每轮结束，避免 idle-in-transaction。业务写事务不更新 PG 锁行。
 150: - 获取总预算 10s 涵盖连接建立、重试与 SQL，所有阻塞操作用剩余预算或更短超时；拿不到全部锁或 token 写失败，回滚锁行短事务，逆序解锁已获取的唯一身份并物理关闭。释放时先尽力条件清行且保留 token，再逆序显式解锁并关闭物理连接，异常时关闭兜底。仅归还池连接不算物理关闭。中断/丢失后旧 guard 不得再操作。
 151: - ORP 扫描领导权使用独立专用连接与 **单 bigint advisory 锁命名空间**，其生命周期为一轮扫描，业务二元组锁另取。单 Backend/单 worker 约束见 architecture §6。
 152: 
 153: ### 4.4 多 key 加锁顺序
 154: 
 155: - 调用方以去重后的完整 key 集合申请 guard；SQLite 按完整 key 字典序，PG 按 §4.3 的实际冲突域顺序。一次批取齐再发布，部分成功按各自实际加锁顺序逆序释放。不可持部分锁继续或嵌套向同 manager 补取。
 156: - 整批共用 10s deadline。S0/预发布只读会话在取锁前关闭，D23 恢复完成、相关内部事务已关闭后才获取；SQLite 已开启业务写事务时禁止独立连接获取锁行。
 157: - `verify(lease)` 仍为既有 Core port；批 guard、带同业务 session 的 `verify_all` 和 deadline 由 backend 适配层实现。
 158: 
 159: ### 4.5 owner / 接管 / 失配
 160: 
 161: | 场景 | 行为 |
 162: |---|---|
 163: | 同 owner 再次 acquire 同 key | 返回 `None`（不重入），调用方视为编程错误并中止 |
 164: | 租约过期，另一 worker acquire（SQLite） | 允许；token+1；旧 worker 之后 verify/renew 失败 |
 165: | 行租约过期，另一 worker acquire（PG） | 只有拿到 Advisory Lock 才能接管；行过期不构成授权；拿不到则等待/放弃，旧连接存活期间绝不由行 TTL 接管 |
 166: | 旧 worker 在失配后继续写文件 | 禁止；若已进入不可逆步骤，停止并让 ORP 收敛，不得“抢回” |
 167: | release 时 token 已变 | 返回 `False`；不释放、不删除任何文件 |
 168: | 心跳失败 | 标记本地 lease 失效；下一次 verify 前中止；不得继续删除/移动 |
 169: | 进程崩溃 | SQLite 靠过期；PG 连接关闭释放 advisory lock；GC 租约靠过期接管 |
 170: 
 171: ### 4.6 心跳
 172: 
 173: - 每批 guard 至多一个心跳调度，每 15s 续齐持有的租约；操作结束停止。获取 SQLite 至第一把锁后即计时，整批获取不得耗尽其 TTL。
 174: - `renew` 返回 `False`（owner/token/expiry 失配）→ 设置 abort 标志；主流程在下一个不可逆步骤前检查并抛 `STORAGE_LEASE_LOST`。
 175: - SQLite `renew` 遇到 `database is locked/busy` 属于**瞬时竞争**，不是令牌失配：心跳应记录并稍后重试，不得立即 abort；仅当本地已观察到租约过期或 owner/token 不匹配时才 abort。实现必须区分“False（失配）”与“可重试异常”。
 176: - 心跳线程不得执行文件操作、DB 长事务或日志刷屏；失败只记录一次。
 177: - **非事务性批处理**（ORP、staging 清扫）若预计超过 60s，必须分片处理，每片重新获取/释放锁；不得依赖心跳无限延长。
 178: - **上传、Draft、approve 的锁必须持有到对应 DB commit**。耗时文件操作全部在业务写事务前完成；SQLite 主写事务内心跳遇 busy 可退避，commit 前由同 session 验证 token/expiry。失配、到期或无法验证时先回滚，再释放；独立写会话不能在主事务内阻塞等待。
 179: - `verify_all` 由将执行 commit 的同一业务 session 核对所有锁行。SQLite 在本写事务内读取 owner/token/expiry，避免另开连接。PG 在末次提交区间暂停并排空本 guard 的 heartbeat，业务 session 按完整 key 排序锁住各 token 行（`SELECT … FOR UPDATE`），核对 owner/token/expiry，再由独立专用会话只检查会话身份及 advisory 持锁状态。DB token 行锁持至 commit/rollback。若 PG 专用会话在最后检查后断线，接管者仍必须等 token 写成功并提交才能获得可用 guard，期间不能动文件。最终核验/等待有界，异常回滚业务事务后再关闭 guard。
 180: 
~~~

### gc-and-orphan-recovery.md · §6.1 扫描领导权（129–135）

~~~text
 129: ## 6. ORP 独立孤儿扫描
 130: 
 131: ### 6.1 调度与领导权
 132: 
 133: - 间隔 300s；启动后安排首次轻量扫描、后台继续，可停止事件控制。单 Backend、单数据根、单 worker，沿用 ProcessLock；双 worker 用例只取证。生命周期结束时停止 worker 并释放专用连接，再释放 DB/OS 锁。
 134: - PostgreSQL 每轮通过独立物理连接持扫描领导权，使用单 bigint 锁命名空间，详见 storage-and-lock-contract §4.3。取不到则跳过该轮；结束或异常都 unlock/物理关闭。SQLite 依赖既有单实例部署。
 135: 
~~~
