"""Unit tests for server.tool_xml_filter.ToolCallXMLStreamFilter.

Run directly:  python tests/test_tool_xml_filter.py
Or via pytest: pytest tests/test_tool_xml_filter.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.tool_xml_filter import (  # noqa: E402
    ToolCallXMLStreamFilter,
    parse_function_calls_block,
)


def run(chunks):
    """Feed chunks through a fresh filter; return (visible_text, tool_calls)."""
    f = ToolCallXMLStreamFilter()
    visible = []
    calls = []
    for c in chunks:
        v, cs = f.feed(c)
        visible.append(v)
        calls.extend(cs)
    v, cs = f.flush()
    visible.append(v)
    calls.extend(cs)
    return "".join(visible), calls


_BLOCK = (
    "<function_calls>\n"
    '<invoke name="mcp-pubchem">\n'
    '<parameter name="action">search_compound</parameter>\n'
    '<parameter name="query">orforglipron</parameter>\n'
    "</invoke>\n"
    "</function_calls>"
)


def test_plain_text_passthrough():
    text = "Here is the molecular structure image of orforglipron."
    visible, calls = run([text])
    assert visible == text, visible
    assert calls == [], calls


def test_full_block_single_chunk_is_stripped_and_parsed():
    visible, calls = run(["Before. ", _BLOCK, " After."])
    assert "<function_calls>" not in visible
    assert "<invoke" not in visible
    assert "<parameter" not in visible
    assert "Before." in visible and "After." in visible
    assert calls == [
        {"name": "mcp-pubchem",
         "arguments": {"action": "search_compound", "query": "orforglipron"}}
    ], calls


def test_block_split_across_chunks():
    # Mirrors the real stream: tags split at arbitrary points.
    chunks = [
        "I'll help you get the molecule image of orforglipron. ",
        "\n\n<function", "_calls>\n<invoke name=\"m", "cp-pubchem\">\n",
        '<parameter name="', 'action">search_compound</parameter>\n',
        '<parameter name="query">orforgli', "pron</parameter>\n",
        "</inv", "oke>\n</function_calls>",
        "\n\nHere is the image.",
    ]
    visible, calls = run(chunks)
    assert "<function" not in visible and "invoke" not in visible, repr(visible)
    assert "parameter" not in visible, repr(visible)
    assert "I'll help you get the molecule image of orforglipron." in visible
    assert "Here is the image." in visible
    assert calls == [
        {"name": "mcp-pubchem",
         "arguments": {"action": "search_compound", "query": "orforglipron"}}
    ], calls


def test_thinking_and_results_dropped_without_calls():
    visible, calls = run(["A ", "<thinking>secret reasoning</thinking>", " B ",
                          "<results>raw dump</results>", " C"])
    assert "secret reasoning" not in visible
    assert "raw dump" not in visible
    assert "A " in visible and " B " in visible and " C" in visible
    assert calls == []


def test_benign_less_than_preserved():
    for text in ["if a < b then c", "x <= y", "use <html> tags", "3 < 4 < 5"]:
        visible, calls = run([text])
        assert visible == text, (text, visible)
        assert calls == []


def test_benign_less_than_split_across_chunks():
    visible, _ = run(["value is <", "= 5 always"])
    assert visible == "value is <= 5 always", repr(visible)


def test_unclosed_block_dropped_at_flush():
    visible, calls = run(["text ", "<function_calls>\n<invoke name=\"x\">"])
    assert "function_calls" not in visible
    assert "invoke" not in visible
    assert visible.strip() == "text", repr(visible)
    assert calls == []  # never completed


def test_multiple_invokes_in_one_block():
    block = (
        "<function_calls>"
        '<invoke name="a"><parameter name="p">1</parameter></invoke>'
        '<invoke name="b"><parameter name="q">2</parameter></invoke>'
        "</function_calls>"
    )
    visible, calls = run([block])
    assert visible.strip() == ""
    assert calls == [
        {"name": "a", "arguments": {"p": "1"}},
        {"name": "b", "arguments": {"q": "2"}},
    ], calls


def test_stray_invoke_outside_block_is_dropped():
    visible, calls = run(['x <invoke name="y">stuff</invoke> z'])
    assert "invoke" not in visible
    assert "stuff" not in visible          # inner value dropped too
    assert "x " in visible and " z" in visible
    # No wrapping <function_calls>, so nothing is parsed — just cleaned.
    assert calls == []


def test_stray_parameter_value_outside_block_is_dropped():
    # Mirrors the real leak: a bare <parameter> sibling of a function_calls block.
    text = ('</function_calls>\n'
            '<parameter name="server_name">mcp-pubchem</parameter>\n'
            'Here is the image.')
    visible, calls = run([text])
    assert "mcp-pubchem" not in visible
    assert "parameter" not in visible
    assert "Here is the image." in visible


def test_parse_helper_handles_empty():
    assert parse_function_calls_block("") == []
    assert parse_function_calls_block("no invokes here") == []


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  ok  {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL  {t.__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
