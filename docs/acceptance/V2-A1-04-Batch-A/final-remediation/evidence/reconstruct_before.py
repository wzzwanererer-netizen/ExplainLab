"""重建 final-remediation 整改前快照（逆向应用本轮编辑）。

Batch A 文件未提交、无 Git 历史快照。对每一处本轮编辑，按“当前 -> 整改前”的
精确字节替换逆向应用；每处 `current` 必须恰好出现 1 次，否则立即失败（不猜测）。
输出写入 final-remediation/before/，供 diff 与 SHA-256 对照。

用法（仓库根目录）：python docs/acceptance/.../evidence/reconstruct_before.py
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
PKG = Path(__file__).resolve().parents[1]
BEFORE = PKG / "before"
AUDIT = PKG.parent / "audit-round2" / "02-code"

# 本轮开始前已由 round2 审计快照留存的文件
SNAPSHOTS = {
    "backend/app/services/source_identity.py": "source_identity.py",
    "backend/app/services/source_instance_id.py": "source_instance_id.py",
    "backend/tests/test_markdown_batch_a_identity.py": "test_markdown_batch_a_identity.py",
}

REVERSE_EDITS: dict[str, list[tuple[bytes, bytes]]] = {
    "backend/app/services/markdown.py": [
        (
            (
                "        # P1-02：身份分类校验、导入 DB 写入与 commit 必须与 MATERIALIZE/ROTATE\n"
                "        # 串行（同一 Journal 锁），避免并发导出物化后导入追加 ImportOrigin。\n"
                "        with self._coordinator.keyed(lock_key), self._identity.identity_guard():\n"
            ).encode(),
            b"        with self._coordinator.keyed(lock_key):\n",
        ),
        (
            (
                "        if existing is not None and self._identity.has_committed_materialize(\n"
                "            existing.id\n"
                "        ):\n"
                "            # §22.2：ImportOrigin 与 COMMITTED MATERIALIZE 并存即冲突态。\n"
                "            # 已物化本地文档不得经导入追加来源身份或重写实例字段（2b 冻结）。\n"
                "            raise MarkdownServiceError(\n"
                "                SOURCE_IDENTITY_CONFLICT,\n"
                '                "目标条目为已物化本地文档，导入不得追加来源身份",\n'
                "                status_code=409,\n"
                "            )\n"
            ).encode(),
            b"",
        ),
    ],
    "backend/app/services/import_review_hook.py": [
        (
            b"from app.services.source_identity import SourceIdentityService\n",
            b"",
        ),
        (
            (
                b"    def __init__(self, session: Session, identity: SourceIdentityService) -> None:\n"
                b"        self._session = session\n"
                b"        self._identity = identity\n"
            ),
            (
                b"    def __init__(self, session: Session) -> None:\n"
                b"        self._session = session\n"
            ),
        ),
        (
            (
                "        if self._identity.has_committed_materialize(record.id):\n"
                "            # §22.2：审核批准时条目已被物化 → 追加 ImportOrigin 会造成冲突态。\n"
                "            # 在写任何导入字段前 fail-closed；路由回滚整个审核事务。\n"
                "            raise MarkdownServiceError(\n"
                '                "SOURCE_IDENTITY_CONFLICT",\n'
                '                "目标条目已物化，导入审核不得追加来源身份",\n'
                "                status_code=409,\n"
                "            )\n"
                "\n"
            ).encode(),
            b"",
        ),
    ],
    "backend/app/api/routes/governance.py": [
        (
            (
                "    coordinator: ImportCoordinator = request.app.state.import_coordinator\n"
                '    identity = getattr(request.app.state, "source_identity", None)\n'
                "    if identity is None:\n"
                '        raise HTTPException(status_code=503, detail="identity_service_unavailable")\n'
                "    context = coordinator.keyed(lock_key) if lock_key else _null_context()\n"
                "    # P1-02：审核批准的身份写入与 MATERIALIZE/ROTATE 串行；钩子在写前校验\n"
                "    # 目标条目未被物化，冲突时整事务回滚、审核单保持 PENDING。\n"
                "    with context, identity.identity_guard():\n"
            ).encode(),
            (
                b"    coordinator: ImportCoordinator = request.app.state.import_coordinator\n"
                b"    context = coordinator.keyed(lock_key) if lock_key else _null_context()\n"
                b"    with context:\n"
            ),
        ),
        (
            (
                b"    coordinator: ImportCoordinator = request.app.state.import_coordinator\n"
                b'    identity = getattr(request.app.state, "source_identity", None)\n'
                b"    if identity is None:\n"
                b'        raise HTTPException(status_code=503, detail="identity_service_unavailable")\n'
                b"    context = coordinator.keyed(lock_key) if lock_key else _null_context()\n"
                b"    with context:\n"
            ),
            (
                b"    coordinator: ImportCoordinator = request.app.state.import_coordinator\n"
                b"    context = coordinator.keyed(lock_key) if lock_key else _null_context()\n"
                b"    with context:\n"
            ),
        ),
        (
            b"ImportReviewHook(session, identity).apply_approved(review, envelope)",
            b"ImportReviewHook(session).apply_approved(review, envelope)",
        ),
        (
            b"ImportReviewHook(session, identity).apply_rejected(review)",
            b"ImportReviewHook(session).apply_rejected(review)",
        ),
    ],
}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    BEFORE.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    failures: list[str] = []
    for rel, snap in SNAPSHOTS.items():
        src = AUDIT / snap
        if not src.is_file():
            failures.append(f"missing snapshot {src}")
            continue
        data = src.read_bytes()
        (BEFORE / rel.replace("/", "__")).write_bytes(data)
        cur = sha((ROOT / rel).read_bytes())
        lines.append(f"{rel}\tbefore={sha(data)}\tafter={cur}\t{'same' if sha(data) == cur else 'changed'}")
    for rel, edits in REVERSE_EDITS.items():
        data = (ROOT / rel).read_bytes()
        for idx, (new, old) in enumerate(edits, 1):
            count = data.count(new)
            if count != 1:
                failures.append(f"{rel} edit {idx}: current snippet count={count} (expect 1)")
                break
            data = data.replace(new, old)
        else:
            (BEFORE / rel.replace("/", "__")).write_bytes(data)
            cur = sha((ROOT / rel).read_bytes())
            lines.append(f"{rel}\tbefore={sha(data)}\tafter={cur}\tchanged(reconstructed)")
    if failures:
        print("FAILED:")
        for f in failures:
            print("  " + f)
        return 1
    out = PKG / "before-sha256.tsv"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"reconstructed {len(lines)} files -> {BEFORE}")
    print(out.read_text(encoding="utf-8"), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())