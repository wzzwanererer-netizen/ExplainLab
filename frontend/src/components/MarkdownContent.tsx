import { Fragment, useState } from "react";

import {
  parseInlineTokens,
  parseMarkdownBlocks,
  type InlineToken,
} from "../lib/markdownUtils";

export interface MarkdownContentProps {
  content: string;
  onWikilinkClick?: (targetTitle: string) => void;
  onTagClick?: (tag: string) => void;
}

function renderInline(
  text: string,
  onWikilinkClick?: (targetTitle: string) => void,
  onTagClick?: (tag: string) => void,
  onImageClick?: (src: string, alt: string) => void,
) {
  const lines = text.split("\n");
  return lines.map((line, lineIdx) => {
    const tokens: InlineToken[] = parseInlineTokens(line);
    return (
      <Fragment key={lineIdx}>
        {lineIdx > 0 && <br />}
        {tokens.map((tok, idx) => {
          switch (tok.type) {
            case "bold":
              return (
                <strong
                  key={idx}
                  className="font-semibold"
                  style={{ color: "var(--nesti-text-primary)" }}
                >
                  {tok.value}
                </strong>
              );
            case "italic":
              return (
                <em key={idx} className="italic">
                  {tok.value}
                </em>
              );
            case "code":
              return (
                <code
                  key={idx}
                  className="rounded px-1.5 py-0.5 font-mono text-[12px]"
                  style={{
                    background: "var(--nesti-surface-2)",
                    color: "var(--nesti-accent)",
                  }}
                >
                  {tok.value}
                </code>
              );
            case "image":
              return (
                <img
                  key={idx}
                  src={tok.src}
                  alt={tok.alt || "知识插图"}
                  loading="lazy"
                  onClick={() => onImageClick?.(tok.src, tok.alt)}
                  className="my-1.5 block max-h-60 cursor-zoom-in rounded-xl border object-contain shadow-xs transition-transform hover:scale-[1.01]"
                  style={{ borderColor: "var(--nesti-border-subtle)" }}
                />
              );
            case "link":
              return (
                <a
                  key={idx}
                  href={tok.href}
                  target="_blank"
                  rel="noreferrer"
                  className="underline decoration-dotted underline-offset-2 hover:opacity-80"
                  style={{ color: "var(--nesti-accent)" }}
                >
                  {tok.label}
                </a>
              );
            case "wikilink":
              return (
                <button
                  key={idx}
                  type="button"
                  onClick={() => onWikilinkClick?.(tok.target)}
                  title={`跳转到知识：${tok.target}`}
                  className="mx-0.5 inline-flex items-center rounded px-1.5 py-0.5 text-[12px] font-medium transition-colors hover:opacity-85"
                  style={{
                    background: "color-mix(in srgb, var(--nesti-accent) 14%, transparent)",
                    color: "var(--nesti-accent)",
                  }}
                >
                  [[{tok.label}]]
                </button>
              );
            case "tag":
              return (
                <button
                  key={idx}
                  type="button"
                  onClick={() => onTagClick?.(tok.tag)}
                  title={`按标签 #${tok.tag} 筛选`}
                  className="mx-0.5 inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium transition-colors hover:opacity-85"
                  style={{
                    background: "var(--nesti-surface-2)",
                    color: "var(--nesti-text-secondary)",
                  }}
                >
                  #{tok.tag}
                </button>
              );
            default:
              return <Fragment key={idx}>{tok.value}</Fragment>;
          }
        })}
      </Fragment>
    );
  });
}

/**
 * Nesti Fluent Markdown 富文本渲染器：
 * 支持标题、列表/任务列表、代码块、引用块、表格、可点击 [[双链]] 与 #标签。
 */
export function MarkdownContent({
  content,
  onWikilinkClick,
  onTagClick,
}: MarkdownContentProps) {
  const blocks = parseMarkdownBlocks(content);
  const [lightbox, setLightbox] = useState<{ src: string; alt: string } | null>(null);
  const openLightbox = (src: string, alt: string) => setLightbox({ src, alt });
  const inline = (txt: string) =>
    renderInline(txt, onWikilinkClick, onTagClick, openLightbox);

  return (
    <div
      className="space-y-2 text-sm leading-relaxed"
      style={{ color: "var(--nesti-text-secondary)" }}
    >
      {blocks.map((block, idx) => {
        switch (block.type) {
          case "heading": {
            const cls =
              block.level === 1
                ? "text-base font-bold pt-1"
                : block.level === 2
                  ? "text-sm font-semibold pt-1"
                  : "text-xs font-semibold uppercase tracking-wide pt-0.5";
            return (
              <div
                key={idx}
                className={cls}
                style={{ color: "var(--nesti-text-primary)" }}
              >
                {inline(block.text)}
              </div>
            );
          }
          case "code":
            return (
              <div
                key={idx}
                className="overflow-x-auto rounded-lg border"
                style={{
                  background: "var(--nesti-surface-0)",
                  borderColor: "var(--nesti-border-subtle)",
                }}
              >
                {block.lang && (
                  <div
                    className="border-b px-3 py-1 font-mono text-[10px] uppercase tracking-wider"
                    style={{
                      borderColor: "var(--nesti-border-subtle)",
                      color: "var(--nesti-text-tertiary)",
                    }}
                  >
                    {block.lang}
                  </div>
                )}
                <pre className="p-3 font-mono text-xs leading-relaxed">
                  <code>{block.code}</code>
                </pre>
              </div>
            );
          case "blockquote":
            return (
              <blockquote
                key={idx}
                className="border-l-2 pl-3 italic"
                style={{
                  borderColor: "var(--nesti-accent)",
                  color: "var(--nesti-text-tertiary)",
                }}
              >
                {block.lines.map((l, li) => (
                  <p key={li}>{inline(l)}</p>
                ))}
              </blockquote>
            );
          case "ul":
            return (
              <ul key={idx} className="space-y-1 pl-4 list-disc">
                {block.items.map((item, ii) => (
                  <li key={ii} className={item.checked !== undefined ? "list-none -ml-4 flex items-start gap-2" : ""}>
                    {item.checked !== undefined && (
                      <input
                        type="checkbox"
                        checked={item.checked}
                        readOnly
                        className="mt-1 h-3.5 w-3.5 accent-[var(--nesti-accent)]"
                      />
                    )}
                    <span className={item.checked ? "line-through opacity-70" : ""}>
                      {inline(item.text)}
                    </span>
                  </li>
                ))}
              </ul>
            );
          case "ol":
            return (
              <ol key={idx} className="space-y-1 pl-5 list-decimal">
                {block.items.map((item, ii) => (
                  <li key={ii}>{inline(item)}</li>
                ))}
              </ol>
            );
          case "table":
            return (
              <div
                key={idx}
                className="overflow-x-auto rounded-lg border"
                style={{ borderColor: "var(--nesti-border-subtle)" }}
              >
                <table className="w-full border-collapse text-left text-xs">
                  <thead>
                    <tr style={{ background: "var(--nesti-surface-2)" }}>
                      {block.headers.map((h, hi) => (
                        <th
                          key={hi}
                          className="border-b px-2.5 py-1.5 font-semibold"
                          style={{
                            borderColor: "var(--nesti-border-subtle)",
                            color: "var(--nesti-text-primary)",
                          }}
                        >
                          {inline(h)}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {block.rows.map((row, ri) => (
                      <tr
                        key={ri}
                        className="border-b last:border-b-0"
                        style={{ borderColor: "var(--nesti-border-subtle)" }}
                      >
                        {row.map((cell, ci) => (
                          <td key={ci} className="px-2.5 py-1.5">
                            {inline(cell)}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            );
          case "image":
            return (
              <figure key={idx} className="my-2">
                <img
                  src={block.src}
                  alt={block.alt || "知识插图"}
                  loading="lazy"
                  onClick={() => setLightbox({ src: block.src, alt: block.alt })}
                  className="max-h-72 cursor-zoom-in rounded-xl border object-contain shadow-xs transition-transform hover:scale-[1.01]"
                  style={{ borderColor: "var(--nesti-border-subtle)" }}
                />
                {block.alt && (
                  <figcaption
                    className="mt-1 text-[11px]"
                    style={{ color: "var(--nesti-text-tertiary)" }}
                  >
                    {block.alt}
                  </figcaption>
                )}
              </figure>
            );
          case "mediaCard":
            return (
              <div
                key={idx}
                className="my-2.5 flex flex-col gap-3 rounded-xl border p-3 sm:flex-row sm:items-start"
                style={{
                  background: "var(--nesti-surface-0)",
                  borderColor: "var(--nesti-border-subtle)",
                }}
              >
                <img
                  src={block.src}
                  alt={block.alt || block.title}
                  loading="lazy"
                  onClick={() => setLightbox({ src: block.src, alt: block.alt || block.title })}
                  className="h-24 w-32 shrink-0 cursor-zoom-in rounded-lg border object-cover shadow-xs transition-transform hover:scale-[1.02]"
                  style={{ borderColor: "var(--nesti-border-subtle)" }}
                />
                <div className="min-w-0 flex-1 space-y-1.5">
                  <div
                    className="text-sm font-semibold"
                    style={{ color: "var(--nesti-text-primary)" }}
                  >
                    {inline(block.title)}
                  </div>
                  <ul className="list-disc space-y-0.5 pl-4 text-xs">
                    {block.bullets.map((b, bi) => (
                      <li key={bi}>{inline(b)}</li>
                    ))}
                  </ul>
                  {block.note && (
                    <p
                      className="pt-0.5 text-[11px]"
                      style={{ color: "var(--nesti-text-tertiary)" }}
                    >
                      {inline(block.note)}
                    </p>
                  )}
                </div>
              </div>
            );
          case "hr":
            return (
              <hr
                key={idx}
                className="my-2 border-t"
                style={{ borderColor: "var(--nesti-border-subtle)" }}
              />
            );
          default:
            return (
              <p key={idx} className="whitespace-pre-wrap">
                {inline(block.text)}
              </p>
            );
        }
      })}
      {lightbox && (
        <div
          role="dialog"
          aria-modal="true"
          className="fixed inset-0 z-[80] flex items-center justify-center bg-black/75 p-6 backdrop-blur-xs"
          onClick={() => setLightbox(null)}
        >
          <img
            src={lightbox.src}
            alt={lightbox.alt}
            className="max-h-[88vh] max-w-[90vw] rounded-xl object-contain shadow-2xl"
          />
        </div>
      )}
    </div>
  );
}
