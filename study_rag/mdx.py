"""只遮罩 MDX 展示语法；不执行 JSX，保留原始字符与行位置。"""
import re


def blank(text: str) -> str:
    return re.sub(r"[^\n]", " ", text)


def mdx_mask(text: str) -> str:
    chars = list(text)
    protected = [False] * len(text)
    fence, length, offset = "", 0, 0
    for line in text.splitlines(keepends=True):
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line)
        if fence or marker:
            protected[offset:offset + len(line)] = [True] * len(line)
        if marker:
            token, suffix = marker.groups()
            if not fence:
                fence, length = token[0], len(token)
            elif token[0] == fence and len(token) >= length and not suffix.strip():
                fence = ""
        offset += len(line)

    def hide(start, end):
        chars[start:end] = list(blank(text[start:end]))

    # ES module 声明可以跨行；不碰代码示例里的 import/export。
    for match in re.finditer(r"(?m)^\s*(?:import|export)\b", text):
        start = match.start()
        if protected[min(match.end() - 1, len(text) - 1)]:
            continue
        pos, depth, quote, escape = match.end(), 0, "", False
        while pos < len(text):
            char = text[pos]
            if quote:
                if escape:
                    escape = False
                elif char == "\\":
                    escape = True
                elif char == quote:
                    quote = ""
            elif char in "\"'`":
                quote = char
            elif char in "{[(":
                depth += 1
            elif char in "}])":
                depth -= 1
            elif depth == 0 and char in ";\n":
                pos += 1
                break
            pos += 1
        hide(start, pos)

    for match in re.finditer(r"<!--.*?-->|\{/\*.*?\*/\}|<(iframe|script|style|video|audio)\b.*?</\1\s*>", text, re.S | re.I):
        if not protected[match.start()]:
            hide(*match.span())
    # JSX 属性里的字符串、对象和箭头函数可能含 >，必须跟踪引号和花括号。
    for match in re.finditer(r"</?[A-Za-z][\w.:-]*(?=[\s/>])|<>|</>", text):
        if protected[match.start()] or chars[match.start()] == " ":
            continue
        pos, depth, quote, escape = match.end(), 0, "", False
        if match[0] in {"<>", "</>"}:
            hide(*match.span())
            continue
        while pos < len(text):
            char = text[pos]
            if quote:
                if escape:
                    escape = False
                elif char == "\\":
                    escape = True
                elif char == quote:
                    quote = ""
            elif char in "\"'`":
                quote = char
            elif char == "{":
                depth += 1
            elif char == "}":
                depth = max(0, depth - 1)
            elif char == ">" and depth == 0:
                hide(match.start(), pos + 1)
                break
            pos += 1
    for match in re.finditer(r"!\[[^\]]*\]\([^)]*\)", text):
        if not protected[match.start()]:
            hide(*match.span())
    return "".join(chars)
