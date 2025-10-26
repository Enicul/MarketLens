/**
 * Lightweight Markdown renderer supporting headings, lists, emphasis,
 * inline code, blockquotes, links, and paragraphs.
 * HTML input is escaped before formatting.
 */

const HTML_ESCAPE_LOOKUP: Record<string, string> = {
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
  '"': "&quot;",
  "'": "&#39;"
};

function escapeHtml(text: string): string {
  return text.replace(/[&<>"']/g, (char) => HTML_ESCAPE_LOOKUP[char]);
}

function renderInlineFormatting(text: string): string {
  let result = escapeHtml(text);
  result = result.replace(/!\[([^\]]*)]\(([^)]+)\)/g, (_match, alt, src) => {
    return `<img src="${src}" alt="${alt}" />`;
  });
  result = result.replace(/\[([^\]]+)]\(([^)]+)\)/g, (_match, label, href) => {
    return `<a href="${href}" target="_blank" rel="noreferrer">${label}</a>`;
  });
  result = result.replace(/`([^`]+)`/g, (_match, code) => `<code>${code}</code>`);
  result = result.replace(/~~([^~]+)~~/g, (_match, value) => `<del>${value}</del>`);
  result = result.replace(/(\*\*|__)(.*?)\1/g, (_match, _wrapper, value) => `<strong>${value}</strong>`);
  result = result.replace(/(\*|_)(.*?)\1/g, (_match, _wrapper, value) => `<em>${value}</em>`);
  return result;
}

function wrapList(type: "ul" | "ol", items: string[]): string {
  const content = items.map((item) => `<li>${item}</li>`).join("");
  return `<${type}>${content}</${type}>`;
}

export function renderMarkdown(markdown: string): string {
  if (!markdown) return "";

  const lines = markdown.replace(/\r\n?/g, "\n").split("\n");
  const htmlParts: string[] = [];
  let listType: "ul" | "ol" | null = null;
  let listItems: string[] = [];
  let blockquoteBuffer: string[] | null = null;

  const flushList = () => {
    if (listType && listItems.length) {
      htmlParts.push(wrapList(listType, listItems));
    }
    listType = null;
    listItems = [];
  };

  const flushBlockquote = () => {
    if (blockquoteBuffer && blockquoteBuffer.length) {
      const content = blockquoteBuffer.map((line) => `<p>${line}</p>`).join("");
      htmlParts.push(`<blockquote>${content}</blockquote>`);
    }
    blockquoteBuffer = null;
  };

  for (const line of lines) {
    const trimmed = line.trimEnd();

    if (!trimmed.trim()) {
      flushList();
      flushBlockquote();
      htmlParts.push("<br />");
      continue;
    }

    const listMatch = trimmed.match(/^(\*|-|\+)\s+(.*)$/);
    const orderedMatch = trimmed.match(/^(\d+)\.\s+(.*)$/);
    const blockquoteMatch = trimmed.match(/^>\s?(.*)$/);
    const headingMatch = trimmed.match(/^(#{1,6})\s+(.*)$/);

    if (blockquoteMatch) {
      flushList();
      if (!blockquoteBuffer) blockquoteBuffer = [];
      blockquoteBuffer.push(renderInlineFormatting(blockquoteMatch[1]));
      continue;
    }

    flushBlockquote();

    if (headingMatch) {
      flushList();
      const level = headingMatch[1].length;
      const tag = `h${Math.min(level, 6)}`;
      htmlParts.push(`<${tag}>${renderInlineFormatting(headingMatch[2])}</${tag}>`);
      continue;
    }

    if (listMatch) {
      const item = renderInlineFormatting(listMatch[2]);
      if (listType !== "ul") {
        flushList();
        listType = "ul";
      }
      listItems.push(item);
      continue;
    }

    if (orderedMatch) {
      const item = renderInlineFormatting(orderedMatch[2]);
      if (listType !== "ol") {
        flushList();
        listType = "ol";
      }
      listItems.push(item);
      continue;
    }

    flushList();
    htmlParts.push(`<p>${renderInlineFormatting(trimmed)}</p>`);
  }

  flushList();
  flushBlockquote();

  return htmlParts.join("");
}
