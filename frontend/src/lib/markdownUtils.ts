/**
 * 纯 TypeScript Markdown / [[双链]] / #标签 解析工具（无第三方重依赖，无 dangerouslySetInnerHTML）。
 */

export interface WikilinkQuery {
  start: number;
  end: number;
  query: string;
}

export type InlineToken =
  | { type: "text"; value: string }
  | { type: "bold"; value: string }
  | { type: "italic"; value: string }
  | { type: "code"; value: string }
  | { type: "link"; label: string; href: string }
  | { type: "wikilink"; target: string; label: string }
  | { type: "tag"; tag: string };

export type MarkdownBlock =
  | { type: "heading"; level: 1 | 2 | 3 | 4; text: string }
  | { type: "code"; lang: string; code: string }
  | { type: "blockquote"; lines: string[] }
  | { type: "ul"; items: { text: string; checked?: boolean }[] }
  | { type: "ol"; items: string[] }
  | { type: "table"; headers: string[]; rows: string[][] }
  | { type: "hr" }
  | { type: "paragraph"; text: string };

/** 提取正文中的 #标签（忽略代码块与标题 # ）。支持中英文、数字、斜杠层级标签。 */
export function extractTags(content: string): string[] {
  const withoutCode = content.replace(/```[\s\S]*?```/g, "").replace(/`[^`]*`/g, "");
  const found = new Set<string>();
  const re = /(?:^|[\s(（[【,，;；])#([\p{L}\p{N}_\-/]{1,32})/gu;
  let m: RegExpExecArray | null;
  while ((m = re.exec(withoutCode)) !== null) {
    const tag = m[1].replace(/^\/+|\/+$/g, "");
    if (tag && !/^\d+$/.test(tag)) {
      found.add(tag);
    }
  }
  return [...found];
}

/** 提取正文中的 [[双链]] 目标标题列表。 */
export function extractWikilinks(content: string): string[] {
  const withoutCode = content.replace(/```[\s\S]*?```/g, "").replace(/`[^`]*`/g, "");
  const found = new Set<string>();
  const re = /\[\[([^[\]|#\n]+)(?:\|[^[\]\n]+)?\]\]/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(withoutCode)) !== null) {
    const target = m[1].trim();
    if (target) found.add(target);
  }
  return [...found];
}

/** 检测光标位置是否正处于未闭合的 [[双链 补全输入中。 */
export function getActiveWikilinkQuery(
  text: string,
  cursorPos: number,
): WikilinkQuery | null {
  const before = text.slice(0, cursorPos);
  const openIdx = before.lastIndexOf("[[");
  if (openIdx === -1) return null;
  const fragment = before.slice(openIdx + 2);
  if (fragment.includes("]]") || fragment.includes("\n")) return null;
  return {
    start: openIdx,
    end: cursorPos,
    query: fragment.trim(),
  };
}

/** 解析行内 Markdown 语法：行内代码、[[双链]]、外部链接、加粗、斜体、#标签。 */
export function parseInlineTokens(text: string): InlineToken[] {
  const tokens: InlineToken[] = [];
  const pattern =
    /(`[^`\n]+`)|(\[\[([^[\]|#\n]+)(?:\|([^[\]\n]+))?\]\])|(\[([^\]]+)\]\((https?:\/\/[^\s)]+)\))|(\*\*([^*\n]+)\*\*)|(\*([^*\n]+)\*)|((?:^|(?<=[\s(（[【,，;；]))#([\p{L}\p{N}_\-/]{1,32}))/gu;

  let lastIndex = 0;
  let m: RegExpExecArray | null;
  while ((m = pattern.exec(text)) !== null) {
    if (m.index > lastIndex) {
      tokens.push({ type: "text", value: text.slice(lastIndex, m.index) });
    }
    if (m[1]) {
      tokens.push({ type: "code", value: m[1].slice(1, -1) });
    } else if (m[2]) {
      const target = m[3].trim();
      const label = (m[4] ?? m[3]).trim();
      tokens.push({ type: "wikilink", target, label });
    } else if (m[5]) {
      tokens.push({ type: "link", label: m[6], href: m[7] });
    } else if (m[8]) {
      tokens.push({ type: "bold", value: m[9] });
    } else if (m[10]) {
      tokens.push({ type: "italic", value: m[11] });
    } else if (m[12]) {
      const tag = m[13].replace(/^\/+|\/+$/g, "");
      if (tag && !/^\d+$/.test(tag)) {
        tokens.push({ type: "tag", tag });
      } else {
        tokens.push({ type: "text", value: m[12] });
      }
    }
    lastIndex = pattern.lastIndex;
  }

  if (lastIndex < text.length) {
    tokens.push({ type: "text", value: text.slice(lastIndex) });
  }
  return tokens;
}

function splitTableRow(line: string): string[] {
  const trimmed = line.trim().replace(/^\|/, "").replace(/\|$/, "");
  return trimmed.split("|").map((cell) => cell.trim());
}

function isTableSeparator(line: string): boolean {
  return /^\s*\|?(\s*:?-{3,}:?\s*\|)+\s*:?-{3,}:?\s*\|?\s*$/.test(line);
}

/** 将 Markdown 文本解析为结构化块列表。 */
export function parseMarkdownBlocks(content: string): MarkdownBlock[] {
  const lines = content.replace(/\r\n/g, "\n").split("\n");
  const blocks: MarkdownBlock[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];
    const trimmed = line.trim();

    if (!trimmed) {
      i += 1;
      continue;
    }

    // 围栏代码块
    const fenceMatch = /^```(\w*)\s*$/.exec(trimmed);
    if (fenceMatch) {
      const lang = fenceMatch[1] || "";
      const codeLines: string[] = [];
      i += 1;
      while (i < lines.length && !/^```\s*$/.test(lines[i].trim())) {
        codeLines.push(lines[i]);
        i += 1;
      }
      if (i < lines.length) i += 1;
      blocks.push({ type: "code", lang, code: codeLines.join("\n") });
      continue;
    }

    // 标题
    const headingMatch = /^(#{1,4})\s+(.+)$/.exec(trimmed);
    if (headingMatch) {
      blocks.push({
        type: "heading",
        level: headingMatch[1].length as 1 | 2 | 3 | 4,
        text: headingMatch[2].trim(),
      });
      i += 1;
      continue;
    }

    // 分割线
    if (/^(-{3,}|\*{3,}|_{3,})$/.test(trimmed)) {
      blocks.push({ type: "hr" });
      i += 1;
      continue;
    }

    // 表格
    if (
      trimmed.includes("|") &&
      i + 1 < lines.length &&
      isTableSeparator(lines[i + 1])
    ) {
      const headers = splitTableRow(line);
      i += 2;
      const rows: string[][] = [];
      while (i < lines.length && lines[i].trim().includes("|")) {
        rows.push(splitTableRow(lines[i]));
        i += 1;
      }
      blocks.push({ type: "table", headers, rows });
      continue;
    }

    // 引用块
    if (/^>\s?/.test(trimmed)) {
      const quoteLines: string[] = [];
      while (i < lines.length && /^>\s?/.test(lines[i].trim())) {
        quoteLines.push(lines[i].trim().replace(/^>\s?/, ""));
        i += 1;
      }
      blocks.push({ type: "blockquote", lines: quoteLines });
      continue;
    }

    // 无序列表 / 任务列表
    if (/^[-*+]\s+/.test(trimmed)) {
      const items: { text: string; checked?: boolean }[] = [];
      while (i < lines.length && /^[-*+]\s+/.test(lines[i].trim())) {
        const raw = lines[i].trim().replace(/^[-*+]\s+/, "");
        const task = /^\[([ xX])\]\s+(.*)$/.exec(raw);
        if (task) {
          items.push({ text: task[2], checked: task[1].toLowerCase() === "x" });
        } else {
          items.push({ text: raw });
        }
        i += 1;
      }
      blocks.push({ type: "ul", items });
      continue;
    }

    // 有序列表
    if (/^\d+\.\s+/.test(trimmed)) {
      const items: string[] = [];
      while (i < lines.length && /^\d+\.\s+/.test(lines[i].trim())) {
        items.push(lines[i].trim().replace(/^\d+\.\s+/, ""));
        i += 1;
      }
      blocks.push({ type: "ol", items });
      continue;
    }

    // 普通段落（合并连续普通文本行）
    const paraLines: string[] = [];
    while (
      i < lines.length &&
      lines[i].trim() &&
      !/^(```|#{1,4}\s+|>\s?|[-*+]\s+|\d+\.\s+|(-{3,}|\*{3,}|_{3,})$)/.test(
        lines[i].trim(),
      )
    ) {
      paraLines.push(lines[i]);
      i += 1;
    }
    blocks.push({ type: "paragraph", text: paraLines.join("\n") });
  }

  return blocks;
}
