"""Markdown rendering for case studies: no raw HTML, Pygments highlighting, heading anchors."""

import re

from markdown_it import MarkdownIt
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import TextLexer, get_lexer_by_name
from pygments.util import ClassNotFound

from app.content.models import TocItem
from app.core.text import slugify

_LANG = re.compile(r"^[A-Za-z0-9_+#.-]{1,24}$")
_FORMATTER = HtmlFormatter(nowrap=True)


def _highlight(code: str, lang: str, _attrs: str) -> str:
    safe_lang = lang if _LANG.match(lang or "") else ""
    try:
        lexer = get_lexer_by_name(safe_lang) if safe_lang else TextLexer()
    except ClassNotFound:
        lexer = TextLexer()
    body = highlight(code, lexer, _FORMATTER)
    css_class = f' class="language-{safe_lang}"' if safe_lang else ""
    return f'<pre class="highlight"><code{css_class}>{body}</code></pre>'


_MARKDOWN = MarkdownIt("commonmark", {"html": False, "highlight": _highlight}).enable(
    ["table", "strikethrough"]
)


def render_markdown(text: str) -> tuple[str, tuple[TocItem, ...]]:
    """Render Markdown to HTML and collect the h2/h3 outline."""
    tokens = _MARKDOWN.parse(text)
    toc: list[TocItem] = []
    used: set[str] = set()
    for index, token in enumerate(tokens):
        if token.type == "heading_open" and token.tag in {"h2", "h3"}:
            heading = tokens[index + 1].content
            anchor = base = slugify(heading)
            counter = 2
            while anchor in used:
                anchor = f"{base}-{counter}"
                counter += 1
            used.add(anchor)
            token.attrSet("id", anchor)
            toc.append(TocItem(level=int(token.tag[1]), id=anchor, text=heading))
    return _MARKDOWN.renderer.render(tokens, _MARKDOWN.options, {}), tuple(toc)
