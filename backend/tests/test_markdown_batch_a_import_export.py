"""Batch A Markdown 导入/导出验收（SQLite 真实 DB + 真实文件系统）。

覆盖 R1.2-ID-01/02/03/05/06/08、R1.2-BAT-01/02、R1.3-HASH-01/02/03/04 与
IMP 主链（创建/更新/幂等/匿名/legacy/附件/审核/链接恢复/索引同步）。
"""

from __future__ import annotations

import json
import sqlite3
import uuid
import zipfile
from io import BytesIO
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import func, select, text

from app.db.session import get_session_factory
from app.models import KnowledgeItemORM
from app.services.markdown import ATTACHMENT_IMPORT_UNSUPPORTED, MarkdownImportDocument
from app.services.markdown_item_repository import MarkdownItemRepository
from knowledge_core.domain.entities import KnowledgeStatus
from knowledge_core.markdown.service import EXPORTER_RESERVED_KEY

INSTANCE_X = "550e8400-e29b-41d4-a716-446655440000"
DOC_X = "660e8400-e29b-41d4-a716-446655440001"
INSTANCE_Y = "770e8400-e29b-41d4-a716-446655440002"
DOC_X2 = "660e8400-e29b-41d4-a716-446655440003"


def _service(client: TestClient):
    return client.app.state.markdown_service


def _import(client: TestClient, text_value: str, filename: str = "doc.md", **kwargs):
    return _service(client).import_documents(
        [MarkdownImportDocument(content=text_value, filename=filename)], **kwargs
    )


def _counts() -> tuple[int, int, int]:
    session = get_session_factory()()
    try:
        items = session.scalar(select(func.count()).select_from(KnowledgeItemORM))
        origins = session.execute(text("select count(*) from import_origin")).scalar_one()
        links = session.execute(text("select count(*) from knowledge_link")).scalar_one()
        return int(items), int(origins), int(links)
    finally:
        session.close()


def _record(item_id: UUID):
    session = get_session_factory()()
    try:
        return MarkdownItemRepository(session).get(str(item_id))
    finally:
        session.close()


def _meta(item_id: UUID) -> dict:
    record = _record(item_id)
    assert record is not None
    return record.extra_metadata


def _fm(**fields: str) -> str:
    lines = ["---"]
    for key, value in fields.items():
        lines.append(f"{key}: {value}")
    lines.extend(["---", "正文"])
    return "\n".join(lines)


def _identity_doc(instance: str, document: str, body: str = "正文", **extra: str) -> str:
    lines = [
        "---",
        "title: 导入标题",
        f"source_instance_id: {instance}",
        f"source_document_id: {document}",
    ]
    for key, value in extra.items():
        lines.append(f"{key}: {value}")
    lines.extend(["---", body])
    return "\n".join(lines)


class TestImportBasics:
    def test_import_creates_draft_with_filename_title_and_tags(self, client: TestClient):
        outcome = _import(
            client,
            "---\ntags: [概念, 图谱]\nstatus: active\n---\n正文",  # type: ignore[arg-type]
            "入门.md",
        )
        assert outcome.report.created == 1
        item = outcome.report.items[0]
        assert item.status.value == "created"
        assert item.status_changes == ["active->draft"]
        record = _record(item.item_id)
        assert record is not None
        assert record.title == "入门"
        assert record.status == "draft"
        assert record.content == "正文"

    def test_import_restores_links_and_reports_unresolved(self, client: TestClient):
        target = client.post(
            "/api/knowledge", json={"title": "目标", "content": "目标正文"}
        ).json()
        outcome = _import(
            client,
            "---\ntitle: 来源\n---\n参见 [[目标]] 与 [[不存在]]",
            "links.md",
        )
        item = outcome.report.items[0]
        assert item.status.value == "created"
        assert any("unresolved_link:不存在" in w for w in item.unresolved_links)
        links = client.get(f"/api/knowledge/{item.item_id}/links").json()
        by_title = {link["target_title"]: link for link in links}
        assert by_title["目标"]["target_id"] == target["id"]
        assert by_title["不存在"]["target_id"] is None

    def test_reimport_same_identity_and_payload_is_skipped(self, client: TestClient):
        text_value = _identity_doc(INSTANCE_X, DOC_X)
        first = _import(client, text_value)
        assert first.report.created == 1
        second = _import(client, text_value)
        assert second.report.skipped == 1
        assert second.report.items[0].item_id == first.report.items[0].item_id
        assert _counts()[0] == 1

    def test_anonymous_same_payload_is_skipped_and_changed_is_duplicate(
        self, client: TestClient
    ):
        first = _import(client, "---\ntitle: 匿名\n---\n相同正文", "anon.md")
        assert first.report.created == 1
        same = _import(client, "---\ntitle: 匿名\n---\n相同正文", "anon.md")
        assert same.report.skipped == 1
        changed = _import(
            client,
            "---\ntitle: 匿名\ntags: [新标签]\n---\n相同正文",
            "anon.md",
        )
        assert changed.report.duplicates == 1
        assert len(changed.report.items[0].duplicates) == 1

    def test_explicit_target_updates_existing_item(self, client: TestClient):
        created = client.post(
            "/api/knowledge", json={"title": "旧标题", "content": "旧正文"}
        ).json()
        outcome = _service(client).import_documents(
            [
                MarkdownImportDocument(
                    content="---\ntitle: 新标题\n---\n新正文",
                    filename="update.md",
                    target_item_id=UUID(created["id"]),
                )
            ]
        )
        assert outcome.report.updated == 1
        item = client.get(f"/api/knowledge/{created['id']}").json()
        assert item["title"] == "新标题"
        assert item["content"] == "新正文"

    def test_batch_isolates_per_document_result(self, client: TestClient):
        outcome = _service(client).import_documents(
            [
                MarkdownImportDocument(
                    content="---\ntitle: 好\n---\n好正文", filename="good.md"
                ),
                MarkdownImportDocument(
                    content='---\ntitle: "未闭合\nbad: [\n---\n坏正文',
                    filename="bad.md",
                ),
            ]
        )
        assert outcome.report.total == 2
        statuses = {item.filename: item.status.value for item in outcome.report.items}
        assert statuses == {"good.md": "created", "bad.md": "skipped"}
        assert outcome.report.items[1].conflicts

    def test_empty_import_rejected(self, client: TestClient):
        from app.services.markdown import MarkdownServiceError

        try:
            _service(client).import_documents([])
        except MarkdownServiceError as exc:
            assert exc.code == "IMPORT_EMPTY"
        else:  # pragma: no cover
            raise AssertionError("empty import must fail")


class TestLegacyIdentity:
    def test_half_identity_is_legacy_and_never_persisted(self, client: TestClient):
        outcome = _import(
            client,
            f"---\ntitle: 半身份\nsource_instance_id: {INSTANCE_X}\n---\n正文",
        )
        item = outcome.report.items[0]
        assert item.status.value == "created"
        assert outcome.report.legacy == 1
        assert "legacy_source_identity" in item.warnings
        meta = _meta(item.item_id)
        assert "source_instance_id" not in meta
        assert "source_document_id" not in meta
        session = get_session_factory()()
        try:
            row = session.get(KnowledgeItemORM, str(item.item_id))
            assert row is not None
            assert row.source_instance_id is None
            assert session.execute(text("select count(*) from import_origin")).scalar_one() == 0
        finally:
            session.close()

    def test_non_string_identity_is_legacy_and_stripped(self, client: TestClient):
        outcome = _import(
            client,
            "---\ntitle: 非法\nsource_instance_id: 123\nsource_document_id: [a]\n---\n正文",
            "bad-identity.md",
        )
        item = outcome.report.items[0]
        assert item.status.value == "created"
        assert outcome.report.legacy == 1
        meta = _meta(item.item_id)
        assert "source_instance_id" not in meta
        assert "source_document_id" not in meta

    def test_legacy_no_identity_uses_content_dedup_and_draft(self, client: TestClient):
        first = _import(client, "---\ntitle: L\n---\n同文", "l.md")
        second = _import(client, "---\ntitle: L\n---\n同文", "l.md")
        assert first.report.created == 1
        assert second.report.skipped == 1
        assert _record(first.report.items[0].item_id).status == "draft"

    def test_source_identity_conflict_with_target(self, client: TestClient):
        x = _import(client, _identity_doc(INSTANCE_X, DOC_X))
        x_id = x.report.items[0].item_id
        outcome = _service(client).import_documents(
            [
                MarkdownImportDocument(
                    content=_identity_doc(INSTANCE_X, DOC_X2, "冲突正文"),
                    filename="conflict.md",
                    target_item_id=x_id,
                )
            ]
        )
        assert outcome.report.errors == 1
        assert outcome.report.items[0].errors == ["SOURCE_IDENTITY_CONFLICT"]

    def test_multiple_origins_for_same_identity_are_ambiguous(self, client: TestClient):
        first = _import(client, _identity_doc(INSTANCE_X, DOC_X))
        # 人为制造第二条同身份记录（模拟历史脏数据/并发写入遗留）。
        session = get_session_factory()()
        try:
            from app.models import ImportOriginORM

            other = KnowledgeItemORM(
                id=str(uuid.uuid4()),
                title="另一个",
                content="另一个",
                status=KnowledgeStatus.DRAFT.value,
                space_id=None,
                extra_metadata="{}",
            )
            session.add(other)
            session.flush()
            session.add(
                ImportOriginORM(
                    id=str(uuid.uuid4()),
                    item_id=other.id,
                    source_payload_hash="a" * 64,
                    source_content_hash="b" * 64,
                    source_instance_id=INSTANCE_X,
                    source_document_id=DOC_X,
                    source_canonicalization_version=1,
                )
            )
            session.commit()
        finally:
            session.close()
        from app.services.markdown import MarkdownServiceError

        try:
            _import(client, _identity_doc(INSTANCE_X, DOC_X))
        except MarkdownServiceError as exc:
            assert exc.code == "SOURCE_IDENTITY_AMBIGUOUS"
        else:  # pragma: no cover
            raise AssertionError("ambiguous identity must fail closed")
        assert _record(first.report.items[0].item_id).source_payload_hash is not None


class TestD22Conflicts:
    def test_duplicate_reserved_key_rejected_before_any_write(self, client: TestClient):
        before = _counts()
        text_value = (
            "---\n"
            "title: 冲突\n"
            f'{EXPORTER_RESERVED_KEY}: "x"\n'
            f'"{EXPORTER_RESERVED_KEY}": "y"\n'
            "---\n正文"
        )
        from app.services.markdown import MarkdownServiceError

        try:
            _import(client, text_value)
        except MarkdownServiceError as exc:
            assert exc.code == "EXPORTER_METADATA_RESERVED_CONFLICT"
        else:  # pragma: no cover
            raise AssertionError("duplicate reserved key must be rejected")
        assert _counts() == before

    def test_manifest_exporter_mismatch_rejected_zero_writes(self, client: TestClient):
        before = _counts()
        document = MarkdownImportDocument(
            content=_identity_doc(INSTANCE_X, DOC_X).replace(
                "---\n正文", f'{EXPORTER_RESERVED_KEY}: "frontmatter"\n---\n正文'
            ),
            filename="doc.md",
        )
        from app.services.markdown import MarkdownServiceError

        try:
            _service(client).import_documents(
                [document],
                manifest={
                    "documents": [
                        {"filename": "doc.md", "exporter_instance_id": "manifest-other"}
                    ]
                },
            )
        except MarkdownServiceError as exc:
            assert exc.code == "EXPORTER_METADATA_RESERVED_CONFLICT"
        else:  # pragma: no cover
            raise AssertionError("manifest mismatch must fail")
        assert _counts() == before

    def test_db_metadata_reserved_key_rejected_zero_writes(self, client: TestClient):
        session = get_session_factory()()
        try:
            target = KnowledgeItemORM(
                id=str(uuid.uuid4()),
                title="用户条目",
                content="用户正文",
                status=KnowledgeStatus.DRAFT.value,
                space_id=None,
                extra_metadata=json.dumps({EXPORTER_RESERVED_KEY: "user"}),
            )
            session.add(target)
            session.commit()
            target_id = target.id
        finally:
            session.close()
        before = _counts()
        from app.services.markdown import MarkdownServiceError

        try:
            _service(client).import_documents(
                [
                    MarkdownImportDocument(
                        content="---\ntitle: 新\n---\n新正文",
                        filename="new.md",
                        target_item_id=UUID(target_id),
                    )
                ]
            )
        except MarkdownServiceError as exc:
            assert exc.code == "EXPORTER_METADATA_RESERVED_CONFLICT"
        else:  # pragma: no cover
            raise AssertionError("user metadata conflict must reject")
        assert _counts() == before
        session = get_session_factory()()
        try:
            row = session.get(KnowledgeItemORM, target_id)
            assert row is not None
            assert json.loads(row.extra_metadata) == {EXPORTER_RESERVED_KEY: "user"}
            assert row.title == "用户条目"
        finally:
            session.close()

    def test_nested_reserved_key_in_user_metadata_rejected_zero_writes(
        self, client: TestClient
    ):
        session = get_session_factory()()
        try:
            target = KnowledgeItemORM(
                id=str(uuid.uuid4()),
                title="用户条目",
                content="用户正文",
                status=KnowledgeStatus.DRAFT.value,
                space_id=None,
                extra_metadata=json.dumps({"meta": {"深层": {EXPORTER_RESERVED_KEY: "x"}}}),
            )
            session.add(target)
            session.commit()
            target_id = target.id
        finally:
            session.close()
        before = _counts()
        from app.services.markdown import MarkdownServiceError

        try:
            _service(client).import_documents(
                [
                    MarkdownImportDocument(
                        content="---\ntitle: 新\n---\n新正文",
                        filename="new.md",
                        target_item_id=UUID(target_id),
                    )
                ]
            )
        except MarkdownServiceError as exc:
            assert exc.code == "EXPORTER_METADATA_RESERVED_CONFLICT"
        else:  # pragma: no cover
            raise AssertionError("nested reserved key must reject")
        assert _counts() == before

    def test_export_rejects_user_metadata_reserved_key(self, client: TestClient):
        session = get_session_factory()()
        try:
            target = KnowledgeItemORM(
                id=str(uuid.uuid4()),
                title="用户条目",
                content="用户正文",
                status=KnowledgeStatus.DRAFT.value,
                space_id=None,
                extra_metadata=json.dumps({EXPORTER_RESERVED_KEY: "user"}),
            )
            session.add(target)
            session.commit()
            target_id = target.id
        finally:
            session.close()
        response = client.get(f"/api/knowledge/{target_id}/markdown")
        assert response.status_code == 409
        assert response.json()["detail"] == "EXPORTER_METADATA_RESERVED_CONFLICT"


class TestExporterHashDecoupling:
    def test_exporter_changes_text_but_not_hashes(self, client: TestClient):
        identity = client.app.state.source_identity
        created = client.post(
            "/api/knowledge", json={"title": "稳定", "content": "内容"}
        ).json()
        before = client.get(f"/api/knowledge/{created['id']}/markdown")
        assert before.status_code == 200
        first_text = before.text
        first_hash = before.headers["X-ExplainLab-Document-Payload-Hash"]
        first_source = before.headers["X-ExplainLab-Source-Instance-Id"]
        first_exporter = before.headers["X-ExplainLab-Exporter-Instance-Id"]

        identity.rotate()
        after = client.get(f"/api/knowledge/{created['id']}/markdown")
        assert after.status_code == 200
        assert after.headers["X-ExplainLab-Exporter-Instance-Id"] != first_exporter
        assert after.headers["X-ExplainLab-Exporter-Instance-Id"] == identity._store.read()
        assert after.headers["X-ExplainLab-Document-Payload-Hash"] == first_hash
        assert after.headers["X-ExplainLab-Source-Instance-Id"] == first_source
        assert first_text != after.text
        assert first_exporter in first_text
        assert identity._store.read() in after.text

    def test_import_strips_exporter_and_hash_matches_without_key(self, client: TestClient):
        service = _service(client)
        plain = service._prepare(
            MarkdownImportDocument(
                content="---\ntitle: H\n---\n同文", filename="plain.md"
            )
        )
        injected = service._prepare(
            MarkdownImportDocument(
                content=(
                    "---\n"
                    "title: H\n"
                    f'{EXPORTER_RESERVED_KEY}: "{INSTANCE_Y}"\n'
                    "---\n同文"
                ),
                filename="injected.md",
            )
        )
        assert injected.content_hash == plain.content_hash
        assert injected.payload_hash == plain.payload_hash
        assert injected.document.extra_metadata == plain.document.extra_metadata
        assert EXPORTER_RESERVED_KEY not in injected.document.extra_metadata

    def test_import_persists_no_exporter_value_or_column(self, client: TestClient, settings):
        outcome = _import(
            client,
            "---\n"
            "title: E\n"
            f'{EXPORTER_RESERVED_KEY}: "{INSTANCE_Y}"\n'
            "---\n正文",
            "e.md",
        )
        item = outcome.report.items[0]
        assert EXPORTER_RESERVED_KEY not in _meta(item.item_id)
        db_path = settings.database_url
        path = db_path.removeprefix("sqlite:///")
        connection = sqlite3.connect(path)
        try:
            columns = {
                row[1] for row in connection.execute("PRAGMA table_info(knowledge_item)")
            }
            origin_columns = {
                row[1] for row in connection.execute("PRAGMA table_info(import_origin)")
            }
        finally:
            connection.close()
        assert EXPORTER_RESERVED_KEY not in columns
        assert EXPORTER_RESERVED_KEY not in origin_columns
        assert not any("exporter" in column for column in columns | origin_columns)


class TestExportImportRoundTrip:
    def test_single_export_contains_identity_and_exporter(self, client: TestClient):
        outcome = _import(client, _identity_doc(INSTANCE_X, DOC_X))
        item_id = outcome.report.items[0].item_id
        response = client.get(f"/api/knowledge/{item_id}/markdown")
        assert response.status_code == 200
        assert f"source_instance_id: {INSTANCE_X}" in response.text
        assert f"source_document_id: {DOC_X}" in response.text
        current = client.app.state.source_instance_store.read()
        assert f'{EXPORTER_RESERVED_KEY}: "{current}"' in response.text
        assert response.headers["X-ExplainLab-Source-Instance-Id"] == INSTANCE_X
        assert response.headers["X-ExplainLab-Source-Document-Id"] == DOC_X
        assert response.headers["X-ExplainLab-Exporter-Instance-Id"] == current

    def test_export_then_reimport_same_instance_updates_same_identity(
        self, client: TestClient
    ):
        outcome = _import(client, _identity_doc(INSTANCE_X, DOC_X))
        item_id = outcome.report.items[0].item_id
        exported = client.get(f"/api/knowledge/{item_id}/markdown")
        second = _import(client, exported.text, "roundtrip.md")
        # 导出会补全 id/status/时间等字段，payload 版本变化走既有更新分类；
        # 关键约束：不重复建条目、不分裂来源身份。
        assert second.report.created == 0
        assert second.report.duplicates == 0
        assert second.report.items[0].status.value in {"updated", "skipped"}
        assert second.report.items[0].item_id == item_id
        assert _counts()[0] == 1

    def test_zip_export_manifest_and_documents(self, client: TestClient):
        first = _import(client, _identity_doc(INSTANCE_X, DOC_X, "一"))
        second = _import(client, _identity_doc(INSTANCE_X, DOC_X2, "二"))
        ids = [str(first.report.items[0].item_id), str(second.report.items[0].item_id)]
        response = client.post("/api/knowledge/export", json={"ids": ids})
        assert response.status_code == 200
        with zipfile.ZipFile(BytesIO(response.content)) as archive:
            names = archive.namelist()
            assert "manifest.json" in names
            manifest = json.loads(archive.read("manifest.json"))
            markdown = [name for name in names if name.endswith(".md")]
            assert len(markdown) == 2
        assert manifest["exporter_instance_id"] == client.app.state.markdown_service.exporter_instance_id
        assert len(manifest["documents"]) == 2
        assert all(
            document["source_instance_id"] == INSTANCE_X
            for document in manifest["documents"]
        )

    def test_zip_reimport_is_idempotent(self, client: TestClient):
        first = _import(client, _identity_doc(INSTANCE_X, DOC_X, "一"))
        second = _import(client, _identity_doc(INSTANCE_X, DOC_X2, "二"))
        ids = [str(first.report.items[0].item_id), str(second.report.items[0].item_id)]
        exported = client.post("/api/knowledge/export", json={"ids": ids})
        import base64

        body = {"archive_base64": base64.b64encode(exported.content).decode("ascii")}
        reimport = client.post("/api/knowledge/import/batch", json=body)
        assert reimport.status_code == 200
        report = reimport.json()
        assert report["created"] == 0
        assert report["duplicates"] == 0
        assert report["updated"] + report["skipped"] == 2
        assert _counts()[0] == 2

    def test_export_empty_and_missing(self, client: TestClient):
        assert client.post("/api/knowledge/export", json={"ids": []}).status_code == 400
        assert (
            client.get(
                "/api/knowledge/00000000-0000-0000-0000-000000000099/markdown"
            ).status_code
            == 404
        )


class TestAttachmentBoundary:
    def test_single_import_with_attachments_rejected_zero_writes(self, client: TestClient):
        before = _counts()
        response = client.post(
            "/api/knowledge/import",
            json={
                "content": "正文",
                "filename": "a.md",
                "attachments": [{"filename": "a.png", "content_hash": "aa"}],
            },
        )
        assert response.status_code == 400
        assert response.json()["detail"] == ATTACHMENT_IMPORT_UNSUPPORTED
        assert _counts() == before

    def test_batch_attachments_marked_unsupported_and_continue(self, client: TestClient):
        response = client.post(
            "/api/knowledge/import/batch",
            json={
                "documents": [
                    {
                        "content": "---\ntitle: 附件\n---\n正文",
                        "filename": "with-att.md",
                        "attachments": [{"filename": "a.png"}],
                    },
                    {"content": "---\ntitle: 正常\n---\n正文", "filename": "ok.md"},
                ]
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["unsupported"] == 1
        assert body["created"] == 1
        statuses = {item["filename"]: item["status"] for item in body["items"]}
        assert statuses["with-att.md"] == "unsupported"
        assert statuses["ok.md"] == "created"
        assert _counts()[0] == 1

    def test_attachment_export_rejected(self, client: TestClient):
        response = client.post(
            "/api/knowledge/export", json={"ids": [], "include_attachments": True}
        )
        assert response.status_code == 400
        assert response.json()["detail"] == "ATTACHMENT_EXPORT_UNSUPPORTED"


class TestActiveReviewFlow:
    def _prepare_active_import(self, client: TestClient):
        first = _import(client, _identity_doc(INSTANCE_X, DOC_X, "初版", tags="[旧]"))
        item_id = first.report.items[0].item_id
        patched = client.patch(f"/api/knowledge/{item_id}", json={"status": "active"})
        assert patched.status_code == 200
        return item_id

    def test_active_content_change_creates_review_then_approve_applies_hook(
        self, client: TestClient
    ):
        item_id = self._prepare_active_import(client)
        changed = _identity_doc(
            INSTANCE_X,
            DOC_X,
            "新版 [[目标]]",
            tags="[新]",
            custom="值",
        )
        client.post("/api/knowledge", json={"title": "目标", "content": "t"})
        outcome = _import(client, changed)
        result = outcome.report.items[0]
        assert result.status.value == "pending_review"
        assert result.review_id is not None
        before = client.get(f"/api/knowledge/{item_id}").json()
        assert before["content"] == "初版"

        reviews = client.get("/api/reviews?status=pending").json()
        review = next(r for r in reviews if r["id"] == str(result.review_id))
        assert review["payload"]["__a1_import"]["source_payload_hash"] == result.source_payload_hash
        approved = client.post(f"/api/reviews/{result.review_id}/approve", json={})
        assert approved.status_code == 200, approved.text
        after = client.get(f"/api/knowledge/{item_id}").json()
        assert after["content"] == "新版 [[目标]]"
        assert after["status"] == "draft"
        record = _record(item_id)
        assert record is not None
        assert record.extra_metadata.get("custom") == "值"
        tags = client.get(f"/api/knowledge/{item_id}/links").json()
        assert any(link["target_title"] == "目标" for link in tags)

    def test_pending_same_reused_and_different_rejected(self, client: TestClient):
        item_id = self._prepare_active_import(client)
        changed = _identity_doc(INSTANCE_X, DOC_X, "待审版本")
        first = _import(client, changed)
        assert first.report.pending_review == 1
        same = _import(client, changed)
        assert same.report.reused_pending == 1
        assert same.report.items[0].review_id == first.report.items[0].review_id
        other = _import(client, _identity_doc(INSTANCE_X, DOC_X, "另一个版本"))
        assert other.report.errors == 1
        assert other.report.items[0].errors == ["SOURCE_HAS_PENDING_IMPORT"]
        assert _record(item_id).content == "初版"

    def test_reject_leaves_item_and_origin_unchanged(self, client: TestClient):
        item_id = self._prepare_active_import(client)
        changed = _identity_doc(INSTANCE_X, DOC_X, "拒绝版本", tags="[拒绝]")
        outcome = _import(client, changed)
        review_id = outcome.report.items[0].review_id
        session = get_session_factory()()
        try:
            before_origins = session.execute(
                text("select count(*) from import_origin")
            ).scalar_one()
        finally:
            session.close()
        rejected = client.post(f"/api/reviews/{review_id}/reject", json={"note": "不要"})
        assert rejected.status_code == 200
        after = client.get(f"/api/knowledge/{item_id}").json()
        assert after["content"] == "初版"
        session = get_session_factory()()
        try:
            after_origins = session.execute(
                text("select count(*) from import_origin")
            ).scalar_one()
        finally:
            session.close()
        assert after_origins == before_origins

    def test_approve_hook_failure_rolls_back_review_and_item(
        self, client: TestClient, monkeypatch
    ):
        item_id = self._prepare_active_import(client)
        changed = _identity_doc(INSTANCE_X, DOC_X, "回滚版本")
        outcome = _import(client, changed)
        review_id = outcome.report.items[0].review_id

        from app.services import import_review_hook
        from app.services.markdown import MarkdownServiceError

        def boom(self, review, envelope):
            raise MarkdownServiceError("IMPORT_FAILED", "injected", status_code=409)

        monkeypatch.setattr(import_review_hook.ImportReviewHook, "apply_approved", boom)
        response = client.post(f"/api/reviews/{review_id}/approve", json={})
        assert response.status_code == 409
        after = client.get(f"/api/knowledge/{item_id}").json()
        assert after["content"] == "初版"
        pending = client.get("/api/reviews?status=pending").json()
        assert any(r["id"] == str(review_id) for r in pending)