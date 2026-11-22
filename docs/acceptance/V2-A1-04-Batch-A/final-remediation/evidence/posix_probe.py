"""POSIX 文件原语实测（WSL Ubuntu，真实 Linux 内核）。

仅依赖标准库 + 仓库内纯标准库模块：
- app.services.file_write
- app.services.source_instance_id
- app.db.process_lock

JournalStore/SQLAlchemy 依赖在当前 WSL 不可用，未在此脚本中验证。
运行：PYTHONPATH=/mnt/d/ExplainLab/backend python3 posix_probe.py
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path


def check(name: str, condition: bool, detail: dict | None = None) -> None:
    status = "PASS" if condition else "FAIL"
    print(json.dumps({"check": name, "status": status, "detail": detail or {}}, ensure_ascii=False))
    if not condition:
        raise SystemExit(1)


def main() -> None:
    import app.services.file_write as file_write
    import app.services.source_instance_id as instance_module
    from app.db.process_lock import ProcessLock
    from app.services.file_write import write_all
    from app.services.source_instance_id import SourceInstanceIdStore

    with tempfile.TemporaryDirectory(prefix="explainlab-posix-") as raw:
        root = Path(raw)
        data = root / "data"
        data.mkdir()

        store = SourceInstanceIdStore(data)
        created = store.ensure()
        mode = stat.S_IMODE(store.path.stat().st_mode)
        check("id_create_mode_0600", mode == 0o600, {"mode": oct(mode), "id": created})

        same = store.ensure()
        check("id_ensure_idempotent", same == created and store.read() == created)

        # 并发 ensure：8 个独立进程争抢同一目录，必须收敛到同一 ID。
        worker = (
            "import sys\n"
            "from pathlib import Path\n"
            "from app.services.source_instance_id import SourceInstanceIdStore\n"
            "print(SourceInstanceIdStore(Path(sys.argv[1])).ensure())\n"
        )
        concurrent_dir = root / "concurrent"
        concurrent_dir.mkdir()
        procs = [
            subprocess.Popen(
                [sys.executable, "-c", worker, str(concurrent_dir)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            for _ in range(8)
        ]
        outputs = []
        for proc in procs:
            out, err = proc.communicate(timeout=30)
            if proc.returncode != 0:
                check("id_concurrent_ensure", False, {"stderr": err[-500:]})
                return
            outputs.append(out.strip())
        final_ids = {SourceInstanceIdStore(concurrent_dir).read()}
        check(
            "id_concurrent_ensure",
            len(set(outputs)) == 1 and final_ids == set(outputs),
            {"ids": sorted(set(outputs)), "file": sorted(final_ids)},
        )

        # 硬链接不受支持的回退路径（真实 O_EXCL 独占创建）。
        fallback_dir = root / "fallback"
        fallback_dir.mkdir()
        real_link = os.link
        try:
            os.link = lambda *a, **k: (_ for _ in ()).throw(OSError("injected no link"))
            fallback_id = SourceInstanceIdStore(fallback_dir).ensure()
        finally:
            os.link = real_link
        fallback_mode = stat.S_IMODE((fallback_dir / "source-instance-id").stat().st_mode)
        check(
            "id_fallback_exclusive_create",
            bool(fallback_id) and fallback_mode == 0o600,
            {"mode": oct(fallback_mode)},
        )

        # POSIX 目录 fsync：确认 _sync_dir 对目录 fd 实际调用 fsync。
        dir_fsync_calls = []
        real_fsync = os.fsync

        def recording_fsync(fd: int) -> None:
            try:
                is_dir = stat.S_ISDIR(os.fstat(fd).st_mode)
            except OSError:
                is_dir = False
            if is_dir:
                dir_fsync_calls.append(fd)
            real_fsync(fd)

        fsync_dir = root / "fsync-dir"
        fsync_dir.mkdir()
        instance_module.os.fsync = recording_fsync
        try:
            SourceInstanceIdStore(fsync_dir).ensure()
        finally:
            instance_module.os.fsync = real_fsync
        check("posix_dir_fsync_called", len(dir_fsync_calls) >= 1, {"count": len(dir_fsync_calls)})

        # replace 原子替换：旧 ID 在替换前保持可读，替换后为新值。
        replace_store = SourceInstanceIdStore(root / "replace")
        old_id = replace_store.ensure()
        new_id = "f0e8400a-e29b-41d4-a716-446655440099"
        replace_store.replace(new_id)
        check(
            "id_replace_atomic",
            replace_store.read() == new_id and new_id != old_id,
            {"old": old_id, "new": new_id},
        )

        # write_all 对 EINTR 重试。
        target = root / "eintr.bin"
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        real_write = os.write
        calls = 0

        def interrupted(descriptor: int, payload) -> int:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise InterruptedError("injected EINTR")
            return real_write(descriptor, payload)

        file_write.os.write = interrupted
        try:
            write_all(fd, b"posix-eintr")
        finally:
            file_write.os.write = real_write
            os.close(fd)
        check(
            "write_all_eintr_retry",
            target.read_bytes() == b"posix-eintr" and calls == 2,
            {"calls": calls},
        )

        # fcntl/flock 跨进程互斥（同一锁文件）。
        lock_dir = root / "lock"
        lock_dir.mkdir()
        lock = ProcessLock(lock_dir, timeout_seconds=0.3, initial_backoff=0.05, max_backoff=0.1)
        lock.acquire()
        child = (
            "import sys\n"
            "from pathlib import Path\n"
            "from app.db.process_lock import ProcessLock, ProcessLockError\n"
            "try:\n"
            "    ProcessLock(Path(sys.argv[1]), timeout_seconds=0.2, initial_backoff=0.05, max_backoff=0.1).acquire()\n"
            "except ProcessLockError as exc:\n"
            "    print(exc.code)\n"
            "    raise SystemExit(2)\n"
            "print('ACQUIRED')\n"
        )
        conflict = subprocess.run(
            [sys.executable, "-c", child, str(lock_dir)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        lock.release()
        check(
            "process_lock_cross_process_contention",
            conflict.returncode == 2
            and conflict.stdout.strip() == "BACKEND_ALREADY_RUNNING",
            {"returncode": conflict.returncode, "stdout": conflict.stdout.strip()},
        )
        after = subprocess.run(
            [sys.executable, "-c", child, str(lock_dir)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        lock_mode = stat.S_IMODE((lock_dir / ".explainlab.process.lock").stat().st_mode)
        check(
            "process_lock_release_allows_child",
            after.returncode == 0 and after.stdout.strip() == "ACQUIRED" and lock_mode == 0o600,
            {"returncode": after.returncode, "mode": oct(lock_mode)},
        )

    print(
        json.dumps(
            {
                "check": "journal_store_full_import",
                "status": "UNVERIFIED",
                "detail": {
                    "reason": "WSL Ubuntu 26.04 has Python 3.14 without pip/SQLAlchemy; "
                    "full backend test suite not runnable in this POSIX environment"
                },
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()