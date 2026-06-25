"""The security gate: every mutation-XSS vector must come out inert, and sanitizing must be idempotent.

A sanitizer is only as good as its adversarial corpus, so this is the file that matters. ``_live_danger`` reparses a
sanitized string and reports any executable construct that survived; ``XSS_CORPUS`` collects the known mutation-XSS
classes (foreign-content confusion, raw-text breakout, URL-scheme evasion, comment breakout). Two properties are
asserted across the whole corpus and every disposition: nothing dangerous survives, and ``sanitize(sanitize(x)) ==
sanitize(x)`` -- the round-trip invariant that turns a list of patched payloads into a guarantee, because any input
whose sanitized form sanitizes differently a second time is a live mutation-XSS.
"""

from __future__ import annotations

import pytest

from turbohtml import Element, parse_fragment
from turbohtml.clean import OnDisallowed, Policy, sanitize

# Elements that execute or load script if they survive in the HTML namespace.
_DANGER_TAGS = frozenset({"script", "iframe", "object", "embed", "frame", "style", "noscript", "base"})
# Schemes that run script when navigated to.
_DANGER_SCHEMES = ("javascript:", "data:", "vbscript:")


def _live_danger(html: str) -> list[str]:
    """Reparse sanitized HTML and list every executable construct that survived; empty means safe."""
    found: list[str] = []
    stack = list(parse_fragment(html).children)
    while stack:
        node = stack.pop()
        if isinstance(node, Element):
            if node.tag in _DANGER_TAGS and node.namespace.value == "html":
                found.append(f"<{node.tag}>")
            for name, raw in node.attrs.items():
                value = (" ".join(raw) if isinstance(raw, list) else (raw or "")).lower()
                if name.startswith("on"):
                    found.append(f"@{name}")
                if name in {"href", "src", "action", "xlink:href", "formaction"}:
                    cleaned = "".join(ch for ch in value if ord(ch) > 0x20)
                    if cleaned.startswith(_DANGER_SCHEMES):
                        found.append(f"{name}={cleaned[:24]}")
        stack.extend(getattr(node, "children", ()))
    return found


XSS_CORPUS = [
    pytest.param("<script>alert(1)</script>", id="script"),
    pytest.param("<scr<script>ipt>alert(1)</scr</script>ipt>", id="nested-script"),
    pytest.param("<img src=x onerror=alert(1)>", id="img-onerror"),
    pytest.param("<a href='javascript:alert(1)'>x</a>", id="js-url"),
    pytest.param("<a href='java\tscript:alert(1)'>x</a>", id="js-url-tab"),
    pytest.param("<a href='java\nscript:alert(1)'>x</a>", id="js-url-newline"),
    pytest.param("<a href='&#106;avascript:alert(1)'>x</a>", id="js-url-entity"),
    pytest.param("<a href='ja&#x09;vascript:alert(1)'>x</a>", id="js-url-hex-entity"),
    pytest.param("<a href='JaVaScRiPt:alert(1)'>x</a>", id="js-url-case"),
    pytest.param("<a href='  javascript:alert(1)'>x</a>", id="js-url-leading-space"),
    pytest.param("<a href='\x01javascript:alert(1)'>x</a>", id="js-url-control"),
    pytest.param("<a href='data:text/html,<script>alert(1)</script>'>x</a>", id="data-url"),
    pytest.param("<a href='vbscript:msgbox(1)'>x</a>", id="vbscript-url"),
    pytest.param(
        "<svg><iframe><a title='</a><img src=x onerror=alert(1)>'>x</a></iframe></svg>", id="svg-ns-confusion"
    ),
    pytest.param(
        "<math><mtext><table><mglyph><style><img src=x onerror=alert(1)></style></table></mtext></math>",
        id="mathml-mglyph",
    ),
    pytest.param("<svg><a><circle/></a></svg>", id="svg-a-not-html-a"),
    pytest.param("<noscript><p title='</noscript><img src=x onerror=alert(1)>'>", id="noscript-context"),
    pytest.param("<style><img src=x onerror=alert(1)></style>", id="style-rawtext"),
    pytest.param("<title><img src=x onerror=alert(1)></title>", id="title-rawtext"),
    pytest.param("<textarea><img src=x onerror=alert(1)></textarea>", id="textarea-rcdata"),
    pytest.param("<xmp><img src=x onerror=alert(1)></xmp>", id="xmp-rawtext"),
    pytest.param("<!-- --><img src=x onerror=alert(1)>", id="comment-then-img"),
    pytest.param("<!--<img src=x onerror=alert(1)>-->", id="img-in-comment"),
    pytest.param("<![CDATA[<img src=x onerror=alert(1)>]]>", id="cdata"),
    pytest.param("<svg></p><style><a id=</style><img src=x onerror=alert(1)>", id="svg-style-attr-breakout"),
    pytest.param(
        "<form><math><mtext></form><form><mglyph><style></math><img src onerror=alert(1)>", id="form-math-mutation"
    ),
    pytest.param("<select><noscript><svg><style></select><img src onerror=alert(1)>", id="select-noscript-svg"),
    pytest.param("<b><i></b></i><img src=x onerror=alert(1)>", id="misnested-adoption"),
    pytest.param('<a href="javascript:alert(1)" onmouseover=alert(2)>x</a>', id="js-url-plus-handler"),
    pytest.param("<p title='\"><img src=x onerror=alert(1)>'>safe</p>", id="attr-value-breakout"),
    pytest.param("<a href='http://ok' href='javascript:alert(1)'>x</a>", id="dup-href-js-second"),
    pytest.param("<a href='javascript:alert(1)' href='http://ok'>x</a>", id="dup-href-js-first"),
    pytest.param("<a href='http://ok' href='data:text/html,<script>alert(1)</script>'>x</a>", id="dup-href-data"),
    pytest.param('<a href="http://ok" href="vbscript:msgbox(1)">x</a>', id="dup-href-vbscript"),
]

_MODES = [
    pytest.param(Policy(), id="escape"),
    pytest.param(Policy(on_disallowed_tag=OnDisallowed.STRIP), id="strip"),
    pytest.param(Policy(on_disallowed_tag=OnDisallowed.REMOVE), id="remove"),
    pytest.param(Policy.relaxed(), id="relaxed"),
    pytest.param(Policy.strict(), id="strict"),
]


@pytest.mark.parametrize("payload", XSS_CORPUS)
@pytest.mark.parametrize("policy", _MODES)
def test_no_live_danger(payload: str, policy: Policy) -> None:
    danger = _live_danger(sanitize(payload, policy))
    assert danger == [], f"live XSS survived: {danger}"


@pytest.mark.parametrize("payload", XSS_CORPUS)
@pytest.mark.parametrize("policy", _MODES)
def test_round_trip_invariant(payload: str, policy: Policy) -> None:
    once = sanitize(payload, policy)
    assert sanitize(once, policy) == once, "sanitizing is not idempotent: a live mutation-XSS"


def test_oracle_detects_a_real_handler() -> None:
    # guard the guard: _live_danger must flag an event handler that is genuinely live
    assert _live_danger('<img src=x onerror="alert(1)">') == ["@onerror"]


def test_oracle_detects_a_real_script() -> None:
    assert _live_danger("<script>alert(1)</script>") == ["<script>"]


def test_oracle_detects_a_dangerous_url() -> None:
    assert _live_danger('<a href="javascript:alert(1)">x</a>') == ["href=javascript:alert(1)"]


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param("<select><plaintext></select><img src=x onerror=alert(1)>", id="plaintext-in-select"),
        pytest.param("<plaintext><img src=x onerror=alert(1)>", id="bare-plaintext"),
    ],
)
def test_allowlisted_plaintext_is_neutralized(payload: str) -> None:
    # a custom policy may allowlist <plaintext>, but its content is raw text that cannot
    # be escaped once the element is kept, so a </select><img onerror> tail would reparse
    # into a live image. Like <xmp>, <plaintext> must always be neutralized (#72).
    policy = Policy(tags=frozenset({"plaintext", "select", "img"}), attributes={"img": frozenset({"src"})})
    out = sanitize(payload, policy)
    assert _live_danger(out) == [], f"live XSS survived: {out!r}"
    assert sanitize(out, policy) == out, "sanitizing is not idempotent"
