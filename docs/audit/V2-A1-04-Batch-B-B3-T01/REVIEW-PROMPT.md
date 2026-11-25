# B3-T01 独立审计请求（整改复审）

请对 ExplainLab V2 · Batch B · B3-T01 的**整改后实现**做独立复核。结论请明确区分 PASS / CONDITIONAL PASS / FAIL，不要以文档自述代替源码核对。

## 1. 审计范围

- B3-T01：Manifest Schema 与 Staging Service。
- 本轮整改项：P1-01、P1-02、P2-01、P2-02、P2-03，以及 ZIP-01…ZIP-05。
- 不包含：B3-T02、B4、B5（未实现，不应按已实现审核）。

## 2. 必读材料

- `acceptance/B3-T01-remediation-report.md`
- `acceptance/guard-lifetime-proof.md`
- `acceptance/posix-durability.md`
- `acceptance/empty-attachment-rejection.md`
- `acceptance/corrupt-zip-mapping.md`
- `acceptance/pending-fail-closed.md`
- `acceptance/unresolved.md`
- `source/` 下的精确源码快照

## 3. 重点核对

1. `stage_from_zip` 的 guard 是否在目录创建前获取、覆盖 ReviewRequest 与 commit、提交后释放；已知失败是否在仍持 guard 时清理；commit 结果不明确是否保留 staging。
2. `_import_one` 是否在 guard 内 commit，失败分支是否正确设置 `keep_for_orp`，是否存在自锁或锁序倒置。
3. `_reuse_pending` 是否在 guard 内重读 pending 并校验 `.complete`/文件/hash，陈旧 pending 是否 409。
4. POSIX 目录 fsync 顺序是否覆盖根、staging、blobs、`.complete`；失败是否稳定 503；Windows no-op 是否被诚实记录而未声称断电持久。
5. 零字节附件是否在元数据阶段 400 `ATTACHMENT_EMPTY`，且零 staging、零 DB 写入。
6. 损坏 CRC/Deflate/截断流是否映射 400 `IMPORT_ARCHIVE_INVALID`，是否存在漏网的 500 路径。
7. `pending_staging_ids()` 的 `None` 是否在所有调用点 fail-closed。
8. `orig_filename` NUL、全 ZIP 压缩预算、根 manifest 预算是否真实生效；100 MiB 是否未放宽。
9. 测试是否真实使用 tmp FS/SQLite，是否存在 mock 冒充；skip 是否被误记为 pass。
10. B1/B2 生产文件是否未被本轮修改；`test_attachment_api.py` 的哈希漂移是否有 mtime 证据说明其早于本轮。

## 4. 验证命令

```bash
unzip ExplainLab-B3-T01-Remediation-Audit-Package.zip -d b3
cd b3
sha256sum -c PACKAGE-SHA256SUMS
```

源码对照：

```bash
sha256sum -c SOURCE-SHA256SUMS
```

## 5. 已知未验证项（不得视为通过）

- 真实 PostgreSQL：未连接（`EXPLAINLAB_PG_TEST_URL` 未设置）。
- 真实 POSIX 主机：未执行；Windows 上目录 fsync 为 no-op。
- 进程 kill / 断电一致性：未取证。
- 100 MiB 仅验证“解析器拒绝 100 MiB+1”，未做 100 MiB 级成功导入。
- 第二 Windows 卷/跨卷：未验证。

## 6. 约束

- 本轮未提交、未推送。
- 不得以文档结论替代源码与日志核对。
- 最终状态必须保持 **B3-T01 IMPLEMENTED / PENDING INDEPENDENT REVIEW**，直到独立审计给出结论。