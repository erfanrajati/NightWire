"use strict";

const LANGUAGE_ALIASES = new Map([
  ["js", "javascript"], ["jsx", "javascript"], ["ts", "typescript"], ["tsx", "typescript"],
  ["py", "python"], ["rb", "ruby"], ["sh", "shell"], ["bash", "shell"],
  ["yml", "yaml"], ["md", "markdown"], ["html", "html"], ["xml", "xml"],
]);

const KEYWORDS = {
  javascript: new Set("async await break case catch class const continue default delete do else export extends finally for from function if import in instanceof let new of return static super switch this throw try typeof var void while with yield true false null undefined".split(" ")),
  typescript: new Set("abstract any as async await boolean break case catch class const constructor continue declare default delete do else enum export extends false finally for from function if implements import in infer instanceof interface is keyof let module namespace never new null number object of private protected public readonly return static string super switch symbol this throw true try type typeof undefined unknown var void while with yield".split(" ")),
  python: new Set("and as assert async await break class continue def del elif else except False finally for from global if import in is lambda None nonlocal not or pass raise return True try while with yield".split(" ")),
  ruby: new Set("alias and begin break case class def defined do else elsif end ensure false for if in module next nil not or redo rescue retry return self super then true undef unless until when while yield".split(" ")),
  shell: new Set("case do done elif else esac fi for function if in then until while".split(" ")),
  css: new Set("color background display position margin padding width height grid flex font border content media supports import important".split(" ")),
  sql: new Set("select from where join left right inner outer on group by order having limit offset insert update delete into values create alter drop table index distinct union all as and or not null is".split(" ")),
};

export function normalizeLanguage(value) {
  const language = String(value || "").trim().toLowerCase();
  return LANGUAGE_ALIASES.get(language) || language;
}

export function detectLanguage(source) {
  const value = String(source || "");
  if (/^\s*<(!doctype\s+html|html|[a-z][\w-]*[\s>])/i.test(value)) return "html";
  if (/^\s*(from\s+\w+\s+import|import\s+\w+|def\s+\w+\s*\(|class\s+\w+.*:)/m.test(value)) return "python";
  if (/\b(interface|type)\s+\w+\s*[={]|:\s*(string|number|boolean)\b/.test(value)) return "typescript";
  if (/\b(const|let|var|function)\s+\w+|=>|console\.(log|error)\s*\(/.test(value)) return "javascript";
  if (/^\s*(SELECT|INSERT|UPDATE|DELETE|CREATE)\b[\s\S]*\b(FROM|INTO|TABLE|SET)\b/im.test(value)) return "sql";
  if (/^\s*[.#]?[\w-]+\s*\{[\s\S]*[\w-]+\s*:/m.test(value)) return "css";
  if (/^\s*(#!.*\b(sh|bash)|(?:export\s+)?[A-Z_][A-Z0-9_]*=)/m.test(value)) return "shell";
  if (/^\s*[\w.-]+:\s+\S/m.test(value)) return "yaml";
  return "plain";
}

function appendInline(parent, source) {
  const pattern = /(!?\[[^\]\n]*\]\([^\s)]+(?:\s+"[^"]*")?\)|`[^`\n]+`|\*\*[^*\n]+\*\*|__[^_\n]+__|\*[^*\n]+\*|_[^_\n]+_)/g;
  let cursor = 0;
  for (const match of source.matchAll(pattern)) {
    parent.append(document.createTextNode(source.slice(cursor, match.index)));
    const token = match[0];
    if (token.startsWith("![")) {
      const label = token.slice(2, token.indexOf("]("));
      const omitted = document.createElement("span");
      omitted.className = "text-remote-omitted";
      omitted.textContent = `[Remote image omitted${label ? `: ${label}` : ""}]`;
      parent.append(omitted);
    } else if (token.startsWith("[")) {
      const divider = token.indexOf("](");
      const label = token.slice(1, divider);
      const rawTarget = token.slice(divider + 2, -1).replace(/\s+"[^"]*"$/, "");
      let target = null;
      try {
        const parsed = new URL(rawTarget, window.location.origin);
        if (["http:", "https:", "mailto:"].includes(parsed.protocol)) target = parsed.href;
      } catch (_) {}
      if (target) {
        const link = document.createElement("a");
        link.href = target; link.textContent = label; link.rel = "noopener noreferrer nofollow";
        if (!target.startsWith(`${window.location.origin}/`)) link.target = "_blank";
        parent.append(link);
      } else {
        parent.append(document.createTextNode(label));
      }
    } else if (token.startsWith("`")) {
      const code = document.createElement("code"); code.textContent = token.slice(1, -1); parent.append(code);
    } else {
      const strong = token.startsWith("**") || token.startsWith("__");
      const element = document.createElement(strong ? "strong" : "em");
      element.textContent = token.slice(strong ? 2 : 1, strong ? -2 : -1); parent.append(element);
    }
    cursor = match.index + token.length;
  }
  parent.append(document.createTextNode(source.slice(cursor)));
}

export function renderMarkdown(container, source) {
  const fragment = document.createDocumentFragment();
  const lines = String(source || "").replace(/\r\n?/g, "\n").split("\n");
  let list = null, listType = null, code = null;
  const endList = () => { list = null; listType = null; };
  for (const line of lines) {
    if (code) {
      if (/^\s*```/.test(line)) { fragment.append(code.wrapper); code = null; }
      else code.body.append(document.createTextNode(`${code.body.childNodes.length ? "\n" : ""}${line}`));
      continue;
    }
    const fence = line.match(/^\s*```\s*([\w+.#-]*)\s*$/);
    if (fence) {
      endList();
      const wrapper = document.createElement("pre"), body = document.createElement("code");
      const language = normalizeLanguage(fence[1]);
      if (language) body.dataset.language = language;
      wrapper.append(body); code = { wrapper, body }; continue;
    }
    const heading = line.match(/^(#{1,6})\s+(.+)$/);
    if (heading) {
      endList(); const node = document.createElement(`h${heading[1].length}`); appendInline(node, heading[2]); fragment.append(node); continue;
    }
    if (/^\s*(?:---+|\*\*\*+)\s*$/.test(line)) { endList(); fragment.append(document.createElement("hr")); continue; }
    const quote = line.match(/^>\s?(.*)$/);
    if (quote) { endList(); const node = document.createElement("blockquote"); appendInline(node, quote[1]); fragment.append(node); continue; }
    const listItem = line.match(/^\s*(?:([-+*])|(\d+)\.)\s+(.+)$/);
    if (listItem) {
      const type = listItem[2] ? "ol" : "ul";
      if (!list || listType !== type) { list = document.createElement(type); listType = type; fragment.append(list); }
      const item = document.createElement("li"); appendInline(item, listItem[3]); list.append(item); continue;
    }
    endList();
    if (!line.trim()) { fragment.append(document.createElement("br")); continue; }
    const paragraph = document.createElement("p"); appendInline(paragraph, line); fragment.append(paragraph);
  }
  if (code) fragment.append(code.wrapper);
  container.replaceChildren(fragment);
}

function highlightedLine(source, language) {
  const fragment = document.createDocumentFragment();
  const keywords = KEYWORDS[normalizeLanguage(language)] || new Set();
  const tokenPattern = /(\/\/.*$|#.*$|--.*$|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|\b\d+(?:\.\d+)?\b|\b[A-Za-z_$][\w$]*\b)/gm;
  let cursor = 0;
  for (const match of source.matchAll(tokenPattern)) {
    fragment.append(document.createTextNode(source.slice(cursor, match.index)));
    const token = match[0], span = document.createElement("span");
    if (/^(\/\/|#|--)/.test(token)) span.className = "tok-comment";
    else if (/^["']/.test(token)) span.className = "tok-string";
    else if (/^\d/.test(token)) span.className = "tok-number";
    else if (keywords.has(token) || keywords.has(token.toLowerCase())) span.className = "tok-keyword";
    span.textContent = token; fragment.append(span); cursor = match.index + token.length;
  }
  fragment.append(document.createTextNode(source.slice(cursor)));
  return fragment;
}

export function renderCode(container, source, language, { lineNumbers = true } = {}) {
  const detected = normalizeLanguage(language) || detectLanguage(source);
  const pre = document.createElement("pre"); pre.className = "text-code-block"; pre.dataset.language = detected;
  const code = document.createElement("code");
  String(source || "").replace(/\r\n?/g, "\n").split("\n").forEach((line, index) => {
    const row = document.createElement("span"); row.className = "text-code-line";
    if (lineNumbers) { const number = document.createElement("span"); number.className = "text-line-number"; number.textContent = String(index + 1); row.append(number); }
    const value = document.createElement("span"); value.className = "text-code-value"; value.append(highlightedLine(line, detected)); row.append(value); code.append(row);
  });
  pre.append(code); container.replaceChildren(pre); return detected;
}

export function renderText(container, text, options = {}) {
  const mode = text?.mode || "plain", content = text?.content || "";
  container.className = `text-rendered text-rendered-${mode}`;
  if (mode === "markdown") { renderMarkdown(container, content); return "markdown"; }
  if (mode === "code") return renderCode(container, content, text?.language, options);
  const pre = document.createElement("pre"); pre.className = "text-plain-block"; pre.textContent = content; container.replaceChildren(pre); return "plain";
}
