# Git 状态和范围

基线与 HEAD 均为 `970c0d8ec05f0b8c68286839a56b14c74ea230c6`。分支为 `fix/m0-admission-and-m5-regressions`。启动诊断时已有 4 个 tracked 后端文件改动，另有 2 个未跟踪 B1 实现文件、7 个未跟踪 B1 测试文件和历史交付件。开始时暂存区为空。

本轮仅在 `docs/acceptance/V2-A1-04-Batch-B-B1-environment-recovery/` 写入本次交付件。未修改业务源码、测试、冻结文件、迁移、锁文件或台账。未暂存、提交或推送。Git 清单见原始诊断编号 16–19 及结束核对。

Linux 执行结束时再次核对 HEAD 和暂存区，暂存区为空。原始工作树仅追加本轮验收材料及脚本，见 [最终 Git 输出](evidence/git-after-linux.json)。

交付复核比较 Linux 输入包与 Windows 当前工作区的 180 个源码、测试、迁移、冻结及配置文件。其中 137 项字节一致，43 项仅 CRLF/LF 不同，无内容差异。HEAD 与暂存区核验通过。交付目录外 Git 状态与首轮 Linux 测试结束时一致。[范围核对](evidence/final-source-compare.json) · [交付 Git 状态](evidence/git-handoff.json)
