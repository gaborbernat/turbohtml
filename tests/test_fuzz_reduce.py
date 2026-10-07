from __future__ import annotations

import io
import json
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import pytest
from fuzz.reduce import minimize

from turbohtml import parse_fragment

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


def test_reduce_html_removes_subtrees_and_attributes() -> None:
    source = '<section><p id="keep" title="noise">x</p><aside>discard</aside></section>'

    def reproduces(text: str) -> bool:
        root = parse_fragment(text)
        return any(node.attrs.get("id") == "keep" and node.text == "x" for node in root.iter_elements())

    assert minimize(source, reproduces, "html") == '<section><p id="keep">x</p></section>'


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        pytest.param("p{color:red;margin:1px}", "p{color:red;}", id="style-rule"),
        pytest.param("@media screen{p{color:red;margin:1px}}", "@media screen{p{color:red;}}", id="media"),
        pytest.param("@font-face{color:red;src:url(x)}", "@font-face{color:red;}", id="at-rule-declarations"),
        pytest.param("color:red;margin:1px", "color:red;", id="inline"),
        pytest.param('p{color:red;content:"a;b"}', "p{color:red;}", id="string-semicolon"),
        pytest.param("@import 'x';p{color:red;margin:1px}", '@import "x";p{color:red;}', id="keep-other-rule"),
        pytest.param("p{broken;}", "p{broken;}", id="invalid-declaration"),
        pytest.param("", "", id="empty"),
    ],
)
def test_reduce_css_removes_declarations(source: str, expected: str) -> None:
    assert minimize(source, lambda candidate: "color:red" in candidate, "css") == expected


@pytest.mark.parametrize("syntax", ["html", "css", "js"])
def test_reduce_zero_budget_does_not_compare(syntax: Literal["html", "css", "js"]) -> None:
    assert minimize("<p>x</p>", lambda _text: pytest.fail("zero budget compared"), syntax, budget=0) == "<p>x</p>"


def test_reduce_budget_stops_predicate_calls() -> None:
    compared: list[str] = []
    assert minimize(
        "p{color:red;margin:1px;padding:2px}", lambda candidate: bool(compared.append(candidate)), "css", 1
    ) == ("p{color:red;margin:1px;padding:2px}")
    assert len(compared) == 1


def test_reduce_keeps_original_finding_class() -> None:
    source = "p{color:red;margin:1px}"

    def finding(text: str) -> str | None:
        return "original" if "color:red" in text and "margin:1px" in text else "different"

    assert minimize(source, lambda candidate: finding(candidate) == "original", "css") == source


def test_reduce_js_protocol_checks_candidates(mocker: MockerFixture) -> None:
    mocker.patch("fuzz.reduce.shutil.which", return_value="node")
    mocker.patch("fuzz.reduce.Path.is_dir", return_value=True)
    replies = io.StringIO(
        json.dumps({"kind": "candidate", "text": "keep();"})
        + "\n"
        + json.dumps({"kind": "done", "text": "keep();"})
        + "\n"
    )
    answers = io.StringIO()
    mocker.patch("fuzz.reduce.subprocess.Popen", autospec=True).return_value.__enter__.return_value = mocker.MagicMock(
        stdin=answers, stdout=replies
    )
    assert minimize("discard();keep();", lambda source: source == "keep();", "js") == "keep();"
    assert answers.getvalue() == '{"text": "discard();keep();", "budget": 600}\ntrue\n'


def test_reduce_js_reports_premature_exit(mocker: MockerFixture) -> None:
    mocker.patch("fuzz.reduce.shutil.which", return_value="node")
    mocker.patch("fuzz.reduce.Path.is_dir", return_value=True)
    mocker.patch("fuzz.reduce.subprocess.Popen", autospec=True).return_value.__enter__.return_value = mocker.MagicMock(
        stdin=io.StringIO(), stdout=io.StringIO(), returncode=3
    )
    with pytest.raises(RuntimeError, match="exited without a result: 3"):
        minimize("keep();", lambda _source: True, "js")


@pytest.mark.parametrize("missing", [pytest.param("node", id="node"), pytest.param("package", id="package")])
def test_reduce_js_reports_missing_backend(mocker: MockerFixture, missing: str) -> None:
    mocker.patch("fuzz.reduce.shutil.which", return_value=None if missing == "node" else "node")
    mocker.patch("fuzz.reduce.Path.is_dir", return_value=False)
    with pytest.raises(FileNotFoundError, match="required for JS reduction"):
        minimize("keep();", lambda _source: True, "js")


@pytest.mark.oracle
@pytest.mark.skipif(
    shutil.which("node") is None
    or not (Path(__file__).parents[1] / "tools/bench/node/node_modules/uglify-js").is_dir(),
    reason="node/npm backend absent",
)
@pytest.mark.parametrize(
    "source",
    [
        pytest.param("discard();keep();", id="statements"),
        pytest.param("function unused(){return 42}keep();", id="function"),
        pytest.param("if (noise) {discard()} keep();", id="conditional"),
        pytest.param("for(let i=0;i<3;i++)discard(i);keep();", id="loop"),
        pytest.param("const unused={name:'text'};keep();", id="object"),
        pytest.param("const unused=[1,2,3];keep();", id="array"),
        pytest.param("try{discard()}catch(e){discard(e)}finally{discard()}keep();", id="try"),
        pytest.param("class Unused{method(){return 4}}keep();", id="class"),
    ],
)
def test_reduce_js_uses_pinned_ast_fork(source: str) -> None:
    assert minimize(source, lambda candidate: "keep()" in candidate, "js", 100) == "keep();"


@pytest.mark.oracle
@pytest.mark.skipif(
    shutil.which("node") is None
    or not (Path(__file__).parents[1] / "tools/bench/node/node_modules/uglify-js").is_dir(),
    reason="node/npm backend absent",
)
def test_reduce_js_keeps_invalid_source() -> None:
    assert minimize("function {", lambda _candidate: True, "js") == "function {"


def test_reduce_acceptance_consumes_last_budget_call() -> None:
    assert minimize("p{color:red;margin:1px}", lambda _candidate: True, "css", 1) == "p{margin:1px;}"
