from __future__ import annotations

import pytest

from turbohtml import Markdown, parse


@pytest.mark.parametrize(
    ("source", "language", "content"),
    [
        pytest.param(
            '<pre><code class="highlight language-python">one</code></pre>', "python", "one", id="second-class"
        ),
        pytest.param('<pre><code class=" language-python">one</code></pre>', "python", "one", id="leading-space"),
        pytest.param(
            '<pre><code class="highlight&#9;&#10;&#12;&#13;language-python other">one</code></pre>',
            "python",
            "one",
            id="ascii-whitespace",
        ),
        pytest.param(
            '<pre><code class="language- language-python">one</code></pre>', "python", "one", id="empty-token"
        ),
        pytest.param(
            '<pre><code class="language-python language-ruby">one</code></pre>', "python", "one", id="first-language"
        ),
        pytest.param(
            '<pre><code class="highlight\u00a0language-python">one</code></pre>',
            "fallback",
            "one",
            id="nbsp-is-not-separator",
        ),
        pytest.param('<pre><code class="LANGUAGE-python">one</code></pre>', "fallback", "one", id="case-sensitive"),
        pytest.param('<pre class="language-ruby">one</pre>', "ruby", "one", id="pre-language"),
        pytest.param('<pre class="language-ruby"><code>one</code></pre>', "ruby", "one", id="inherit-pre"),
        pytest.param(
            '<pre class="language-ruby"><code class="language-python">one</code></pre>', "python", "one", id="code-wins"
        ),
        pytest.param('<pre> <code class="language-python">one</code> </pre>', "python", " one ", id="space-siblings"),
        pytest.param('<pre><code class="language-python">one</code> </pre>', "python", "one ", id="trailing-space"),
        pytest.param(
            '<pre>\n\n<code class="language-python">one</code>\n\n</pre>', "python", "\none\n", id="newline-siblings"
        ),
        pytest.param('<pre><code class="language-python">one</code>two</pre>', "fallback", "onetwo", id="text-sibling"),
        pytest.param(
            '<pre><code class="language-python">one</code><code>two</code></pre>',
            "fallback",
            "onetwo",
            id="two-code-elements",
        ),
        pytest.param(
            '<pre><!--comment--><code class="language-python">one</code></pre>', "fallback", "one", id="comment-sibling"
        ),
        pytest.param("<pre><svg>one</svg></pre>", "fallback", "one", id="foreign-element"),
    ],
)
def test_code_language(source: str, language: str, content: str) -> None:
    assert (
        parse(source).to_markdown(Markdown(code=Markdown.Code(language="fallback"))) == f"```{language}\n{content}\n```"
    )
