import { describe, expect, it } from "vitest";

import {
  extractTags,
  extractWikilinks,
  getActiveWikilinkQuery,
  parseInlineTokens,
  parseMarkdownBlocks,
} from "./markdownUtils";

describe("markdownUtils", () => {
  it("extracts hashtags while ignoring headings and code blocks", () => {
    const md = [
      "## 标题不是标签",
      "正文包含 #架构 与 #AI/Agent 以及 `code #ignored`",
      "```python",
      "# comment_not_tag",
      "```",
    ].join("\n");
    expect(extractTags(md)).toEqual(["架构", "AI/Agent"]);
  });

  it("extracts wikilinks with optional aliases", () => {
    const md = "参考 [[知识图谱]] 以及 [[MCP 方案|MCP 接入]] 和 `[[code]]`";
    expect(extractWikilinks(md)).toEqual(["知识图谱", "MCP 方案"]);
  });

  it("detects active wikilink autocomplete query at cursor", () => {
    expect(getActiveWikilinkQuery("请看 [[知识", 7)).toEqual({
      start: 3,
      end: 7,
      query: "知识",
    });
    expect(getActiveWikilinkQuery("已经闭合 [[知识]] 后面", 13)).toBeNull();
  });

  it("parses headings, code blocks, lists, tables, and inline tokens", () => {
    const md = [
      "## 小节",
      "- [x] 完成项",
      "- 普通项 **加粗** [[目标]] #效率",
      "```ts",
      "const x = 1;",
      "```",
      "| 列1 | 列2 |",
      "| --- | --- |",
      "| A | B |",
    ].join("\n");
    const blocks = parseMarkdownBlocks(md);
    expect(blocks.map((b) => b.type)).toEqual(["heading", "ul", "code", "table"]);
    const inline = parseInlineTokens("看 **重点** [[目标|别名]] #效率");
    expect(inline.some((t) => t.type === "bold" && t.value === "重点")).toBe(true);
    expect(inline.some((t) => t.type === "wikilink" && t.target === "目标")).toBe(true);
    expect(inline.some((t) => t.type === "tag" && t.tag === "效率")).toBe(true);
  });
});
