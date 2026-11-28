"""交互式动态原理沙盒（Live Explain Sandbox）服务。

让每条知识不再只以静态文字存在：调用已配置的 ModelAdapter 为任意知识条目
生成单文件、无外部依赖、可交互的 HTML+CSS+SVG+JS 原理演示，并持久化保存在
`data_dir/sandboxes/{item_id}.html`（零数据库迁移，双库通用）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from knowledge_core.model_adapter import ModelAdapter, ModelMessage, ModelRequest

_VALID_ITEM_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_FENCE_RE = re.compile(r"```(?:html)?\s*([\s\S]*?)```", re.IGNORECASE)
_EXTERNAL_SCRIPT_RE = re.compile(
    r"<script\b[^>]*\bsrc\s*=[^>]*>[\s\S]*?</script>",
    re.IGNORECASE,
)
_EXTERNAL_LINK_RE = re.compile(
    r"<link\b[^>]*\bhref\s*=\s*['\"]https?://[^>]*>",
    re.IGNORECASE,
)

_SANDBOX_SYSTEM_PROMPT = """你是 ExplainLab 的交互式可视化教学工程师。
请根据用户提供的「知识标题」和「知识内容」，直接输出一个**完整、自包含、无需任何外网 CDN**的单文件 HTML 页面，把抽象概念变成一个**可点击、可调节参数、可单步演进的交互式原理演示沙盒**。

硬性要求（必须 100% 遵守）：
1. 只输出纯 HTML 代码（以 `<!doctype html>` 开头，以 `</html>` 完整结尾），不要输出任何额外解释文字。
2. 严禁引用任何外部 `<script src=...>`、外部 CSS、外部字体或网络图片，必须 100% 离线可运行。
3. **强制使用内联 `<svg viewBox="0 0 720 260">` 渲染核心可视化舞台（禁止使用容易白屏的 `<canvas>`）**：把核心架构节点、连线、标签直接写在 SVG HTML 中，JS 仅用于切换高亮类、驱动动画与更新数值说明。确保页面加载首帧无需等待 JS 就能看到完整清晰的图形，彻底杜绝白屏！
4. **代码精炼（严格控制在 220 行以内）**：结构清晰、变量名简短、零语法错误、所有 `<script>` 标签完整闭合。
5. 视觉风格现代精致（浅色清爽卡片底 `#f8fafc` + 冰蓝强调 `#2463eb` + 柔和圆角阴影），紧凑适配宽 760px、高 480px 的嵌套视口，不出现难看的滚动条。
6. 至少包含 2 个有意义的交互控件（例如：步进播放/重置按钮、参数滑块、模式切换或异常模拟按钮），并在 SVG 画布与底部说明区实时反馈动态变化。
"""

_RUNTIME_GUARD_SCRIPT = (
    "<script>"
    "window.addEventListener('error',function(e){"
    "var b=document.createElement('div');"
    "b.style.cssText='position:fixed;left:12px;right:12px;bottom:12px;z-index:9999;"
    "padding:8px 12px;border-radius:10px;background:#fef2f2;border:1px solid #fecaca;"
    "color:#b91c1c;font:12px/1.4 system-ui,sans-serif;';"
    "b.textContent='沙盒脚本运行异常：'+(e.message||'未知错误')+'（请点击右上角「重新生成沙盒」）';"
    "document.body&&document.body.appendChild(b);"
    "});"
    "</script>"
)


@dataclass(frozen=True)
class SandboxRecord:
    item_id: str
    exists: bool
    html: str | None
    updated_at: str | None


def _sandbox_path(data_dir: Path, item_id: str) -> Path:
    if not _VALID_ITEM_ID.match(item_id):
        raise ValueError(f"非法知识条目 ID: {item_id}")
    root = (data_dir / "sandboxes").resolve()
    root.mkdir(parents=True, exist_ok=True)
    target = (root / f"{item_id}.html").resolve()
    if target.parent != root:
        raise ValueError("非法的沙盒存储路径")
    return target


def extract_and_sanitize_html(raw: str) -> str:
    """从模型输出中提取纯 HTML，并移除任何外链脚本/样式确保离线安全。"""
    text = raw.strip()
    match = _FENCE_RE.search(text)
    if match:
        text = match.group(1).strip()

    # 若模型在 <!doctype html> 前说了多余前缀，裁切到 HTML 起始位置
    lower = text.lower()
    for marker in ("<!doctype html", "<html"):
        idx = lower.find(marker)
        if idx != -1:
            text = text[idx:]
            break

    text = _EXTERNAL_SCRIPT_RE.sub("", text)
    text = _EXTERNAL_LINK_RE.sub("", text)

    if "<html" not in text.lower() and "<body" not in text.lower():
        text = (
            "<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'/>"
            "<style>body{font-family:system-ui,sans-serif;margin:0;padding:16px;"
            "background:#f8fafc;color:#1e293b;}</style></head><body>"
            f"{text}</body></html>"
        )

    lower_cleaned = text.lower()
    open_scripts = len(re.findall(r"<script\b", lower_cleaned))
    close_scripts = len(re.findall(r"</script>", lower_cleaned))
    if open_scripts != close_scripts:
        raise ValueError("模型生成的沙盒代码被截断（<script> 未闭合），请点击「重新生成沙盒」重试。")

    if "<svg" not in lower_cleaned and "<canvas" not in lower_cleaned:
        raise ValueError("模型生成的沙盒缺少可视化画布（<svg>/<canvas>），请点击「重新生成沙盒」重试。")

    # 注入轻量运行时错误兜底提示条，避免极端情况下脚本报错导致静默白屏
    if "沙盒脚本运行异常" not in text:
        head_close = re.search(r"</head>", text, re.IGNORECASE)
        if head_close:
            idx = head_close.start()
            text = text[:idx] + _RUNTIME_GUARD_SCRIPT + text[idx:]
        else:
            text = _RUNTIME_GUARD_SCRIPT + text

    return text.strip()


def get_sandbox(data_dir: Path, item_id: str) -> SandboxRecord:
    path = _sandbox_path(data_dir, item_id)
    if not path.is_file():
        return SandboxRecord(item_id=item_id, exists=False, html=None, updated_at=None)
    stat = path.stat()
    updated = datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat()
    return SandboxRecord(
        item_id=item_id,
        exists=True,
        html=path.read_text(encoding="utf-8"),
        updated_at=updated,
    )


def save_sandbox(data_dir: Path, item_id: str, html: str) -> SandboxRecord:
    cleaned = extract_and_sanitize_html(html)
    path = _sandbox_path(data_dir, item_id)
    path.write_text(cleaned, encoding="utf-8")
    return get_sandbox(data_dir, item_id)


def delete_sandbox(data_dir: Path, item_id: str) -> bool:
    path = _sandbox_path(data_dir, item_id)
    if not path.is_file():
        return False
    path.unlink()
    return True


async def generate_sandbox(
    adapter: ModelAdapter,
    *,
    data_dir: Path,
    item_id: str,
    title: str,
    content: str,
    instruction: str | None = None,
) -> SandboxRecord:
    user_prompt = f"知识标题：{title}\n\n知识内容：\n{content}"
    if instruction and instruction.strip():
        user_prompt += f"\n\n用户额外交互要求：{instruction.strip()}"

    last_err: ValueError | None = None
    for attempt in range(2):
        prompt = user_prompt
        if attempt == 1:
            prompt += (
                "\n\n【重要修正】上一次生成未能通过完整性校验。"
                "本次请务必精简代码到 160 行以内，使用内联 <svg viewBox='0 0 720 260'> 绘制清晰图解，"
                "并确保所有 <script> 与 </html> 完整闭合！"
            )
        response = await adapter.generate(
            ModelRequest(
                messages=[
                    ModelMessage(role="system", content=_SANDBOX_SYSTEM_PROMPT),
                    ModelMessage(role="user", content=prompt),
                ],
                temperature=0.35 if attempt == 0 else 0.2,
                max_tokens=8192,
            )
        )
        try:
            return save_sandbox(data_dir, item_id, response.content)
        except ValueError as exc:
            last_err = exc
    assert last_err is not None
    raise last_err
