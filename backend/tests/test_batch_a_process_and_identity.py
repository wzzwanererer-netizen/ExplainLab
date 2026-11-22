"""A1-04 Batch A：OS 单实例锁、source-instance-id、导入锁与同步线程模型验收。

全部使用真实文件系统 / 真实 SQLite / 真实子进程；不 mock 平台锁语义。
"""

from __future__ import annotations

import ast
import asyncio
import inspect
import os
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.api.routes import governance, import_export
from app.db.process_lock import (
    BACKEND_ALREADY_RUNNING,
    ProcessLock,
    ProcessLockError,
    process_lock_path,
)
from app.db.session import get_session_factory
from app.models import ImportOriginORM, KnowledgeItemORM
from app.services.import_coordinator import (
    IMPORT_LOCK_TIMEOUT,
    ImportCoordinator,
    ImportLockTimeout,
)
from app.services.markdown import MarkdownImportDocument
from app.services.source_instance_id import (
    SOURCE_INSTANCE_ID_INVALID,
    SOURCE_INSTANCE_ID_UNAVAILABLE,
    SourceInstanceIdError,
    SourceInstanceIdStore,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
ASYNC_INSTANCE = "550e8400-e29b-41d4-a716-446655440000"
ASYNC_DOC = "660e8400-e29b-41d4-a716-446655440001"
ASYNC_INSTANCE2 = "770e8400-e29b-41d4-a716-446655440002"
ASYNC_DOC2 = "660e8400-e29b-41d4-a716-446655440003"


def _child_env() -> dict[str, str]:
    env = dict(os.environ)
    existing = env.get("PYTHONPATH")
    backend = str(REPO_ROOT / "backend")
    env["PYTHONPATH"] = backend if not existing else f"{backend}{os.pathsep}{existing}"
    return env


def _run_child(script: str, *args: str, timeout: float = 30) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", script, *args],
        cwd=str(REPO_ROOT),
        env=_child_env(),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


LOCK_SCRIPT = """
import sys
from pathlib import Path
from app.db.process_lock import ProcessLock, ProcessLockError
lock = ProcessLock(Path(sys.argv[1]), timeout_seconds=0.4, initial_backoff=0.05, max_backoff=0.1)
try:
    lock.acquire()
except ProcessLockError as exc:
    print(exc.code, flush=True)
else:
    print("ACQUIRED", flush=True)
    if len(sys.argv) > 2 and sys.argv[2] == "crash":
        import os
        os._exit(0)
    lock.release()
"""

INSTANCE_SCRIPT = """
import sys
from pathlib import Path
from app.services.source_instance_id import SourceInstanceIdStore
print(SourceInstanceIdStore(Path(sys.argv[1])).ensure(), flush=True)
"""


class TestProcessLock:
    def test_lock_path_and_same_object_guard(self, tmp_path: Path):
        lock = ProcessLock(tmp_path, timeout_seconds=0.2)
        assert lock.path == process_lock_path(tmp_path)
        assert lock.path.name == ".explainlab.process.lock"
        assert ProcessLock(tmp_path)._timeout == 10.0
        lock.acquire()
        assert lock.acquired
        with pytest.raises(ProcessLockError):
            lock.acquire()
        lock.release()
        assert not lock.acquired
        lock.release()  # 幂等
        assert lock.path.exists()  # 锁文件永不删除

    def test_second_object_same_process_refused_by_registry(self, tmp_path: Path):
        first = ProcessLock(tmp_path, timeout_seconds=0.2)
        second = ProcessLock(tmp_path, timeout_seconds=0.2)
        first.acquire()
        started = time.monotonic()
        with pytest.raises(ProcessLockError) as excinfo:
            second.acquire()
        assert excinfo.value.code == BACKEND_ALREADY_RUNNING
        assert time.monotonic() - started < 2.0
        first.release()
        second.acquire()
        second.release()

    def test_context_manager(self, tmp_path: Path):
        with ProcessLock(tmp_path, timeout_seconds=0.2) as lock:
            assert lock.acquired
        assert not lock.acquired

    def test_cross_process_refusal_then_release(self, tmp_path: Path):
        parent = ProcessLock(tmp_path, timeout_seconds=0.2)
        parent.acquire()
        try:
            blocked = _run_child(LOCK_SCRIPT, str(tmp_path))
            assert blocked.returncode == 0, blocked.stderr
            assert blocked.stdout.strip() == BACKEND_ALREADY_RUNNING
        finally:
            parent.release()
        allowed = _run_child(LOCK_SCRIPT, str(tmp_path))
        assert allowed.returncode == 0, allowed.stderr
        assert allowed.stdout.strip() == "ACQUIRED"

    def test_os_releases_lock_on_process_crash(self, tmp_path: Path):
        crashed = _run_child(LOCK_SCRIPT, str(tmp_path), "crash")
        assert crashed.returncode == 0, crashed.stderr
        assert crashed.stdout.strip() == "ACQUIRED"
        lock = ProcessLock(tmp_path, timeout_seconds=1.0)
        lock.acquire()
        lock.release()


class TestSourceInstanceId:
    @pytest.mark.parametrize(
        "raw",
        [
            b"550E8400-E29B-41D4-A716-446655440000\n",  # uppercase
            b"550e8400-e29b-11d4-a716-446655440000\n",  # v1
            b"\xef\xbb\xbf550e8400-e29b-41d4-a716-446655440000\n",  # BOM
            b" 550e8400-e29b-41d4-a716-446655440000\n",
            b"550e8400-e29b-41d4-a716-446655440000\n\n",
            b"550e8400-e29b-41d4-a716-446655440000\r\n",
            b"not-a-uuid\n",
            b"\xff\xfe\n",
        ],
    )
    def test_invalid_existing_file_fails_closed_without_rewrite(
        self, tmp_path: Path, raw: bytes
    ):
        store = SourceInstanceIdStore(tmp_path)
        store.path.parent.mkdir(parents=True, exist_ok=True)
        store.path.write_bytes(raw)
        with pytest.raises(SourceInstanceIdError) as excinfo:
            store.ensure()
        assert excinfo.value.code == SOURCE_INSTANCE_ID_INVALID
        assert store.path.read_bytes() == raw

    def test_missing_file_is_unavailable(self, tmp_path: Path):
        with pytest.raises(SourceInstanceIdError) as excinfo:
            SourceInstanceIdStore(tmp_path).read()
        assert excinfo.value.code == SOURCE_INSTANCE_ID_UNAVAILABLE

    def test_ensure_creates_canonical_v4_and_is_stable(self, tmp_path: Path):
        store = SourceInstanceIdStore(tmp_path)
        first = store.ensure()
        text = store.path.read_text(encoding="ascii")
        assert text == first + "\n"
        assert len(first) == 36 and first == first.lower()
        assert store.ensure() == first
        assert SourceInstanceIdStore(tmp_path).ensure() == first
        assert not list(tmp_path.glob(".source-instance-id.*.tmp"))

    def test_replace_is_atomic_and_validates(self, tmp_path: Path):
        store = SourceInstanceIdStore(tmp_path)
        store.ensure()
        new = "f0e8400a-e29b-41d4-a716-446655440099"
        store.replace(new)
        assert store.read() == new
        with pytest.raises(SourceInstanceIdError) as excinfo:
            store.replace("not-a-uuid")
        assert excinfo.value.code == SOURCE_INSTANCE_ID_INVALID
        assert store.read() == new
        assert not list(tmp_path.glob(".source-instance-id.*.tmp"))

    def test_concurrent_cross_process_creation_yields_single_id(self, tmp_path: Path):
        env = _child_env()
        processes = [
            subprocess.Popen(
                [sys.executable, "-c", INSTANCE_SCRIPT, str(tmp_path)],
                cwd=str(REPO_ROOT),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            for _ in range(4)
        ]
        outputs = []
        for process in processes:
            stdout, stderr = process.communicate(timeout=30)
            assert process.returncode == 0, stderr
            outputs.append(stdout.strip())
        assert len(set(outputs)) == 1
        assert SourceInstanceIdStore(tmp_path).read() == outputs[0]
        assert not [
            path for path in tmp_path.iterdir() if path.name.endswith(".tmp")
        ]


class TestImportCoordinator:
    def test_same_key_serializes(self):
        coordinator = ImportCoordinator(wait_seconds=2)
        order: list[str] = []
        entered = threading.Event()
        release = threading.Event()

        def first():
            with coordinator.keyed("k"):
                order.append("first-enter")
                entered.set()
                release.wait(3)
                order.append("first-exit")

        def second():
            entered.wait(3)
            with coordinator.keyed("k"):
                order.append("second-enter")

        threads = [threading.Thread(target=first), threading.Thread(target=second)]
        for thread in threads:
            thread.start()
        entered.wait(3)
        time.sleep(0.1)
        assert order == ["first-enter"]
        release.set()
        for thread in threads:
            thread.join(3)
        assert order == ["first-enter", "first-exit", "second-enter"]
        assert coordinator.waiting_keys == 0

    def test_different_keys_do_not_block(self):
        coordinator = ImportCoordinator(wait_seconds=2)
        entered = threading.Event()
        release = threading.Event()

        def holder():
            with coordinator.keyed("a"):
                entered.set()
                release.wait(3)

        thread = threading.Thread(target=holder)
        thread.start()
        assert entered.wait(3)
        started = time.monotonic()
        with coordinator.keyed("b"):
            assert time.monotonic() - started < 1.0
        release.set()
        thread.join(3)
        assert coordinator.waiting_keys == 0

    def test_timeout_is_bounded_and_reports_stable_code(self):
        coordinator = ImportCoordinator(wait_seconds=0.2)
        entered = threading.Event()
        release = threading.Event()

        def holder():
            with coordinator.keyed("busy"):
                entered.set()
                release.wait(3)

        thread = threading.Thread(target=holder)
        thread.start()
        assert entered.wait(3)
        started = time.monotonic()
        with pytest.raises(ImportLockTimeout) as excinfo, coordinator.keyed("busy"):
            pass
        elapsed = time.monotonic() - started
        assert excinfo.value.code == IMPORT_LOCK_TIMEOUT
        assert 0.15 <= elapsed < 1.5
        assert coordinator.is_held("busy")
        release.set()
        thread.join(3)
        assert coordinator.waiting_keys == 0

    def test_registry_reclaims_after_exception(self):
        coordinator = ImportCoordinator()
        with pytest.raises(RuntimeError), coordinator.keyed("k"):
            raise RuntimeError("boom")
        assert coordinator.waiting_keys == 0
        assert not coordinator.is_held("k")


class TestSyncThreadModel:
    def test_write_routes_are_sync_def(self):
        for endpoint in (
            import_export.import_markdown,
            import_export.import_markdown_batch,
            import_export.export_markdown,
            import_export.export_single_markdown,
            governance.approve_review,
            governance.reject_review,
        ):
            assert not inspect.iscoroutinefunction(endpoint)

    def test_s0_is_closed_before_lock_and_sessions_stay_on_one_thread(
        self, client: TestClient, monkeypatch
    ):
        service = client.app.state.markdown_service
        real_factory = service._factory
        opened: list = []
        closed: set[int] = set()
        threads: set[int] = set()
        lock_checked = threading.Event()

        class TrackingFactory:
            def __call__(self):
                session = real_factory()
                opened.append(session)
                threads.add(threading.get_ident())
                original_close = session.close

                def tracking_close():
                    original_close()
                    closed.add(id(session))

                session.close = tracking_close
                return session

        coordinator = client.app.state.import_coordinator
        original_keyed = coordinator.keyed

        @contextmanager
        def checking_keyed(key):
            assert opened
            assert all(id(session) in closed for session in opened)
            threads.add(threading.get_ident())
            lock_checked.set()
            with original_keyed(key):
                yield

        monkeypatch.setattr(service, "_factory", TrackingFactory())
        monkeypatch.setattr(coordinator, "keyed", checking_keyed)
        response = client.post(
            "/api/knowledge/import", json={"content": "# 线程\n\n正文", "filename": "t.md"}
        )
        assert response.status_code == 201, response.text
        assert lock_checked.is_set()
        assert len(threads) == 1

    def test_single_import_lock_timeout_maps_to_409(
        self, client: TestClient
    ):
        created = client.post(
            "/api/knowledge", json={"title": "目标", "content": "正文"}
        ).json()
        coordinator = client.app.state.import_coordinator
        old_wait = coordinator._wait_seconds
        coordinator._wait_seconds = 0.2
        entered = threading.Event()
        release = threading.Event()

        def holder():
            with coordinator.keyed(f"target-item:{created['id']}"):
                entered.set()
                release.wait(5)

        thread = threading.Thread(target=holder)
        thread.start()
        assert entered.wait(5)
        try:
            response = client.post(
                "/api/knowledge/import",
                json={
                    "content": "---\ntitle: 更新\n---\n正文",
                    "filename": "blocked.md",
                    "target_item_id": created["id"],
                },
            )
            assert response.status_code == 409
            assert response.json()["detail"] == IMPORT_LOCK_TIMEOUT
        finally:
            release.set()
            thread.join(5)
            coordinator._wait_seconds = old_wait
        item = client.get(f"/api/knowledge/{created['id']}").json()
        assert item["title"] == "目标"

    def test_batch_import_isolates_lock_timeout_per_item(self, client: TestClient):
        created = client.post(
            "/api/knowledge", json={"title": "目标", "content": "正文"}
        ).json()
        coordinator = client.app.state.import_coordinator
        old_wait = coordinator._wait_seconds
        coordinator._wait_seconds = 0.2
        entered = threading.Event()
        release = threading.Event()

        def holder():
            with coordinator.keyed(f"target-item:{created['id']}"):
                entered.set()
                release.wait(5)

        thread = threading.Thread(target=holder)
        thread.start()
        assert entered.wait(5)
        try:
            response = client.post(
                "/api/knowledge/import/batch",
                json={
                    "documents": [
                        {
                            "content": "---\ntitle: 更新\n---\n正文",
                            "filename": "blocked.md",
                            "target_item_id": created["id"],
                        },
                        {
                            "content": "---\ntitle: 新条目\n---\n新正文",
                            "filename": "new.md",
                        },
                    ]
                },
            )
            assert response.status_code == 200, response.text
            body = response.json()
            statuses = [item["status"] for item in body["items"]]
            assert "error" in statuses
            assert "created" in statuses
            blocked = next(item for item in body["items"] if item["status"] == "error")
            assert blocked["errors"] == [IMPORT_LOCK_TIMEOUT]
        finally:
            release.set()
            thread.join(5)
            coordinator._wait_seconds = old_wait
        assert client.get(f"/api/knowledge/{created['id']}").json()["title"] == "目标"

class TestAsyncAndCancellation:
    def test_exception_rolls_back_closes_session_before_lock_release(
        self, client: TestClient, monkeypatch
    ):
        """R1.2-ASYNC-04：失败/取消路径先 Rollback + close，再释放身份锁。"""
        service = client.app.state.markdown_service
        coordinator = client.app.state.import_coordinator
        events: list[str] = []
        real_factory = service._factory

        class TrackingFactory:
            def __call__(self):
                session = real_factory()
                original_close = session.close
                original_rollback = session.rollback

                def tracking_close():
                    original_close()
                    events.append("close")

                def tracking_rollback():
                    original_rollback()
                    events.append("rollback")

                session.close = tracking_close
                session.rollback = tracking_rollback
                return session

        original_keyed = coordinator.keyed

        @contextmanager
        def tracking_keyed(key):
            events.append("lock-enter")
            with original_keyed(key):
                try:
                    yield
                finally:
                    events.append("lock-exit")

        def boom(*args, **kwargs):
            events.append("apply")
            raise RuntimeError("injected apply failure")

        monkeypatch.setattr(service, "_factory", TrackingFactory())
        monkeypatch.setattr(coordinator, "keyed", tracking_keyed)
        monkeypatch.setattr(service, "_apply_import", boom)
        outcome = service.import_documents(
            [MarkdownImportDocument(content="# 失败\n\n正文", filename="fail.md")]
        )
        assert outcome.report.items[0].errors == ["IMPORT_FAILED"]
        assert events.index("apply") < events.index("rollback")
        assert events.index("rollback") < events.index("lock-exit")
        assert events[-1] == "lock-exit"
        assert coordinator.waiting_keys == 0

    def test_no_async_lock_architecture(self, client: TestClient):
        """R1.2-ASYNC-06：只有同步身份锁一套，无 async keyed lock 双架构。"""
        import app.services.import_coordinator as coordinator_module
        import app.services.markdown as markdown_module

        for module in (coordinator_module, markdown_module):
            source = inspect.getsource(module)
            assert "asyncio.Lock" not in source
            assert "asyncio.Semaphore" not in source
            assert not any(
                isinstance(node, ast.AsyncFunctionDef)
                for node in ast.walk(ast.parse(source))
            )
        coordinator = client.app.state.import_coordinator
        assert type(coordinator._guard) is type(threading.Lock())
        assert coordinator is client.app.state.import_coordinator

    async def test_same_identity_concurrent_requests_serialize(
        self, client: TestClient
    ):
        """R1.2-ASYNC-07：同身份并发串行，不产生重复条目/来源。"""
        body = {
            "content": (
                "---\ntitle: 并发\n"
                f"source_instance_id: {ASYNC_INSTANCE}\n"
                f"source_document_id: {ASYNC_DOC}\n---\n正文"
            ),
            "filename": "concurrent.md",
        }
        transport = httpx.ASGITransport(app=client.app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as async_client:
            responses = await asyncio.gather(
                async_client.post("/api/knowledge/import", json=body),
                async_client.post("/api/knowledge/import", json=body),
            )
        assert sorted(response.status_code for response in responses) == [200, 201]
        statuses = sorted(
            response.json()["items"][0]["status"] for response in responses
        )
        assert statuses == ["created", "skipped"]
        session = get_session_factory()()
        try:
            assert session.scalar(select(func.count()).select_from(KnowledgeItemORM)) == 1
            assert session.scalar(select(func.count()).select_from(ImportOriginORM)) == 1
        finally:
            session.close()

    async def test_different_identities_concurrent_requests_both_succeed(
        self, client: TestClient
    ):
        """R1.2-ASYNC-07：不同身份并发不被全局单锁串行化且都成功。"""
        def body(instance: str, document: str, title: str) -> dict:
            return {
                "content": (
                    f"---\ntitle: {title}\n"
                    f"source_instance_id: {instance}\n"
                    f"source_document_id: {document}\n---\n正文"
                ),
                "filename": f"{title}.md",
            }

        transport = httpx.ASGITransport(app=client.app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as async_client:
            responses = await asyncio.gather(
                async_client.post(
                    "/api/knowledge/import",
                    json=body(ASYNC_INSTANCE, ASYNC_DOC, "甲"),
                ),
                async_client.post(
                    "/api/knowledge/import",
                    json=body(ASYNC_INSTANCE2, ASYNC_DOC2, "乙"),
                ),
            )
        assert all(response.status_code == 201 for response in responses)
        session = get_session_factory()()
        try:
            assert session.scalar(select(func.count()).select_from(KnowledgeItemORM)) == 2
            assert session.scalar(select(func.count()).select_from(ImportOriginORM)) == 2
        finally:
            session.close()

    async def test_event_loop_stays_responsive_while_import_waits_on_lock(
        self, client: TestClient
    ):
        """R1.2-ASYNC-08：同步锁/DB 等待在线程池，event loop 继续调度。"""
        created = client.post(
            "/api/knowledge", json={"title": "目标", "content": "正文"}
        ).json()
        coordinator = client.app.state.import_coordinator
        old_wait = coordinator._wait_seconds
        coordinator._wait_seconds = 0.5
        entered = threading.Event()
        release = threading.Event()

        def holder():
            with coordinator.keyed(f"target-item:{created['id']}"):
                entered.set()
                release.wait(10)

        thread = threading.Thread(target=holder)
        thread.start()
        assert entered.wait(5)
        ticks = 0
        transport = httpx.ASGITransport(app=client.app)
        try:
            async with httpx.AsyncClient(
                transport=transport, base_url="http://testserver"
            ) as async_client:
                task = asyncio.create_task(
                    async_client.post(
                        "/api/knowledge/import",
                        json={
                            "content": "---\ntitle: 更新\n---\n正文",
                            "filename": "wait.md",
                            "target_item_id": created["id"],
                        },
                    )
                )
                while not task.done():
                    await asyncio.sleep(0.02)
                    ticks += 1
                response = await task
            assert response.status_code == 409
            assert response.json()["detail"] == IMPORT_LOCK_TIMEOUT
            assert ticks >= 5
        finally:
            release.set()
            thread.join(10)
            coordinator._wait_seconds = old_wait
