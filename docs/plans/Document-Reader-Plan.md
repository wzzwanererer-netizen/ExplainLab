# ExplainLab · 内置多格式文档阅读器规划（Word / Excel / PPT / PDF）

> 制定日期：2026-11-27  
> 设计原则：**零重型第三方依赖**（不捆绑数百 MB 的 LibreOffice，保持桌面端轻快离线）、**与 Nesti Fluent 浅/深主题原生融合**、**点击附件原位即看**。

---

## 一、支持格式与阅读器形态

| 格式 | 阅读器形态与交互能力 | 底层解析方案（纯 Python 标准库 + 原生引擎） |
| :--- | :--- | :--- |
| **PDF (`.pdf`)** | **内嵌原位 PDF 阅读器**（缩放、翻页、目录、文本复制、打印） | 直接复用 Electron/Chromium 原生 PDF 渲染器 + 已有 HTTP `Range` (206) 流式传输，大 PDF 秒开 |
| **Word (`.docx`)** | **结构化富文档阅读器**（标题层级、段落、列表、**完整表格**、文档内嵌图片点击放大） | 纯 Python `zipfile` + `xml.etree.ElementTree` 解析 `word/document.xml` 与图片关系表 `word/_rels/`，零新增依赖 |
| **Excel / CSV (`.xlsx` / `.csv`)** | **交互式电子表格阅读器**（多 Sheet 标签页切换、表头吸顶、页内关键词筛选高亮、行列统计） | 纯 Python `zipfile` + `ET` 解析 `xl/workbook.xml`、`sharedStrings.xml` 与 `sheet*.xml`；CSV 自动兼容 UTF-8 / GBK 中文编码 |
| **PowerPoint (`.pptx`)** | **幻灯片翻页演示阅读器**（上一页/下一页、键盘 `←/→` 翻页、底部页码条、每页标题/要点/表格/内嵌图 + 演讲者备注） | 纯 Python `zipfile` + `ET` 解析 `ppt/slides/slide*.xml`、`notesSlides/` 与 `ppt/media/` |

---

## 二、后端接口与存储设计

1. **细化媒体分类**（[media.py](file:///d:/ExplainLab/backend/app/services/media.py)）：
   - 将 `kind` 从 `image / audio / video / pdf / file` 扩展为：`image | audio | video | pdf | word | excel | ppt | file`。
2. **新增文档结构化预览服务**（`backend/app/services/doc_preview.py`）：
   - `parse_document_preview(path, kind)` 返回统一 JSON DTO：
     - `pdf` → `{ kind: "pdf", stream_url }`
     - `word` → `{ kind: "word", blocks: [{ type: "heading" | "paragraph" | "table" | "image", ... }] }`（文档内嵌图片按需提取并缓存至本地媒体仓，返回 `/api/agents/media/...`）
     - `excel` → `{ kind: "excel", sheets: [{ name, rows: string[][], total_rows, truncated }] }`（单 Sheet 默认安全预览前 500 行，防止十万行大表卡顿浏览器）
     - `ppt` → `{ kind: "ppt", slides: [{ index, title, texts, tables, notes, images }] }`
3. **新增只读预览路由**（[media.py](file:///d:/ExplainLab/backend/app/api/routes/media.py)）：
   - `GET /api/knowledge/{item_id}/media/{media_id}/preview`
4. **联动乱文件夹哨兵**（[folder_watcher.py](file:///d:/ExplainLab/backend/app/services/folder_watcher.py)）：
   - 文件夹哨兵新增支持 `.xlsx / .pptx`，并将收编到的 `.docx / .xlsx / .pptx / .pdf` 同步挂载到对应知识卡片的附件库，实现「文件夹收编 → 卡片内直接阅读」闭环。

---

## 三、前端交互设计

1. **统一大屏阅读器组件 `DocumentReaderModal.tsx`**：
   - 支持全屏切换、`Esc` 关闭、浅色/深色主题跟随；
   - **Word 视图**：干净的文档纸张排版（标题/正文/清晰网格表格/内嵌图灯箱）；
   - **Excel 视图**：顶部多 Sheet 标签页 + 表格搜索框 + 吸顶表头 + 横向滚动；
   - **PPT 视图**：16:9 幻灯片卡片舞台 + 键盘 `←/→` 翻页 + 演讲者备注折叠区；
   - **PDF 视图**：自适应 `<iframe src={media.url} />` 原生阅读；
   - 顶部工具条保留 **`下载原文件`** 按钮作为复杂排版兜底。
2. **无缝接入 `MediaAttachmentsPanel.tsx`**：
   - 凡是 `pdf / word / excel / ppt` 附件，卡片右侧直接显示醒目的 **`原位阅读`** 主按钮（点击即开阅读器）。

---

## 四、诚实边界
- 纯 XML 结构化解析专注「**清晰读懂内容、表格、数据与图片**」，速度快、体积零膨胀、完全离线；
- 极少数老式二进制 `.doc / .xls / .ppt`（Office 97-2003 格式）或复杂艺术字/动画特效无法纯 XML 还原，阅读器会给出友好提示并提供一键下载/本机打开入口。
