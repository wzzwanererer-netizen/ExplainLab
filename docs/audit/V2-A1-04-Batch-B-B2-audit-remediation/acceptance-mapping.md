# B2 整改后的 ATT-01～13 验收映射

Windows HTTP 专项使用真实 SQLite 文件库和目录。PG 列记录 PostgreSQL 18.6 实机执行覆盖和未重复执行的分支。[原审核映射](../V2-A1-04-Batch-B-B2/acceptance-mapping.md)

| 编号 | SQLite / 文件系统回归 | PG HTTP 实测范围 |
| --- | --- | --- |
| ATT-01 | 上传 PNG，核对分片、哈希、行与临时目录 | 上传/下载及跨 item 共享用例 |
| ATT-02 | 同 item 重复复用，跨 item 共享一份 blob | 双请求同 item 201/200，跨 item 两引用一 blob |
| ATT-03 | 非法 Base64、空内容、超限拒绝，库和盘零写入 | 错误分支未在 PG 重复执行 |
| ATT-04 | PNG/PDF magic 与文本声明分支 | 仅覆盖成功上传的 PNG |
| ATT-05 | SVG MIME 拒绝，文本 SVG 按声明保存 | SVG 分支未在 PG 重复执行 |
| ATT-06 | 路径、控制字符、保留名、Unicode 下载头 | 文件名边界未在 PG 重复执行 |
| ATT-07 | item 作用域、响应头、下载字节 | 下载结果、ETag；跨 item 访问拒绝未重复执行 |
| ATT-08 | 删除共享引用不入队，删除最后引用入队 | 删除共享引用，不入队且 blob 保留 |
| ATT-09 | 真实文件缺失、损坏、单已校验句柄与大文件流 | 损坏、缺失和单句柄专项未在 PG 重复执行 |
| ATT-10 | 同 item 与跨 item 双请求，核对引用和物理文件 | 同 item 真实双请求，两个 PG backend、真实 advisory、一个引用和文件。GC/ORP 组合留在冻结后续阶段 |
| ATT-11 | 提交失败及归档抢先导致零行、孤儿 blob、临时清理 | 提交/回滚与 advisory release 观察；归档先提交。24h ORP 留在 B5 |
| ATT-12 | 新增真实发布 syscall 注入，Windows link 和 rename 分别返回 503、稳定码、零行零临时零 blob | PG 专项范围为 HTTP 事务与 advisory，底层 I/O 失败映射由 SQLite HTTP 用例执行 |
| ATT-13 | 稳定排序、archived 上传拒绝和读删允许 | 用 `pg_blocking_pids` 观察真实归档竞态。排序、归档读取和删除沿 SQLite 证据 |

[Windows B2 API 日志](evidence/b2-api-windows.log) · [ATT-12 证据](ATT-12-evidence.md) · [PG 执行状态](PostgreSQL-HTTP.md)
