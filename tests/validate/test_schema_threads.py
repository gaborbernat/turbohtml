from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Final

from turbohtml import parse_xml
from turbohtml.validate import RelaxNG


def test_shared_schema_validates_distinct_documents() -> None:
    schema: Final = RelaxNG(
        '<grammar xmlns="http://relaxng.org/ns/structure/1.0"><start><ref name="node"/></start>'
        '<define name="node"><element name="node"><zeroOrMore><ref name="node"/></zeroOrMore>'
        "</element></define></grammar>"
    )
    documents: Final = [
        parse_xml("<node><node/></node>" if index % 2 == 0 else "<node><other/></node>") for index in range(32)
    ]
    with ThreadPoolExecutor(max_workers=4) as executor:
        results: Final = list(executor.map(schema.validate, documents))
    assert [result.valid for result in results] == [index % 2 == 0 for index in range(32)]
