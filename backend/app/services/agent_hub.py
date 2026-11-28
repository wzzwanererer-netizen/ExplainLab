"""AI 助手副库管理中心与本地会话吸尘器（Agent Hub & Session Vacuum）。

核心能力：
1. 自动探测本机已安装的 AI Agent（DSH / Claude / Codex / Antigravity / Cursor / Qoder / Trae / WorkBuddy / Kimi）；
2. 一键为任意 Agent 单开专属副库（`Agent · <名称>`），可选幂等写入全局自动记忆规则；
3. 本地会话吸尘器：增量读取各 Agent 的本地聊天落盘文件（支持 `.jsonl` 与 `.jsonl.zstd`），
   自动脱敏（过滤密钥/Token）、用大模型筛选提炼高价值知识点并写入对应 Agent 副库，记录游标避免重复处理。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import unquote
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import KnowledgeItemORM, KnowledgeSpace
from app.services.knowledge import SQLAlchemyKnowledgeRepository
from app.services.media import list_media, save_media_bytes
from knowledge_core.domain.entities import (
    KnowledgeItem,
    KnowledgeStatus,
    SourceRef,
    SourceType,
)
from knowledge_core.model_adapter import ModelAdapter, ModelMessage, ModelRequest

_RULE_MARKER_START = "<!-- EXPLAINLAB-AUTO-MEMORY:START -->"
_RULE_MARKER_END = "<!-- EXPLAINLAB-AUTO-MEMORY:END -->"

# 入库与送模型前的敏感凭证脱敏规则（严禁把 API Key / Token / 密码写入知识库）
_SECRET_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"), "[REDACTED_API_KEY]"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"), "[REDACTED_TOKEN]"),
    (re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._\-]{16,}\b"), "Bearer [REDACTED]"),
    (
        re.compile(
            r"(?i)(api[_-]?key|secret|password|passwd|access[_-]?token)\s*[:=]\s*['\"]?[^\s'\",;]{8,}['\"]?"
        ),
        r"\1=[REDACTED]",
    ),
]

_VACUUM_SYSTEM_PROMPT = """你是 ExplainLab 个人知识库的「多模态记忆吸尘器」。
请阅读一段用户与 AI Agent 的对话摘录（以及随附的本地图片资产清单），判断其中是否包含**值得长期沉淀的高价值知识**（例如：角色/设计素材、项目架构方案、技术选型结论、关键排错经验、清晰的概念总结、用户明确的长期偏好）。

硬性规则：
1. 如果对话全是寒暄、简单指令、纯工具刷屏或一次性琐事，必须返回 `{"items": []}`，宁缺毋滥！
2. 如果有高价值内容，提炼 1~3 条结构化知识卡片，每条包含 `title`（简洁明确的中文标题）、`content`（条理清晰的 Markdown 要点，支持表格，末尾可附 `#标签`）。
3. **图文并茂**：如果输入提供了「关联图片资产列表」，务必把与该知识主题相关的图片用标准 Markdown `![图片说明](/api/agents/media/...)` 嵌入正文；若在图片下一行紧跟 `**模块标题**` 与 `- 要点列表`（可选 `> 备注`），前端会自动排成精致的「左图右文」卡片！严禁编造不存在的图片路径，只能使用输入清单里给出的 `/api/agents/media/...` URL。
4. 严禁包含任何 API Key、密码、Token、Cookie 或隐私凭证。
5. 只输出严格 JSON，不要输出任何额外文字，格式：
{"items": [{"title": "...", "content": "..."}]}
"""

_IMAGE_EXTS = frozenset({".png", ".jpg", ".jpeg", ".webp", ".gif"})
_DOC_ATTACH_EXTS = frozenset({".pdf", ".docx", ".xlsx", ".pptx", ".csv"})
_VALID_MEDIA_FILENAME = re.compile(r"^[a-f0-9]{16}\.(png|jpg|jpeg|webp|gif)$")


@dataclass(frozen=True)
class KnownAgentSpec:
    id: str
    name: str
    description: str
    detect_dir: Path
    session_dir: Path
    session_globs: tuple[str, ...]
    rule_file: Path | None = None


@dataclass
class AgentStatus:
    id: str
    name: str
    description: str
    space_name: str
    space_id: str | None
    installed: bool
    connected: bool
    item_count: int
    session_dir: str | None
    session_files_count: int
    unprocessed_count: int
    rule_installed: bool
    last_vacuum_at: str | None
    is_custom: bool = False


@dataclass
class SessionFilePreview:
    file_path: str
    label: str
    preview: str
    updated_at: str
    size_kb: float
    processed: bool
    created_count: int = 0


@dataclass
class VacuumCreatedItem:
    id: str
    agent_name: str
    space_id: str
    title: str
    source_file: str


@dataclass
class VacuumReport:
    scanned_sessions: int = 0
    skipped_sessions: int = 0
    created_items: list[VacuumCreatedItem] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _home() -> Path:
    return Path.home()


def _appdata() -> Path:
    if sys.platform == "darwin":
        return _home() / "Library" / "Application Support"
    if sys.platform != "win32":
        raw_xdg = os.environ.get("XDG_CONFIG_HOME")
        return Path(raw_xdg) if raw_xdg else (_home() / ".config")
    raw = os.environ.get("APPDATA")
    return Path(raw) if raw else (_home() / "AppData" / "Roaming")


def _localappdata() -> Path:
    if sys.platform == "darwin":
        return _home() / "Library" / "Application Support"
    if sys.platform != "win32":
        raw_xdg = os.environ.get("XDG_DATA_HOME")
        return Path(raw_xdg) if raw_xdg else (_home() / ".local" / "share")
    raw = os.environ.get("LOCALAPPDATA")
    return Path(raw) if raw else (_home() / "AppData" / "Local")


def _first_existing(*candidates: Path) -> Path:
    for c in candidates:
        if c.exists():
            return c
    return candidates[0]


def _known_specs() -> list[KnownAgentSpec]:
    h = _home()
    ad = _appdata()
    lad = _localappdata()
    return [
        KnownAgentSpec(
            id="dsh",
            name="DSH",
            description="DeepSeek Harness 桌面智能体",
            detect_dir=h / ".dsh",
            session_dir=h / ".dsh" / "sessions",
            session_globs=("**/*.jsonl.zstd", "**/*.jsonl"),
            rule_file=h / ".dsh" / "AGENTS.md",
        ),
        KnownAgentSpec(
            id="antigravity",
            name="Antigravity",
            description="Google Antigravity 编程智能体",
            detect_dir=h / ".gemini" / "antigravity",
            session_dir=h / ".gemini" / "antigravity" / "brain",
            session_globs=("*/.system_generated/logs/transcript.jsonl",),
            rule_file=h / ".gemini" / "GEMINI.md",
        ),
        KnownAgentSpec(
            id="claude",
            name="Claude",
            description="Anthropic Claude Code 终端助手",
            detect_dir=h / ".claude",
            session_dir=h / ".claude" / "projects",
            session_globs=("**/*.jsonl",),
            rule_file=h / ".claude" / "CLAUDE.md",
        ),
        KnownAgentSpec(
            id="codex",
            name="Codex",
            description="OpenAI Codex 编程助手",
            detect_dir=h / ".codex",
            session_dir=h / ".codex" / "sessions",
            session_globs=("**/*.jsonl",),
            rule_file=h / ".codex" / "AGENTS.md",
        ),
        KnownAgentSpec(
            id="cursor",
            name="Cursor",
            description="Cursor AI 代码编辑器",
            detect_dir=h / ".cursor",
            session_dir=h / ".cursor",
            session_globs=("**/*.jsonl",),
            rule_file=h / ".cursor" / "rules" / "explainlab-memory.mdc",
        ),
        KnownAgentSpec(
            id="qoder",
            name="Qoder",
            description="Qoder 智能研发助手",
            detect_dir=h / ".qoder",
            session_dir=h / ".qoder",
            session_globs=("**/*.jsonl",),
            rule_file=h / ".qoder" / "AGENTS.md",
        ),
        KnownAgentSpec(
            id="doubaowork",
            name="豆包工作",
            description="字节豆包工作 AI 办公智能体",
            detect_dir=_first_existing(h / "DoubaoWork", lad / "DoubaoWork"),
            session_dir=_first_existing(h / "DoubaoWork", lad / "DoubaoWork"),
            session_globs=("**/*.jsonl", "**/*.md"),
            rule_file=None,
        ),
        KnownAgentSpec(
            id="qwenwork",
            name="千问办公",
            description="阿里千问办公 AI 智能体",
            detect_dir=_first_existing(h / ".qwenworkcn", ad / "QwenWorkCN"),
            session_dir=_first_existing(h / ".qwenworkcn", ad / "QwenWorkCN"),
            session_globs=("**/*.jsonl", "**/*.md"),
            rule_file=None,
        ),
        KnownAgentSpec(
            id="trae",
            name="Trae CN",
            description="字节 Trae CN AI IDE",
            detect_dir=_first_existing(h / ".trae-cn", ad / "Trae CN"),
            session_dir=_first_existing(h / ".trae-cn", ad / "Trae CN"),
            session_globs=("**/*.jsonl",),
            rule_file=None,
        ),
        KnownAgentSpec(
            id="codebuddy",
            name="CodeBuddy",
            description="腾讯 CodeBuddy AI 编程助手",
            detect_dir=_first_existing(h / ".codebuddycn", h / ".codebuddy", ad / "CodeBuddy CN"),
            session_dir=_first_existing(h / ".codebuddycn", h / ".codebuddy", ad / "CodeBuddy CN"),
            session_globs=("**/*.jsonl",),
            rule_file=None,
        ),
        KnownAgentSpec(
            id="workbuddy",
            name="WorkBuddy",
            description="WorkBuddy 协作智能体",
            detect_dir=h / ".workbuddy",
            session_dir=h / ".workbuddy",
            session_globs=("**/*.jsonl",),
            rule_file=None,
        ),
        KnownAgentSpec(
            id="kimi",
            name="Kimi Code",
            description="月之暗面 Kimi Code 编程助手",
            detect_dir=h / ".kimi-code",
            session_dir=h / ".kimi-code",
            session_globs=("**/*.jsonl",),
            rule_file=None,
        ),
        KnownAgentSpec(
            id="kimiwork",
            name="Kimi 办公",
            description="Kimi 桌面协作智能体",
            detect_dir=_first_existing(h / ".kimi-work", ad / "kimi-desktop"),
            session_dir=_first_existing(h / ".kimi-work", ad / "kimi-desktop"),
            session_globs=("**/*.jsonl", "**/*.md"),
            rule_file=None,
        ),
        KnownAgentSpec(
            id="opencode",
            name="OpenCode",
            description="OpenCode 开源编程智能体",
            detect_dir=_first_existing(h / ".local" / "share" / "opencode", ad / "ai.opencode.desktop"),
            session_dir=_first_existing(h / ".local" / "share" / "opencode", ad / "ai.opencode.desktop"),
            session_globs=("**/*.jsonl", "**/*.md"),
            rule_file=None,
        ),
        KnownAgentSpec(
            id="hermes",
            name="Hermes",
            description="Nous Hermes 桌面智能体",
            detect_dir=_first_existing(ad / "Hermes", lad / "hermes"),
            session_dir=_first_existing(ad / "Hermes", lad / "hermes"),
            session_globs=("**/*.jsonl", "**/*.md"),
            rule_file=None,
        ),
        KnownAgentSpec(
            id="zcode",
            name="ZCode",
            description="ZCode AI 编程助手",
            detect_dir=_first_existing(h / ".zcode", ad / "ZCode"),
            session_dir=_first_existing(h / ".zcode", ad / "ZCode"),
            session_globs=("**/*.jsonl",),
            rule_file=None,
        ),
        KnownAgentSpec(
            id="copilot",
            name="GitHub Copilot",
            description="GitHub Copilot CLI / IDE 助手",
            detect_dir=h / ".copilot",
            session_dir=h / ".copilot",
            session_globs=("**/*.jsonl",),
            rule_file=None,
        ),
        KnownAgentSpec(
            id="windsurf",
            name="Windsurf",
            description="Codeium Windsurf AI IDE",
            detect_dir=_first_existing(h / ".codeium" / "windsurf", ad / "Windsurf"),
            session_dir=_first_existing(h / ".codeium" / "windsurf", ad / "Windsurf"),
            session_globs=("**/*.jsonl",),
            rule_file=None,
        ),
        KnownAgentSpec(
            id="cline",
            name="Cline",
            description="VS Code Cline 自主编程助手",
            detect_dir=ad / "Code" / "User" / "globalStorage" / "saoudrizwan.claude-dev",
            session_dir=ad / "Code" / "User" / "globalStorage" / "saoudrizwan.claude-dev" / "tasks",
            session_globs=("**/*.json", "**/*.md"),
            rule_file=None,
        ),
        KnownAgentSpec(
            id="roocode",
            name="Roo Code",
            description="VS Code Roo Code 编程智能体",
            detect_dir=ad / "Code" / "User" / "globalStorage" / "rooveterinaryinc.roo-cline",
            session_dir=ad / "Code" / "User" / "globalStorage" / "rooveterinaryinc.roo-cline" / "tasks",
            session_globs=("**/*.json", "**/*.md"),
            rule_file=None,
        ),
        KnownAgentSpec(
            id="grokbot",
            name="Grok Bot",
            description="Grok Bot 桌面智能体",
            detect_dir=_first_existing(h / ".grokbot", ad / "Grok Bot"),
            session_dir=_first_existing(h / ".grokbot", ad / "Grok Bot"),
            session_globs=("**/*.jsonl", "**/*.md"),
            rule_file=None,
        ),
        KnownAgentSpec(
            id="mimo",
            name="Xiaomi MiMo",
            description="小米 MiMo 桌面智能体",
            detect_dir=_first_existing(ad / "Xiaomi MiMo", h / "XiaomiMiMoProjects"),
            session_dir=_first_existing(ad / "Xiaomi MiMo", h / "XiaomiMiMoProjects"),
            session_globs=("**/*.jsonl", "**/*.md"),
            rule_file=None,
        ),
    ]


def _registry_path(data_dir: Path) -> Path:
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "agents_registry.json"


def _vacuum_state_path(data_dir: Path) -> Path:
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "vacuum_state.json"


def vacuum_media_dir(data_dir: Path) -> Path:
    root = (data_dir / "vacuum_media").resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def resolve_vacuum_media_path(data_dir: Path, filename: str) -> Path | None:
    """安全解析吸尘媒体文件路径，防止路径穿越。"""
    if not _VALID_MEDIA_FILENAME.match(filename):
        return None
    root = vacuum_media_dir(data_dir)
    target = (root / filename).resolve()
    if target.parent != root or not target.is_file():
        return None
    return target


def _decode_dsh_encoded_dir(name: str) -> Path | None:
    """解码 DSH 编码目录名，如 `--D-Projects-CampusSafetyAgent--` -> `D:\\Projects\\CampusSafetyAgent`。"""
    if not (name.startswith("--") and name.endswith("--")):
        return None
    inner = name.strip("-")
    inner = re.sub(
        r"~([0-9A-Fa-f]{4})",
        lambda m: chr(int(m.group(1), 16)),
        inner,
    )
    if len(inner) >= 3 and inner[0].isalpha() and inner[1] == "-":
        drive = f"{inner[0]}:\\"
        rest = inner[2:]
        # 优先尝试直接按 '-' 拆分路径，若不存在则保留最后段含连字符的常见形式
        direct = Path(drive + rest.replace("-", "\\"))
        if direct.is_dir():
            return direct
        parts = rest.split("-")
        for split_idx in range(len(parts), 0, -1):
            candidate = Path(drive + "\\".join(parts[:split_idx]))
            if candidate.is_dir():
                return candidate
    return None


def _decode_claude_encoded_dir(name: str) -> Path | None:
    """解码 Claude Code 项目目录名，如 `d--ExplainLab` -> `D:\\ExplainLab`。"""
    m = re.match(r"^([A-Za-z])--(.+)$", name)
    if not m:
        return None
    drive = f"{m.group(1).upper()}:\\"
    rest = m.group(2)
    direct = Path(drive + rest.replace("-", "\\"))
    if direct.is_dir():
        return direct
    parts = rest.split("-")
    for split_idx in range(len(parts), 0, -1):
        candidate = Path(drive + "\\".join(parts[:split_idx]))
        if candidate.is_dir():
            return candidate
    return None


def resolve_session_workspace(
    agent_id: str,
    session_file: Path,
    codex_catalog: dict[str, tuple[str, str, str]] | None = None,
) -> Path | None:
    """统一工作区解析器：支持 4 大 Agent 家族还原会话所属项目目录（cwd）。"""
    # 1) Codex catalog（精确映射 thread_id -> cwd）
    if agent_id == "codex" and codex_catalog:
        for tid, (_, _, cwd_str) in codex_catalog.items():
            if tid in session_file.name and cwd_str:
                p = Path(cwd_str).resolve()
                if p.is_dir() and p != _home().resolve() and len(p.parts) >= 2:
                    return p

    # 2) JSONL 头部 cwd / workspaceUris 字段（适用 Codex / Claude / Antigravity / WorkBuddy / Kimi）
    if session_file.suffix.lower() == ".jsonl":
        try:
            with session_file.open("r", encoding="utf-8", errors="ignore") as fh:
                for i, line in enumerate(fh):
                    if i > 25:
                        break
                    if '"cwd"' not in line and '"workspaceUris"' not in line:
                        continue
                    obj = json.loads(line)
                    if not isinstance(obj, dict):
                        continue
                    pl = obj.get("payload") if isinstance(obj.get("payload"), dict) else obj
                    raw_cwd = pl.get("cwd") if isinstance(pl, dict) else None
                    if isinstance(raw_cwd, str) and raw_cwd.strip():
                        p = Path(raw_cwd.strip()).resolve()
                        if p.is_dir() and p != _home().resolve() and len(p.parts) >= 2:
                            return p
        except Exception:
            pass

    # 3) DSH 编码目录名解码（sessions/--D-Projects-xxx--/session-*/session.v4.jsonl.zstd）
    for anc in session_file.parents:
        decoded = _decode_dsh_encoded_dir(anc.name)
        if decoded is not None:
            return decoded
        claude_dec = _decode_claude_encoded_dir(anc.name)
        if claude_dec is not None:
            return claude_dec
        # 4) VS Code / Cursor / Qoder / Trae workspace.json
        ws_json = anc / "workspace.json"
        if ws_json.is_file():
            try:
                meta = json.loads(ws_json.read_text(encoding="utf-8", errors="ignore"))
                folder_uri = meta.get("folder") if isinstance(meta, dict) else None
                if isinstance(folder_uri, str) and folder_uri.startswith("file:///"):
                    raw_p = unquote(folder_uri[8:])
                    p = Path(raw_p).resolve()
                    if p.is_dir():
                        return p
            except Exception:
                pass
        if len(anc.parts) <= 2:
            break
    return None


def ingest_session_images(
    session_file: Path,
    dialogue_text: str,
    data_dir: Path,
    *,
    agent_id: str = "",
    max_images: int = 6,
) -> list[tuple[str, str, Path]]:
    """统一多模态图片采集器：会话目录 + 对话引用 + 项目 cwd 代表图，SHA-256 去重落盘。

    返回 `[(stem, api_url, stored_path), ...]`，支持正文嵌入与附件面板双通道落库。
    """
    candidates: list[Path] = []
    seen_src: set[str] = set()

    def _add_candidate(p: Path) -> None:
        try:
            rp = p.resolve()
            key = str(rp)
            if (
                key not in seen_src
                and rp.is_file()
                and rp.suffix.lower() in _IMAGE_EXTS
                and 2048 <= rp.stat().st_size <= 12 * 1024 * 1024
            ):
                seen_src.add(key)
                candidates.append(rp)
        except OSError:
            return

    # 1) Antigravity 会话根目录下生成的图片（brain/<conv-id>/*.png|jpg）
    if session_file.name.lower() == "transcript.jsonl" and session_file.parent.name == "logs":
        conv_root = session_file.parent.parent.parent
        if conv_root.is_dir():
            for child in sorted(conv_root.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
                if child.is_file():
                    _add_candidate(child)

    # 2) 会话同级目录图片
    if session_file.parent.is_dir():
        for child in sorted(
            session_file.parent.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True
        ):
            if child.is_file():
                _add_candidate(child)

    # 3) 对话文本里提到的本机绝对图片路径
    for match in re.finditer(
        r"([A-Za-z]:[/\\][^\s\"'<>|]+?\.(?:png|jpg|jpeg|webp|gif))",
        dialogue_text,
        re.IGNORECASE,
    ):
        _add_candidate(Path(match.group(1)))

    # 4) 会话所属项目目录（cwd）内的代表性图片（每子目录最多 2 张，避免序列帧刷屏）
    if len(candidates) < max_images:
        codex_cat = _load_codex_catalog() if agent_id == "codex" else None
        cwd_dir = resolve_session_workspace(agent_id, session_file, codex_cat)
        if cwd_dir is not None:
            root_depth = len(cwd_dir.parts)
            per_dir_count: dict[Path, int] = {}
            found_cwd_imgs: list[Path] = []
            try:
                for dirpath, dirnames, filenames in os.walk(cwd_dir):
                    cur = Path(dirpath)
                    depth = len(cur.parts) - root_depth
                    dirnames[:] = [
                        d
                        for d in dirnames
                        if depth < 3
                        and not d.startswith(".")
                        and d.lower() not in _SKIP_DIRS
                    ]
                    for fname in filenames:
                        if Path(fname).suffix.lower() in _IMAGE_EXTS:
                            found_cwd_imgs.append(cur / fname)
            except OSError:
                pass
            found_cwd_imgs.sort(key=lambda x: x.stat().st_mtime, reverse=True)
            for img_p in found_cwd_imgs:
                if len(candidates) >= max_images:
                    break
                if per_dir_count.get(img_p.parent, 0) >= 2:
                    continue
                before = len(candidates)
                _add_candidate(img_p)
                if len(candidates) > before:
                    per_dir_count[img_p.parent] = per_dir_count.get(img_p.parent, 0) + 1

    media_root = vacuum_media_dir(data_dir)
    ingested: list[tuple[str, str, Path]] = []
    for src in candidates[:max_images]:
        try:
            raw_bytes = src.read_bytes()
            digest = hashlib.sha256(raw_bytes).hexdigest()[:16]
            ext = src.suffix.lower()
            stored_name = f"{digest}{ext}"
            dest = media_root / stored_name
            if not dest.exists():
                dest.write_bytes(raw_bytes)
            ingested.append((src.stem, f"/api/agents/media/{stored_name}", dest))
        except OSError:
            continue
    return ingested


def discover_session_documents(
    session_file: Path,
    *,
    agent_id: str = "",
    max_docs: int = 4,
) -> list[Path]:
    """发现会话所属项目工作区（cwd）内的 Word / Excel / PPT / PDF 核心文档，吸尘时一并挂载。"""
    codex_cat = _load_codex_catalog() if agent_id == "codex" else None
    cwd_dir = resolve_session_workspace(agent_id, session_file, codex_cat)
    if cwd_dir is None:
        return []
    root_depth = len(cwd_dir.parts)
    found: list[Path] = []
    try:
        for dirpath, dirnames, filenames in os.walk(cwd_dir):
            cur = Path(dirpath)
            depth = len(cur.parts) - root_depth
            dirnames[:] = [
                d
                for d in dirnames
                if depth < 3 and not d.startswith(".") and d.lower() not in _SKIP_DIRS
            ]
            for fname in filenames:
                if fname.startswith(".") or fname.startswith("~$"):
                    continue
                fp = cur / fname
                if fp.suffix.lower() not in _DOC_ATTACH_EXTS:
                    continue
                try:
                    st = fp.stat()
                    if 0 < st.st_size <= 25 * 1024 * 1024:
                        found.append(fp)
                except OSError:
                    continue
    except OSError:
        return []
    found.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return found[:max_docs]


def _load_json_dict(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _save_json_dict(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _slug(name: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", name.strip().lower()).strip("-")
    return cleaned or "custom-agent"


def agent_space_name(name: str) -> str:
    clean = re.sub(r"^Agent\s*·\s*", "", name.strip(), flags=re.IGNORECASE).strip()
    return f"Agent · {clean}"


_SKIP_DIRS = frozenset(
    {
        "node_modules",
        "extensions",
        "cache",
        "code cache",
        "gpucache",
        "attachments",
        "blob_storage",
        ".git",
        "__pycache__",
        ".venv",
    }
)


def _list_session_files(
    session_dir: Path | None, globs: tuple[str, ...], *, max_depth: int = 4
) -> list[Path]:
    if session_dir is None or not session_dir.is_dir():
        return []
    found: dict[str, Path] = {}
    root_depth = len(session_dir.parts)
    suffixes = tuple(
        Path(g).name.split("*")[-1].lower()
        for g in globs
        if "*" in Path(g).name and "." in Path(g).name.split("*")[-1]
    )
    exact_names = tuple(
        Path(g).name.lower() for g in globs if "*" not in Path(g).name
    )
    try:
        for dirpath, dirnames, filenames in os.walk(session_dir):
            cur = Path(dirpath)
            depth = len(cur.parts) - root_depth
            dirnames[:] = [
                d for d in dirnames if depth < max_depth and d.lower() not in _SKIP_DIRS
            ]
            for fname in filenames:
                low = fname.lower()
                if exact_names and low not in exact_names:
                    continue
                if not exact_names and suffixes and not any(low.endswith(suf) for suf in suffixes):
                    continue
                fpath = cur / fname
                try:
                    if fpath.stat().st_size > 20:
                        found[str(fpath.resolve())] = fpath
                except OSError:
                    continue
    except OSError:
        return []
    return sorted(found.values(), key=lambda p: p.stat().st_mtime, reverse=True)


def _file_signature(path: Path) -> str:
    st = path.stat()
    return f"{int(st.st_mtime)}:{st.st_size}"


def _has_rule_installed(rule_file: Path | None) -> bool:
    if rule_file is None or not rule_file.is_file():
        return False
    try:
        return _RULE_MARKER_START in rule_file.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False


def _install_rule_file(rule_file: Path, agent_name: str) -> bool:
    if _has_rule_installed(rule_file):
        return True
    block = (
        f"{_RULE_MARKER_START}\n"
        "## ExplainLab 个人知识库自动记忆协议（必须遵守）\n\n"
        "你已接入本地 `explainlab` MCP Server（用户的跨 Agent 统一长期记忆外脑）。请自动遵守：\n"
        "1. **先查后答**：当用户提及历史项目决策、个人偏好、既往踩坑或跨工具上下文时，先调用 `explainlab_search_knowledge` 检索已有记忆。\n"
        "2. **自动沉淀（无需用户每次提醒）**：当本轮对话产出了**有价值的结论、架构规划、关键排错经验、新概念总结或明确的用户长期偏好**时，"
        f'主动调用 `explainlab_record_knowledge`（务必传入 `agent_name: "{agent_name}"` 和简明标签 `tags`）将其沉淀到 ExplainLab；'
        "若与旧知识有关联，顺手调用 `explainlab_link_knowledge` 建立图谱连线。\n"
        "3. **只记高价值，严守安全**：不要记录寒暄、纯过程日志或一次性临时问答；严禁写入任何 API Key、密码、Token 或敏感凭证。\n"
        f"{_RULE_MARKER_END}\n"
    )
    try:
        rule_file.parent.mkdir(parents=True, exist_ok=True)
        if rule_file.is_file():
            backup = rule_file.with_name(rule_file.name + ".bak-explainlab")
            shutil.copy2(rule_file, backup)
            existing = rule_file.read_text(encoding="utf-8", errors="ignore").rstrip()
            rule_file.write_text(f"{existing}\n\n{block}", encoding="utf-8")
        else:
            rule_file.write_text(block, encoding="utf-8")
        return True
    except OSError:
        return False


def _space_maps(session: Session) -> tuple[dict[str, KnowledgeSpace], dict[str, int]]:
    spaces = session.scalars(select(KnowledgeSpace)).all()
    by_lower_name = {s.name.strip().lower(): s for s in spaces}
    counts_rows = session.execute(
        select(KnowledgeItemORM.space_id, func.count(KnowledgeItemORM.id)).group_by(
            KnowledgeItemORM.space_id
        )
    ).all()
    counts = {str(sid): int(cnt) for sid, cnt in counts_rows if sid}
    return by_lower_name, counts


def discover_agents(session: Session, data_dir: Path) -> list[AgentStatus]:
    """探测本机已安装与已接入的 AI Agent，以及各自未吸尘的会话数。"""
    by_name, counts = _space_maps(session)
    registry = _load_json_dict(_registry_path(data_dir))
    custom_entries: dict[str, dict[str, Any]] = registry.get("custom", {})
    vacuum_state = _load_json_dict(_vacuum_state_path(data_dir))
    processed: dict[str, str] = vacuum_state.get("processed", {})
    last_by_agent: dict[str, str] = vacuum_state.get("last_vacuum_at", {})

    results: list[AgentStatus] = []
    seen_space_keys: set[str] = set()

    for spec in _known_specs():
        sp_name = agent_space_name(spec.name)
        sp_key = sp_name.lower()
        seen_space_keys.add(sp_key)
        space = by_name.get(sp_key)
        override_dir = custom_entries.get(spec.id, {}).get("session_dir")
        session_dir = Path(override_dir) if override_dir else spec.session_dir
        files = _list_session_files(session_dir, spec.session_globs)
        unprocessed = sum(
            1 for f in files if processed.get(str(f.resolve())) != _file_signature(f)
        )
        installed = spec.detect_dir.exists() or bool(files)
        results.append(
            AgentStatus(
                id=spec.id,
                name=spec.name,
                description=spec.description,
                space_name=sp_name,
                space_id=space.id if space else None,
                installed=installed,
                connected=space is not None,
                item_count=counts.get(space.id, 0) if space else 0,
                session_dir=str(session_dir) if session_dir.exists() else None,
                session_files_count=len(files),
                unprocessed_count=unprocessed,
                rule_installed=_has_rule_installed(spec.rule_file),
                last_vacuum_at=last_by_agent.get(spec.name),
                is_custom=False,
            )
        )

    # 合并自定义登记的 Agent
    known_ids = {s.id for s in _known_specs()}
    for cid, meta in custom_entries.items():
        if cid in known_ids:
            continue
        cname = str(meta.get("name") or cid).strip()
        sp_name = agent_space_name(cname)
        sp_key = sp_name.lower()
        seen_space_keys.add(sp_key)
        space = by_name.get(sp_key)
        sdir_raw = meta.get("session_dir")
        sdir = Path(sdir_raw) if sdir_raw else None
        files = _list_session_files(sdir, ("**/*.jsonl.zstd", "**/*.jsonl", "**/*.md"))
        unprocessed = sum(
            1 for f in files if processed.get(str(f.resolve())) != _file_signature(f)
        )
        results.append(
            AgentStatus(
                id=cid,
                name=cname,
                description=str(meta.get("description") or "自定义接入的 AI 助手 / 桌宠"),
                space_name=sp_name,
                space_id=space.id if space else None,
                installed=True,
                connected=space is not None,
                item_count=counts.get(space.id, 0) if space else 0,
                session_dir=str(sdir) if sdir and sdir.exists() else sdir_raw,
                session_files_count=len(files),
                unprocessed_count=unprocessed,
                rule_installed=False,
                last_vacuum_at=last_by_agent.get(cname),
                is_custom=True,
            )
        )

    # 兜底：数据库中已有但未在注册表里的 `Agent · xxx` 副库
    for sp_key, space in by_name.items():
        if sp_key.startswith("agent ·") and sp_key not in seen_space_keys:
            cname = re.sub(r"^Agent\s*·\s*", "", space.name, flags=re.IGNORECASE).strip()
            results.append(
                AgentStatus(
                    id=_slug(cname),
                    name=cname,
                    description="已创建的 Agent 专属副库",
                    space_name=space.name,
                    space_id=space.id,
                    installed=True,
                    connected=True,
                    item_count=counts.get(space.id, 0),
                    session_dir=None,
                    session_files_count=0,
                    unprocessed_count=0,
                    rule_installed=False,
                    last_vacuum_at=last_by_agent.get(cname),
                    is_custom=True,
                )
            )

    # 排序：已接入 > 本机已安装 > 其余
    results.sort(key=lambda a: (not a.connected, not a.installed, a.name.lower()))
    return results


def add_or_connect_agent(
    session: Session,
    data_dir: Path,
    *,
    name: str,
    description: str | None = None,
    session_dir: str | None = None,
    write_rule: bool = True,
) -> AgentStatus:
    """为指定 Agent 单开专属副库（幂等），登记会话目录并可选写入自动记忆规则。"""
    clean_name = re.sub(r"^Agent\s*·\s*", "", name.strip(), flags=re.IGNORECASE).strip()
    if not clean_name:
        raise ValueError("Agent 名称不能为空")

    sp_name = agent_space_name(clean_name)
    existing = session.scalar(
        select(KnowledgeSpace).where(func.lower(KnowledgeSpace.name) == sp_name.lower())
    )
    if existing is None:
        existing = KnowledgeSpace(
            id=str(uuid4()),
            name=sp_name,
            kind="project",
        )
        session.add(existing)
        session.commit()

    matched_spec = next(
        (
            s
            for s in _known_specs()
            if s.name.lower() == clean_name.lower() or s.id == clean_name.lower()
        ),
        None,
    )
    agent_id = matched_spec.id if matched_spec else _slug(clean_name)

    registry = _load_json_dict(_registry_path(data_dir))
    custom = registry.setdefault("custom", {})
    if matched_spec is None or (session_dir and session_dir.strip()):
        entry = custom.get(agent_id, {})
        entry["name"] = matched_spec.name if matched_spec else clean_name
        if description:
            entry["description"] = description.strip()
        if session_dir and session_dir.strip():
            entry["session_dir"] = session_dir.strip()
        custom[agent_id] = entry
        _save_json_dict(_registry_path(data_dir), registry)

    if (
        write_rule
        and matched_spec
        and matched_spec.rule_file is not None
        and matched_spec.detect_dir.exists()
    ):
        _install_rule_file(matched_spec.rule_file, matched_spec.name)

    all_agents = discover_agents(session, data_dir)
    for item in all_agents:
        if item.space_name.lower() == sp_name.lower():
            return item
    raise RuntimeError(f"无法读取刚接入的 Agent 状态: {clean_name}")


def sanitize_sensitive_text(text: str) -> str:
    """对对话摘录做密钥与凭证脱敏。"""
    result = text
    for pattern, repl in _SECRET_PATTERNS:
        result = pattern.sub(repl, result)
    return result


def _read_session_raw_text(path: Path, *, max_bytes: int = 2 * 1024 * 1024) -> str:
    """安全读取会话文本；对超大文件（如百 MB 级 Codex 日志）仅采样头尾窗口，防止卡死事件循环。"""
    if path.suffix.lower() == ".zstd":
        proc = subprocess.run(
            ["zstd", "-dc", str(path)],
            capture_output=True,
            timeout=15,
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"zstd 解压失败: {path.name}")
        raw_bytes = proc.stdout
        if len(raw_bytes) > max_bytes:
            head_b = raw_bytes[: max_bytes // 3]
            tail_b = raw_bytes[-(max_bytes * 2 // 3) :]
            return head_b.decode("utf-8", errors="ignore") + "\n" + tail_b.decode("utf-8", errors="ignore")
        return raw_bytes.decode("utf-8", errors="ignore")

    size = path.stat().st_size
    if size <= max_bytes:
        return path.read_text(encoding="utf-8", errors="ignore")
    with path.open("rb") as fh:
        head_b = fh.read(max_bytes // 3)
        fh.seek(max(0, size - (max_bytes * 2 // 3)))
        tail_b = fh.read()
    return head_b.decode("utf-8", errors="ignore") + "\n" + tail_b.decode("utf-8", errors="ignore")


def _extract_text_from_content(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block.strip())
            elif isinstance(block, dict):
                txt = block.get("text") or block.get("content")
                if isinstance(txt, str) and txt.strip():
                    parts.append(txt.strip())
        return "\n".join(parts).strip()
    if isinstance(content, dict):
        txt = content.get("text") or content.get("content")
        return txt.strip() if isinstance(txt, str) else ""
    return ""


def _clean_user_tags(text: str) -> str:
    cleaned = re.sub(r"</?USER_REQUEST>", "", text, flags=re.IGNORECASE)
    for tag in ("ADDITIONAL_METADATA", "USER_SETTINGS_CHANGE", "SYSTEM_MESSAGE", "CONTEXT_SUMMARY"):
        cleaned = re.sub(rf"<{tag}>[\s\S]*?</{tag}>", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(rf"<{tag}>[\s\S]*$", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def _clean_display_snippet(text: str, max_len: int = 88) -> str:
    cleaned = _clean_user_tags(text)
    cleaned = re.sub(r"[#*`>]+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -·：:，,")
    return sanitize_sensitive_text(cleaned)[:max_len]


_TRIVIAL_INPUTS = {
    "ok", "好", "好的", "可以", "继续", "行", "嗯", "开始", "做吧", "加上", "收到", "测试", "1", "111", "333",
}


def _is_substantive_topic(text: str) -> bool:
    low = text.strip().lower()
    if len(low) < 5 or low in _TRIVIAL_INPUTS:
        return False
    return not re.fullmatch(r"[\d\s.,!?;:]+", low)


def _extract_turn_from_obj(obj: dict[str, Any]) -> tuple[str, str] | None:
    """从单条 JSONL 记录中提取 (角色标签, 正文)；兼容 Antigravity / Claude / Codex / DSH。"""
    ev_type = str(obj.get("type") or "").upper()
    if ev_type == "USER_INPUT":
        txt = _clean_user_tags(_extract_text_from_content(obj.get("content")))
        return ("用户", txt) if len(txt) >= 2 else None
    if ev_type == "PLANNER_RESPONSE":
        txt = _extract_text_from_content(obj.get("response") or obj.get("content"))
        return ("助手", txt) if len(txt) >= 4 else None

    role = obj.get("role") or obj.get("type")
    payload = obj.get("message") if isinstance(obj.get("message"), dict) else obj
    if isinstance(payload, dict) and payload.get("role"):
        role = payload.get("role")

    role_str = str(role or "").lower()
    if role_str not in ("user", "human", "assistant", "model"):
        data = obj.get("payload") or obj.get("data")
        if isinstance(data, dict) and str(data.get("role", "")).lower() in (
            "user",
            "human",
            "assistant",
            "model",
        ):
            role_str = str(data.get("role")).lower()
            payload = data
        else:
            return None

    text = _clean_user_tags(_extract_text_from_content(payload.get("content") or payload.get("text")))
    if not text or len(text) < 4:
        return None
    label = "用户" if role_str in ("user", "human") else "助手"
    return (label, text)


def extract_dialogue_from_session_file(path: Path, *, max_chars: int = 8000) -> str:
    """从 .jsonl / .jsonl.zstd / .md 会话文件中提取可读的 User/Assistant 对话摘录。

    对百 MB 级 Computer Use 日志逐行流式读取并跳过 >250KB 的纯 Base64 截图行，
    确保毫秒级提取全部真实文本对话，不被截图行截断。
    """
    if path.suffix.lower() == ".md":
        raw = _read_session_raw_text(path)
        return sanitize_sensitive_text(raw.strip()[:max_chars])

    turns: list[str] = []

    def _consume_line(raw_line: str) -> None:
        line = raw_line.strip()
        if not line or not line.startswith("{") or len(line) > 250_000:
            return
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            return
        if not isinstance(obj, dict):
            return
        parsed = _extract_turn_from_obj(obj)
        if parsed is None:
            return
        label, text = parsed
        turns.append(f"[{label}] {text[:1200]}")

    if path.suffix.lower() == ".zstd":
        raw = _read_session_raw_text(path, max_bytes=6 * 1024 * 1024)
        for ln in raw.splitlines():
            _consume_line(ln)
    else:
        with path.open("rb") as fh:
            for b_line in fh:
                if len(b_line) > 250_000:
                    continue
                _consume_line(b_line.decode("utf-8", errors="ignore"))

    if not turns:
        return ""

    # 优先保留开篇背景与最新收尾对话
    joined = "\n\n".join(turns)
    if len(joined) > max_chars:
        head = joined[: max_chars // 3]
        tail = joined[-(max_chars * 2 // 3) :]
        joined = f"{head}\n\n...（中间过程已省略）...\n\n{tail}"
    return sanitize_sensitive_text(joined)


def _load_codex_catalog() -> dict[str, tuple[str, str, str]]:
    """只读读取 Codex 本地 sqlite 目录表，将 thread_id 映射到 (项目名, 真实对话标题, cwd)。"""
    db_path = _home() / ".codex" / "sqlite" / "codex.db"
    if not db_path.is_file():
        return {}
    mapping: dict[str, tuple[str, str, str]] = {}
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=1.5)
        rows = con.execute(
            "SELECT thread_id, display_title, cwd FROM local_thread_catalog WHERE host_id='local'"
        ).fetchall()
        con.close()
        for tid, title, cwd in rows:
            if not tid:
                continue
            cwd_str = str(cwd or "").strip()
            proj = Path(cwd_str).name if cwd_str else ""
            mapping[str(tid)] = (proj, str(title or "").strip(), cwd_str)
    except Exception:
        return {}
    return mapping


def _extract_codex_cwd_from_head(path: Path) -> str:
    p = resolve_session_workspace("codex", path)
    return p.name if p else ""


def _friendly_session_label(
    path: Path, session_dir: Path, codex_catalog: dict[str, tuple[str, str, str]] | None = None
) -> str:
    if codex_catalog is not None and path.name.startswith("rollout-"):
        for tid, (proj, title, _) in codex_catalog.items():
            if tid in path.name:
                if proj and title:
                    return f"[{proj}] {title}"[:56]
                if title:
                    return title[:56]
                if proj:
                    return f"[{proj}] {path.stem[:24]}"
        cwd_name = _extract_codex_cwd_from_head(path)
        if cwd_name:
            return f"[{cwd_name}] {path.stem[8:24]}"

    try:
        rel = path.relative_to(session_dir)
        parts = list(rel.parts)
    except ValueError:
        parts = [path.parent.name, path.name]
    if path.name.lower() == "transcript.jsonl" and len(parts) >= 1:
        return f"会话 {parts[0][:8]}"
    if len(parts) >= 2:
        raw_parent = parts[0].strip("-")
        raw_parent = re.sub(r"~[0-9A-Fa-f]{4}", " ", raw_parent)
        return raw_parent[:48] or path.stem
    return path.stem[:48]


def _quick_session_preview(path: Path) -> str:
    """快速提取会话里的第一句用户发言作为可视化预览，方便自定义勾选。"""
    try:
        if path.suffix.lower() == ".zstd":
            # zstd 文件可能较大，仅读取解压后的前 96KB 提取首句预览
            proc = subprocess.run(
                ["zstd", "-dc", str(path)],
                capture_output=True,
                timeout=6,
                check=False,
            )
            if proc.returncode != 0:
                return path.name
            raw = proc.stdout[:98304].decode("utf-8", errors="ignore")
        else:
            # Codex 等工具前部常含较长 developer 指令，放宽至 256KB 以准确抓到用户首句
            with path.open("r", encoding="utf-8", errors="ignore") as fh:
                raw = fh.read(262144)
    except Exception:
        return path.name

    if path.suffix.lower() == ".md":
        first = next((ln.strip("# ").strip() for ln in raw.splitlines() if ln.strip()), path.name)
        return sanitize_sensitive_text(first)[:90]

    for line in raw.splitlines():
        line = line.strip()
        if not line or not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        parsed = _extract_turn_from_obj(obj)
        if parsed and parsed[0] == "用户":
            one_line = re.sub(r"\s+", " ", parsed[1]).strip()
            if len(one_line) >= 3:
                return sanitize_sensitive_text(one_line)[:90]
    return path.name


def _build_human_session_card(
    agent_id: str,
    path: Path,
    session_dir: Path,
    codex_catalog: dict[str, tuple[str, str, str]] | None = None,
) -> tuple[str, str]:
    """为任意 Agent 会话生成小白一眼看懂的 (中文主题标题, 最新进展摘要)。"""
    base_label = _friendly_session_label(path, session_dir, codex_catalog)
    has_meaningful_base = (
        codex_catalog is not None
        and base_label.startswith("[")
    ) or (
        not base_label.startswith("会话 ")
        and not re.fullmatch(r"(?:session|chat|conv|log|transcript)[\-_0-9a-z]*", base_label, flags=re.IGNORECASE)
        and not re.fullmatch(r"[0-9a-f\-]{8,}", base_label, flags=re.IGNORECASE)
    )

    head_topic = ""
    fallback_user = ""
    fallback_assistant = ""
    subagent_hint = ""
    try:
        if path.suffix.lower() == ".zstd":
            proc = subprocess.run(
                ["zstd", "-dc", str(path)],
                capture_output=True,
                timeout=6,
                check=False,
            )
            head_raw = proc.stdout[:131072].decode("utf-8", errors="ignore") if proc.returncode == 0 else ""
        else:
            with path.open("r", encoding="utf-8", errors="ignore") as fh:
                head_raw = fh.read(262144)
    except Exception:
        head_raw = ""

    if path.suffix.lower() == ".md":
        first = next((ln for ln in head_raw.splitlines() if ln.strip()), "")
        clean_first = _clean_display_snippet(first, 44)
        return (base_label if has_meaningful_base else (clean_first or base_label)), (
            _clean_display_snippet(head_raw, 96) or path.name
        )

    for line in head_raw.splitlines():
        line = line.strip()
        if not line or not line.startswith("{") or len(line) > 250_000:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        parsed = _extract_turn_from_obj(obj)
        if parsed:
            role, text = parsed
            snippet = _clean_display_snippet(text, 96)
            if role == "用户":
                if not fallback_user and snippet:
                    fallback_user = snippet
                if not head_topic and _is_substantive_topic(snippet):
                    head_topic = snippet
                    break
            elif role == "助手" and not fallback_assistant and len(snippet) >= 8:
                fallback_assistant = snippet
        elif not subagent_hint and str(obj.get("type") or "").upper() == "SYSTEM_MESSAGE":
            raw_sys = _extract_text_from_content(obj.get("content"))
            m = re.search(r"content=(.{12,180})", raw_sys)
            if m:
                subagent_hint = _clean_display_snippet(m.group(1), 64)

    tail_title, tail_preview = _extract_latest_task_summary(path, base_label)
    # 尝试从尾部反查最新实质用户话题（当长会话前面是旧审计/寒暄时）
    clean_tail_topic = tail_title.removeprefix("刚讨论：").strip()

    ws = resolve_session_workspace(agent_id, path)
    ws_prefix = f"[{ws.name}] " if ws and ws.name and ws.name.lower() not in ("brain", "sessions", "logs") else ""

    if has_meaningful_base:
        final_label = base_label
    elif head_topic:
        final_label = f"{ws_prefix}{head_topic[:36]}"
    elif _is_substantive_topic(clean_tail_topic):
        final_label = f"{ws_prefix}{clean_tail_topic[:36]}"
    elif fallback_assistant:
        final_label = f"[后台子任务] {fallback_assistant[:34]}"
    elif subagent_hint:
        final_label = f"[后台子任务] {subagent_hint[:34]}"
    elif fallback_user:
        final_label = f"{ws_prefix}{fallback_user[:34]}"
    else:
        final_label = base_label

    # 预览优先同时交代「讨论主题 + 最新进展」，小白一眼看懂且方便关键词搜索
    clean_tail_body = (
        tail_preview.removeprefix("待记录结论：").removeprefix("最新内容：").strip()
        if tail_preview and tail_preview != path.name and not tail_preview.startswith("transcript")
        else ""
    )
    if head_topic and clean_tail_body and head_topic[:12] not in clean_tail_body:
        final_preview = f"主题：{head_topic[:42]} ｜ 最新：{clean_tail_body[:58]}"
    elif head_topic:
        final_preview = f"主题：{head_topic[:96]}"
    elif clean_tail_body:
        final_preview = f"最新进展：{clean_tail_body[:96]}"
    elif fallback_assistant:
        final_preview = f"助手回复：{fallback_assistant[:92]}"
    elif subagent_hint:
        final_preview = f"子代理任务：{subagent_hint[:92]}"
    else:
        final_preview = "暂无可预览正文"

    return final_label[:56], final_preview[:120]


def list_agent_sessions(
    session: Session,
    data_dir: Path,
    agent_id_or_name: str,
    *,
    limit: int = 100,
) -> list[SessionFilePreview]:
    """列出指定 Agent 的本地全部会话文件与易读中文标题/摘要，供用户自定义勾选吸尘。"""
    agents = discover_agents(session, data_dir)
    target = next(
        (
            a
            for a in agents
            if a.id.lower() == agent_id_or_name.strip().lower()
            or a.name.lower() == agent_id_or_name.strip().lower()
        ),
        None,
    )
    if target is None or not target.session_dir:
        return []

    known_globs = {s.id: s.session_globs for s in _known_specs()}
    globs = known_globs.get(target.id, ("**/*.jsonl.zstd", "**/*.jsonl", "**/*.md"))
    sdir = Path(target.session_dir)
    files = _list_session_files(sdir, globs)[:limit]
    vacuum_state = _load_json_dict(_vacuum_state_path(data_dir))
    processed: dict[str, str] = vacuum_state.get("processed", {})
    created_counts: dict[str, int] = vacuum_state.get("created_counts", {})
    codex_catalog = _load_codex_catalog() if target.id == "codex" else None

    previews: list[SessionFilePreview] = []
    for fpath in files:
        st = fpath.stat()
        fkey = str(fpath.resolve())
        sig = f"{int(st.st_mtime)}:{st.st_size}"
        is_proc = processed.get(fkey) == sig
        label, preview = _build_human_session_card(target.id, fpath, sdir, codex_catalog)
        previews.append(
            SessionFilePreview(
                file_path=fkey,
                label=label,
                preview=preview,
                updated_at=datetime.fromtimestamp(st.st_mtime, tz=UTC).isoformat(),
                size_kb=round(st.st_size / 1024.0, 1),
                processed=is_proc,
                created_count=int(created_counts.get(fkey, 0)) if is_proc else 0,
            )
        )
    return previews


def _parse_extracted_items(raw: str) -> list[tuple[str, str]]:
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        text = text[start : end + 1]
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    raw_items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(raw_items, list):
        return []
    out: list[tuple[str, str]] = []
    for entry in raw_items[:3]:
        if not isinstance(entry, dict):
            continue
        title = str(entry.get("title") or "").strip()
        content = str(entry.get("content") or "").strip()
        if len(title) >= 2 and len(content) >= 12:
            out.append((title[:120], sanitize_sensitive_text(content)))
    return out


async def vacuum_agent_sessions(
    session: Session,
    adapter: ModelAdapter,
    *,
    data_dir: Path,
    agent_name: str | None = None,
    max_sessions: int = 3,
    session_files: list[str] | None = None,
) -> VacuumReport:
    """扫描并吸尘本地对话记录：支持自动增量吸尘（session_files=None）与自定义勾选吸尘。"""
    report = VacuumReport()
    agents = discover_agents(session, data_dir)
    targets = [
        a
        for a in agents
        if a.connected
        and a.space_id
        and a.session_dir
        and (
            agent_name is None
            or a.name.lower() == agent_name.strip().lower()
            or a.id == agent_name.strip().lower()
        )
    ]

    state_path = _vacuum_state_path(data_dir)
    vacuum_state = _load_json_dict(state_path)
    processed: dict[str, str] = vacuum_state.setdefault("processed", {})
    created_counts: dict[str, int] = vacuum_state.setdefault("created_counts", {})
    last_by_agent: dict[str, str] = vacuum_state.setdefault("last_vacuum_at", {})

    known_globs = {s.id: s.session_globs for s in _known_specs()}
    repo = SQLAlchemyKnowledgeRepository(session)
    now_iso = datetime.now(UTC).isoformat()
    selected_set = (
        {str(Path(p).resolve()) for p in session_files if p and p.strip()}
        if session_files
        else None
    )

    for ag in targets:
        assert ag.space_id is not None and ag.session_dir is not None
        globs = known_globs.get(ag.id, ("**/*.jsonl.zstd", "**/*.jsonl", "**/*.md"))
        files = _list_session_files(Path(ag.session_dir), globs)
        if selected_set is not None:
            # 自定义吸尘：仅处理用户勾选且确属该 Agent 会话目录的文件（安全防越权）
            pending = [f for f in files if str(f.resolve()) in selected_set]
        else:
            # 自动吸尘：按游标增量扫描未处理的新对话
            pending = [
                f for f in files if processed.get(str(f.resolve())) != _file_signature(f)
            ][:max_sessions]
        if not pending:
            continue

        existing_rows_by_title = {
            row.title.strip().lower(): row
            for row in session.scalars(
                select(KnowledgeItemORM).where(KnowledgeItemORM.space_id == ag.space_id)
            ).all()
        }

        for fpath in pending:
            sig = _file_signature(fpath)
            fkey = str(fpath.resolve())
            report.scanned_sessions += 1
            try:
                dialogue = extract_dialogue_from_session_file(fpath)
            except Exception as exc:
                report.errors.append(f"{ag.name}/{fpath.name}: {exc}")
                continue

            if len(dialogue) < 80:
                processed[fkey] = sig
                created_counts[fkey] = 0
                report.skipped_sessions += 1
                continue

            session_images = ingest_session_images(fpath, dialogue, data_dir, agent_id=ag.id)
            session_docs = discover_session_documents(fpath, agent_id=ag.id, max_docs=4)
            image_section = ""
            if session_images:
                img_lines = "\n".join(
                    f"- {img_name}: {img_url}" for img_name, img_url, _ in session_images
                )
                image_section = (
                    "\n\n关联图片资产列表（请将相关图片用 Markdown `![说明](URL)` 嵌入对应知识卡片中）：\n"
                    f"{img_lines}"
                )

            try:
                resp = await adapter.generate(
                    ModelRequest(
                        messages=[
                            ModelMessage(role="system", content=_VACUUM_SYSTEM_PROMPT),
                            ModelMessage(
                                role="user",
                                content=(
                                    f"来源 Agent：{ag.name}\n"
                                    f"会话文件：{fpath.parent.name}/{fpath.name}\n\n"
                                    f"对话摘录：\n{dialogue}"
                                    f"{image_section}"
                                ),
                            ),
                        ],
                        temperature=0.2,
                        max_tokens=2600,
                    )
                )
            except Exception as exc:
                report.errors.append(f"{ag.name}/{fpath.name} 模型提炼失败: {type(exc).__name__}")
                continue

            extracted = _parse_extracted_items(resp.content)
            if not extracted:
                processed[fkey] = sig
                created_counts[fkey] = 0
                report.skipped_sessions += 1
                continue

            def _attach_images_to_item(
                target_item_id: str,
                imgs: list[tuple[str, str, Path]] = session_images,
                docs: list[Path] = session_docs,
            ) -> None:
                if not imgs and not docs:
                    return
                already = {m.filename for m in list_media(data_dir, target_item_id)}
                for img_stem, _, img_path in imgs:
                    fname = f"{img_stem}{img_path.suffix.lower()}"
                    if fname in already:
                        continue
                    try:
                        save_media_bytes(
                            data_dir,
                            target_item_id,
                            filename=fname,
                            content=img_path.read_bytes(),
                        )
                        already.add(fname)
                    except Exception:
                        continue
                for doc_path in docs:
                    if doc_path.name in already:
                        continue
                    try:
                        save_media_bytes(
                            data_dir,
                            target_item_id,
                            filename=doc_path.name,
                            content=doc_path.read_bytes(),
                        )
                        already.add(doc_path.name)
                    except Exception:
                        continue

            created_here = 0
            for idx_item, (title, content) in enumerate(extracted):
                # 兜底：若发现了项目图片但首条卡片正文里模型漏嵌了图片，自动追加素材预览块
                if idx_item == 0 and session_images and "/api/agents/media/" not in content:
                    gallery = "\n\n".join(
                        f"![{stem}]({url})" for stem, url, _ in session_images[:3]
                    )
                    content = f"{content}\n\n### 关联素材预览\n{gallery}"

                existing_row = existing_rows_by_title.get(title.lower())
                if existing_row is not None:
                    # 自定义重吸时，允许对同名草稿补全图文与附件（绝不改动已生效条目；仅主条目挂载素材避免重复）
                    if selected_set is not None and existing_row.status == KnowledgeStatus.DRAFT.value:
                        existing_row.content = content
                        existing_row.updated_at = datetime.now(UTC)
                        if idx_item == 0:
                            _attach_images_to_item(existing_row.id)
                        created_here += 1
                        report.created_items.append(
                            VacuumCreatedItem(
                                id=existing_row.id,
                                agent_name=ag.name,
                                space_id=ag.space_id,
                                title=existing_row.title,
                                source_file=f"{fpath.parent.name}/{fpath.name}",
                            )
                        )
                    continue

                item = KnowledgeItem(
                    title=title,
                    content=content,
                    status=KnowledgeStatus.DRAFT,
                    space_id=ag.space_id,
                    source_refs=[
                        SourceRef(
                            source_type=SourceType.IMPORT,
                            uri=f"agent://{ag.name}/vacuum/{fpath.parent.name}",
                            excerpt=f"由 ExplainLab 本地吸尘器自动从 {ag.name} 对话中提炼",
                        )
                    ],
                )
                saved = repo.save(item)
                if idx_item == 0:
                    _attach_images_to_item(str(saved.id))
                created_here += 1
                report.created_items.append(
                    VacuumCreatedItem(
                        id=str(saved.id),
                        agent_name=ag.name,
                        space_id=ag.space_id,
                        title=saved.title,
                        source_file=f"{fpath.parent.name}/{fpath.name}",
                    )
                )

            processed[fkey] = sig
            created_counts[fkey] = created_counts.get(fkey, 0) + created_here
            last_by_agent[ag.name] = now_iso

        session.commit()
        _save_json_dict(state_path, vacuum_state)

    return report


@dataclass(slots=True)
class CompletedTaskSuggestion:
    suggestion_id: str
    agent_id: str
    agent_name: str
    space_id: str | None
    file_path: str
    signature: str
    label: str
    preview: str
    updated_at: str


def _notify_state_path(data_dir: Path) -> Path:
    return data_dir / "agent_notify_state.json"


def dismiss_task_suggestion(data_dir: Path, *, file_path: str, signature: str) -> None:
    """记录用户忽略或已弹窗的会话快照，同一快照不再重复弹出。"""
    path = _notify_state_path(data_dir)
    state = _load_json_dict(path)
    dismissed: dict[str, str] = state.setdefault("dismissed", {})
    dismissed[str(Path(file_path).resolve())] = signature
    _save_json_dict(path, state)


def _extract_latest_task_summary(path: Path, fallback_label: str) -> tuple[str, str]:
    """从会话文件尾部提取「刚刚完成的最新一轮」任务标题与结论摘要（零 Token，直观易懂）。"""
    try:
        if path.suffix.lower() == ".zstd":
            proc = subprocess.run(
                ["zstd", "-dc", str(path)],
                capture_output=True,
                timeout=6,
                check=False,
            )
            if proc.returncode != 0:
                return fallback_label, _quick_session_preview(path)
            raw = proc.stdout[-98304:].decode("utf-8", errors="ignore")
        else:
            size = path.stat().st_size
            with path.open("rb") as fh:
                if size > 131072:
                    fh.seek(size - 131072)
                    fh.readline()  # 跳过截断的首行
                raw = fh.read().decode("utf-8", errors="ignore")
    except Exception:
        return fallback_label, _quick_session_preview(path)

    if path.suffix.lower() == ".md":
        lines = [ln.strip("# >-").strip() for ln in raw.splitlines() if ln.strip()]
        if lines:
            title = sanitize_sensitive_text(lines[-2] if len(lines) >= 2 else lines[-1])[:42]
            summary = sanitize_sensitive_text(lines[-1])[:96]
            return title or fallback_label, summary
        return fallback_label, fallback_label

    last_user = ""
    last_assistant = ""
    for line in raw.splitlines():
        line = line.strip()
        if not line or not line.startswith("{") or len(line) > 250_000:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        parsed = _extract_turn_from_obj(obj)
        if not parsed:
            continue
        role, text = parsed
        # 清洗 Markdown 标题符、多余换行与系统提示包装
        clean = re.sub(r"[#*`>\[\]]+", "", text)
        clean = re.sub(r"\s+", " ", clean).strip()
        if len(clean) < 4:
            continue
        if role == "用户":
            last_user = clean
        elif role == "助手":
            last_assistant = clean

    title = (
        f"刚讨论：{sanitize_sensitive_text(last_user)[:34]}"
        if last_user
        else fallback_label
    )
    if last_assistant:
        preview = f"待记录结论：{sanitize_sensitive_text(last_assistant)[:92]}"
    elif last_user:
        preview = f"最新内容：{sanitize_sensitive_text(last_user)[:92]}"
    else:
        preview = _quick_session_preview(path)
    return title, preview


def detect_completed_agent_tasks(
    session: Session,
    data_dir: Path,
    *,
    idle_seconds: float = 45.0,
    max_age_seconds: float = 1800.0,
    cooldown_seconds: float = 600.0,
    min_growth_bytes: int = 2500,
    include_latest: bool = False,
    mark_notified: bool = True,
) -> list[CompletedTaskSuggestion]:
    """轻量零 Token 检测刚完成任务的 Agent 会话，供桌面悬浮提示窗弹出。

    防骚扰与直观性策略：
    - 仅检测已接入（connected）的 Agent 本地会话文件；
    - 首次运行写入 baseline_ts，绝不把历史旧会话一次性全弹出来；
    - 静默等待 >= 45 秒（真正等一轮对话结束，而非思考/跑命令中途）；
    - 同会话 10 分钟冷却期 + 至少新增 2.5 KB 实质内容才会再次弹出，杜绝一轮弹多次；
    - 标题与预览直接取文件尾部「最新一轮用户问题 + 助手结论」，一眼看懂准备记什么。
    """
    now_ts = datetime.now(UTC).timestamp()
    state_path = _notify_state_path(data_dir)
    notify_state = _load_json_dict(state_path)
    baseline_ts = notify_state.get("baseline_ts")
    if not isinstance(baseline_ts, (int, float)):
        notify_state["baseline_ts"] = now_ts
        _save_json_dict(state_path, notify_state)
        if not include_latest:
            return []
        baseline_ts = now_ts

    dismissed: dict[str, str] = notify_state.setdefault("dismissed", {})
    last_notified_at: dict[str, float] = notify_state.setdefault("last_notified_at", {})
    last_notified_size: dict[str, int] = notify_state.setdefault("last_notified_size", {})
    vacuum_state = _load_json_dict(_vacuum_state_path(data_dir))
    processed: dict[str, str] = vacuum_state.get("processed", {})

    agents = discover_agents(session, data_dir)
    known_globs = {s.id: s.session_globs for s in _known_specs()}
    codex_catalog: dict[str, tuple[str, str, str]] | None = None

    candidates: list[tuple[float, CompletedTaskSuggestion]] = []
    for ag in agents:
        if not ag.connected or not ag.session_dir:
            continue
        globs = known_globs.get(ag.id, ("**/*.jsonl.zstd", "**/*.jsonl", "**/*.md"))
        sdir = Path(ag.session_dir)
        files = _list_session_files(sdir, globs)[:8]
        for fpath in files:
            try:
                st = fpath.stat()
            except OSError:
                continue
            if st.st_size < 600:
                continue
            fkey = str(fpath.resolve())
            sig = f"{int(st.st_mtime)}:{st.st_size}"
            age = now_ts - st.st_mtime

            if not include_latest:
                if st.st_mtime < float(baseline_ts):
                    continue
                if age < idle_seconds or age > max_age_seconds:
                    continue
                if processed.get(fkey) == sig or dismissed.get(fkey) == sig:
                    continue
                prev_ts = float(last_notified_at.get(fkey, 0.0))
                if prev_ts > 0 and (now_ts - prev_ts) < cooldown_seconds:
                    continue
                prev_sz = int(last_notified_size.get(fkey, 0))
                if prev_sz > 0 and (st.st_size - prev_sz) < min_growth_bytes:
                    continue

            if ag.id == "codex" and codex_catalog is None:
                codex_catalog = _load_codex_catalog()

            fallback_label = _friendly_session_label(
                fpath, sdir, codex_catalog if ag.id == "codex" else None
            )
            label, preview = _extract_latest_task_summary(fpath, fallback_label)
            candidates.append(
                (
                    st.st_mtime,
                    CompletedTaskSuggestion(
                        suggestion_id=f"{fkey}::{sig}",
                        agent_id=ag.id,
                        agent_name=ag.name,
                        space_id=ag.space_id,
                        file_path=fkey,
                        signature=sig,
                        label=label,
                        preview=preview,
                        updated_at=datetime.fromtimestamp(st.st_mtime, tz=UTC).isoformat(),
                    ),
                )
            )
            if include_latest:
                break

    if not candidates:
        return []

    candidates.sort(key=lambda item: item[0], reverse=True)
    result = [item[1] for item in candidates[:1]]

    if mark_notified and not include_latest:
        for sug in result:
            dismissed[sug.file_path] = sug.signature
            last_notified_at[sug.file_path] = now_ts
            p_obj = Path(sug.file_path)
            if p_obj.is_file():
                last_notified_size[sug.file_path] = p_obj.stat().st_size
        _save_json_dict(state_path, notify_state)

    return result


@dataclass(slots=True)
class HandoffSessionSummary:
    agent_id: str
    agent_name: str
    label: str
    preview: str
    updated_at: str
    size_kb: float
    file_path: str


@dataclass(slots=True)
class HandoffSessionContent:
    agent_id: str
    agent_name: str
    label: str
    updated_at: str
    file_path: str
    dialogue: str
    truncated: bool


def list_handoff_sessions(
    session: Session,
    data_dir: Path,
    *,
    agent_name: str | None = None,
    keyword: str | None = None,
    limit: int = 12,
) -> list[HandoffSessionSummary]:
    """跨 Agent 接力（纯只读、零写入知识库）：列出本机各 AI 助手最近的对话会话。"""
    agents = discover_agents(session, data_dir)
    known_globs = {s.id: s.session_globs for s in _known_specs()}
    agent_filter = agent_name.strip().lower() if agent_name and agent_name.strip() else None
    kw = keyword.strip().lower() if keyword and keyword.strip() else None
    codex_catalog: dict[str, tuple[str, str, str]] | None = None

    rows: list[tuple[float, HandoffSessionSummary]] = []
    for ag in agents:
        if not ag.session_dir:
            continue
        if agent_filter and agent_filter not in ag.id.lower() and agent_filter not in ag.name.lower():
            continue
        sdir = Path(ag.session_dir)
        if not sdir.is_dir():
            continue
        globs = known_globs.get(ag.id, ("**/*.jsonl.zstd", "**/*.jsonl", "**/*.md"))
        files = _list_session_files(sdir, globs)[:25]
        if ag.id == "codex" and codex_catalog is None:
            codex_catalog = _load_codex_catalog()

        for fpath in files:
            try:
                st = fpath.stat()
            except OSError:
                continue
            if st.st_size < 120:
                continue
            label, preview = _build_human_session_card(
                ag.id, fpath, sdir, codex_catalog if ag.id == "codex" else None
            )
            if kw and kw not in label.lower() and kw not in preview.lower() and kw not in ag.name.lower():
                continue
            rows.append(
                (
                    st.st_mtime,
                    HandoffSessionSummary(
                        agent_id=ag.id,
                        agent_name=ag.name,
                        label=label,
                        preview=preview,
                        updated_at=datetime.fromtimestamp(st.st_mtime, tz=UTC).isoformat(),
                        size_kb=round(st.st_size / 1024.0, 1),
                        file_path=str(fpath.resolve()),
                    ),
                )
            )

    rows.sort(key=lambda item: item[0], reverse=True)
    return [item[1] for item in rows[: max(1, min(limit, 50))]]


def read_handoff_session(
    session: Session,
    data_dir: Path,
    *,
    file_path: str,
    max_chars: int = 12000,
) -> HandoffSessionContent:
    """跨 Agent 接力（纯只读、严格目录白名单校验、自动脱敏）：读取指定会话的对话上下文。"""
    target = Path(file_path).resolve()
    if not target.is_file():
        raise FileNotFoundError("会话文件不存在")

    agents = discover_agents(session, data_dir)
    owner: AgentStatus | None = None
    for ag in agents:
        if not ag.session_dir:
            continue
        sdir = Path(ag.session_dir).resolve()
        if target.is_relative_to(sdir):
            owner = ag
            break

    if owner is None:
        raise PermissionError("拒绝访问：该文件不属于本机已登记的 AI 助手会话目录")

    safe_limit = max(1000, min(int(max_chars), 30000))
    dialogue = extract_dialogue_from_session_file(target, max_chars=safe_limit)
    st = target.stat()
    codex_catalog = _load_codex_catalog() if owner.id == "codex" else None
    label = _friendly_session_label(target, Path(owner.session_dir), codex_catalog)
    return HandoffSessionContent(
        agent_id=owner.id,
        agent_name=owner.name,
        label=label,
        updated_at=datetime.fromtimestamp(st.st_mtime, tz=UTC).isoformat(),
        file_path=str(target),
        dialogue=dialogue,
        truncated="...（中间过程已省略）..." in dialogue,
    )
