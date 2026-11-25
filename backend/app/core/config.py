"""应用配置：全部来自环境变量 / backend/.env，密钥绝不进入前端。

路径一致性（M0-07）：.env 与默认 SQLite 数据文件均锚定到 backend 目录，
无论从仓库根目录还是 backend 目录启动，都加载同一份 .env、指向同一个数据库，
不会因启动目录不同而创建多个数据库。空字符串环境变量视为未配置。
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# config.py 位于 backend/app/core/config.py，parents[2] 即 backend 目录。
BACKEND_DIR = Path(__file__).resolve().parents[2]
# 默认 SQLite 数据文件用绝对路径，避免相对 cwd 解析导致多库。
DEFAULT_DATABASE_URL = f"sqlite:///{(BACKEND_DIR / 'data' / 'explainlab.db').as_posix()}"

# 可选模型/向量字段：空字符串须归一为 None，避免空密钥被误判为已配置。
_OPTIONAL_MODEL_FIELDS = (
    "model_provider",
    "model_base_url",
    "model_api_key",
    "model_name",
    "embed_base_url",
    "embed_api_key",
    "embed_model",
)

# V2 A1-04 Batch B D-08：白色名单固定八类；SVG 永不进入白名单。
DEFAULT_ATTACHMENT_MIME_ALLOWLIST = (
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/webp",
    "application/pdf",
    "text/plain",
    "text/markdown",
    "text/csv",
)

_MIB = 1024 * 1024


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "ExplainLab"
    version: str = "0.1.0"
    environment: str = "development"

    database_url: str = DEFAULT_DATABASE_URL
    # V2 A1-04 Batch B：本机数据根（进程锁 / source-instance-id / Journal）。
    # 默认与 SQLite 数据文件同目录；测试注入临时目录以隔离。
    data_dir: Path = BACKEND_DIR / "data"

    # V2 A1-04 Batch B 冻结配置（architecture §5）。根路径留空时按 data_dir 派生；
    # 显式相对路径相对 data_dir 解析，禁止 ``..`` 逃逸，且必须位于 data_dir 内。
    attachment_storage_root: Path | None = None
    attachment_staging_root: Path | None = None
    attachment_quarantine_dir: Path | None = None
    attachment_max_bytes: int = 10 * _MIB
    attachment_mime_allowlist: list[str] = list(DEFAULT_ATTACHMENT_MIME_ALLOWLIST)
    attachment_import_max_count: int = 100
    attachment_import_max_total_bytes: int = 100 * _MIB
    staging_grace_seconds: int = 86400

    storage_lock_ttl_seconds: float = 60.0
    storage_lock_heartbeat_seconds: float = 15.0
    storage_lock_wait_seconds: float = 10.0

    gc_max_attempts: int = 8
    gc_retry_base_seconds: int = 60
    gc_retry_max_seconds: int = 21600
    gc_quarantine_seconds: int = 86400
    orphan_scan_interval_seconds: int = 300

    # 同步导入身份锁有界等待（秒）；超时返回 IMPORT_LOCK_TIMEOUT。
    import_lock_wait_seconds: float = 10.0
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    # 模型适配层：M1 接入 OpenAI 兼容供应商；密钥仅后端持有，绝不进入前端。
    # 敏感字段用 SecretStr：普通序列化（model_dump_json / repr）只输出掩码，
    # 取值须显式 .get_secret_value()，避免密钥意外进入日志或响应。
    model_provider: str | None = None
    model_base_url: str | None = None
    model_api_key: SecretStr | None = None
    model_name: str | None = None

    # M3 向量来源（独立于聊天配置）：支持 /embeddings 的 OpenAI 兼容端点。
    # 未配置时向量通道如实关闭（仅全文检索），不造假。
    embed_base_url: str | None = None
    embed_api_key: SecretStr | None = None
    embed_model: str | None = None

    @field_validator(*_OPTIONAL_MODEL_FIELDS, mode="before")
    @classmethod
    def _empty_string_to_none(cls, value: object) -> object:
        """空字符串 / 纯空白视为未配置（None）。"""
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("database_url", mode="before")
    @classmethod
    def _normalize_database_url(cls, value: object) -> str:
        """空值回退默认；SQLite 相对文件路径锚定到 backend 目录。

        绝对路径（POSIX 以 / 开头或 Windows 含盘符）、:memory: 与非 SQLite URL 原样保留。
        """
        if not isinstance(value, str) or not value.strip():
            return DEFAULT_DATABASE_URL
        url = value.strip()
        prefix = "sqlite:///"
        if url.startswith(prefix) and ":memory:" not in url:
            path_part = url[len(prefix) :]
            if not path_part.startswith(("/", "file:")) and not Path(path_part).is_absolute():
                anchored = BACKEND_DIR / path_part
                return f"{prefix}{anchored.as_posix()}"
        return url

    @field_validator(
        "attachment_storage_root",
        "attachment_staging_root",
        "attachment_quarantine_dir",
        mode="before",
    )
    @classmethod
    def _empty_path_to_none(cls, value: object) -> object:
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("data_dir", mode="before")
    @classmethod
    def _normalize_data_dir(cls, value: object) -> Path:
        """data_dir 始终为绝对路径；相对值锚定 backend（与 M0-07 一致）。"""
        if value is None or (isinstance(value, str) and not value.strip()):
            return BACKEND_DIR / "data"
        path = Path(value)
        if not path.is_absolute():
            path = BACKEND_DIR / path
        if ".." in path.parts:
            raise ValueError("data_dir must not contain '..'")
        return path

    @model_validator(mode="after")
    def _resolve_attachment_roots(self) -> Settings:
        """派生并校验附件根：位于 data_dir 内、互不重叠、quarantine 为直接子目录。

        这里只做**路径层**校验（不触盘）；真实目录身份、链接/重解析点与同卷
        约束在启动时由 ``attachment_storage.validate_storage_roots`` fail-fast 校验。
        """
        data_dir = Path(self.data_dir)

        def resolve_root(
            value: Path | None, default: Path, *, base: Path, field: str
        ) -> Path:
            candidate = value if value is not None else default
            candidate = Path(candidate)
            if ".." in candidate.parts:
                raise ValueError(f"{field} must not contain '..'")
            if not candidate.is_absolute():
                candidate = base / candidate
            try:
                candidate.relative_to(data_dir)
            except ValueError as exc:
                raise ValueError(f"{field} must be inside data_dir") from exc
            if candidate == data_dir:
                raise ValueError(f"{field} must not equal data_dir")
            return candidate

        storage = resolve_root(
            self.attachment_storage_root,
            data_dir / "attachments",
            base=data_dir,
            field="attachment_storage_root",
        )
        staging = resolve_root(
            self.attachment_staging_root,
            data_dir / "import-staging",
            base=data_dir,
            field="attachment_staging_root",
        )
        quarantine = resolve_root(
            self.attachment_quarantine_dir,
            storage / "_quarantine",
            base=data_dir,
            field="attachment_quarantine_dir",
        )

        def contains(parent: Path, child: Path) -> bool:
            if parent == child:
                return True
            try:
                child.relative_to(parent)
                return True
            except ValueError:
                return False

        if contains(storage, staging) or contains(staging, storage):
            raise ValueError("attachment_storage_root and attachment_staging_root overlap")
        if quarantine.parent != storage:
            raise ValueError(
                "attachment_quarantine_dir must be a direct child of attachment_storage_root"
            )
        if contains(quarantine, staging) or contains(staging, quarantine):
            raise ValueError("attachment_quarantine_dir overlaps attachment_staging_root")
        if quarantine.name in (".tmp", "staging") or (
            len(quarantine.name) == 2
            and all(ch in "0123456789abcdef" for ch in quarantine.name)
        ):
            raise ValueError("attachment_quarantine_dir name collides with storage namespace")

        self.data_dir = data_dir
        self.attachment_storage_root = storage
        self.attachment_staging_root = staging
        self.attachment_quarantine_dir = quarantine
        return self

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()
