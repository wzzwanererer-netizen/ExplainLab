# 最终定点验收 · Git 状态

- 基线及 HEAD 为 `970c0d8ec05f0b8c68286839a56b14c74ea230c6`，分支 `fix/m0-admission-and-m5-regressions`。暂存区为空。
- Git 原始统计仍列此前已有的 4 个 tracked 后端改动。四个本轮测试文件原已处于未跟踪状态，所以同时用原 Linux 输入包作前像，另录 `git diff --no-index --numstat`。四个覆盖文件与 WSL 执行时使用的 SHA-256 逐一一致。
- 与前轮选定的 180 个文件比较，133 个字节一致，43 个仅换行不同，4 个为本轮测试变更，意外内容差异为 0。Repository、锁、启动与存储的生产实现、冻结设计、迁移、依赖锁和 `MILESTONES.md` 未在本轮改动。
- 无暂存、提交、推送、reset、clean 或 stash。Git 快照采于文档和证据生成之后、ZIP 打包之前。

[Git porcelain v2 / diff / 未跟踪路径原始输出](evidence/git-scope.log) · [源码范围与测试摘要](evidence/source-scope.json) · [WSL 实际测试 SHA-256](evidence/wsl-final.g8LQ7isi/round-test-sha256.log)
