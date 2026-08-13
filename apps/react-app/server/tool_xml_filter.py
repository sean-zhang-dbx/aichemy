"""Stateful filter that removes Claude tool-call XML from a streamed text
channel and reconstructs the tool calls it represents.

Some models (Anthropic / Claude via Databricks) intermittently emit their
tool use in the textual ``<function_calls><invoke ...>...`` dialect instead of
as structured tool calls. Left alone that XML renders verbatim in the chat
transcript, and the real tool activity never reaches the Agent Activity panel
(because no structured ``function_call`` events are emitted).

``ToolCallXMLStreamFilter`` consumes streamed text chunks — where a single tag
may be split across chunk boundaries — and returns:

* the text that is safe to display (tool-call/thinking/results XML removed), and
* any tool calls parsed out of completed ``<function_calls>`` blocks.

The visible text and the parsed calls together let the caller both clean the
chat stream and re-emit structured tool-call events for the activity panel.
"""

from __future__ import annotations

import re
from typing import Dict, List, Tuple

# Exact block openers: everything between open and close is removed from the
# visible text. ``<function_calls>`` blocks are additionally parsed into tool
# calls; ``<thinking>`` / ``<results>`` are dropped silently.
_EXACT_OPENERS: Dict[str, Tuple[str, str]] = {
    "<function_calls>": ("calls", "</function_calls>"),
    "<thinking>": ("drop", "</thinking>"),
    "<results>": ("drop", "</results>"),
}

# Attribute-bearing openers matched by prefix (the real tag carries attributes,
# e.g. ``<invoke name="...">``). A *stray* invoke/parameter appearing outside a
# ``<function_calls>`` block — including its inner value — is dropped so leftover
# text like a bare parameter value never reaches the transcript.
_PREFIX_OPENERS: Dict[str, Tuple[str, str]] = {
    "<invoke": ("drop", "</invoke>"),
    "<parameter": ("drop", "</parameter>"),
}

# Tag names we recognize as tool-call XML. A stray closing tag is dropped from
# the visible text as a safety net.
_TAG_NAMES = ("function_calls", "invoke", "parameter", "thinking", "results")

# Start of a recognized tag: ``<name`` or ``</name`` (attributes/``>`` follow).
_TAG_STARTS = tuple(f"<{n}" for n in _TAG_NAMES) + tuple(f"</{n}" for n in _TAG_NAMES)

_INVOKE_RE = re.compile(r'<invoke\s+name="([^"]+)"\s*>(.*?)</invoke>', re.DOTALL)
_PARAM_RE = re.compile(r'<parameter\s+name="([^"]+)"\s*>(.*?)</parameter>', re.DOTALL)


def parse_function_calls_block(inner: str) -> List[dict]:
    """Parse the inner text of a ``<function_calls>`` block into tool calls.

    Returns a list of ``{"name": str, "arguments": {param: value}}``. Malformed
    or empty blocks yield an empty list.
    """
    calls: List[dict] = []
    for name, body in _INVOKE_RE.findall(inner):
        args = {k: v.strip() for k, v in _PARAM_RE.findall(body)}
        calls.append({"name": name.strip(), "arguments": args})
    return calls


def _could_grow_into_tag(buf: str) -> bool:
    """True if ``buf`` (starting with ``<``) could still become a recognized tag.

    Used to hold back a partial tag split across chunk boundaries. ``"<"`` and
    ``"</"`` are always ambiguous; ``"<inv"`` is a prefix of ``"<invoke"``.
    """
    if buf in ("<", "</"):
        return True
    return any(start.startswith(buf) for start in _TAG_STARTS)


class ToolCallXMLStreamFilter:
    """Incrementally strip tool-call XML from a text stream.

    Feed text chunks with :meth:`feed`; call :meth:`flush` once the stream ends
    to release any benign buffered text (unclosed tool-call blocks are dropped).
    """

    def __init__(self) -> None:
        self._buf = ""
        self._mode = "text"          # "text" | "calls" | "drop"
        self._close_tag = ""         # closing tag sought while in a block

    def feed(self, text: str) -> Tuple[str, List[dict]]:
        """Consume a chunk; return (visible_text, tool_calls)."""
        if text:
            self._buf += text
        return self._process(final=False)

    def flush(self) -> Tuple[str, List[dict]]:
        """End of stream: emit benign leftover text, drop unclosed blocks."""
        visible, calls = self._process(final=True)
        if self._mode == "text" and self._buf:
            # A dangling partial like a lone "<" that never became a tag.
            visible += self._buf
        self._buf = ""
        self._mode = "text"
        self._close_tag = ""
        return visible, calls

    def _process(self, final: bool) -> Tuple[str, List[dict]]:
        out: List[str] = []
        calls: List[dict] = []
        progress = True
        while progress:
            progress = False

            if self._mode != "text":
                # Inside a block: consume everything up to the closing tag.
                cidx = self._buf.find(self._close_tag)
                if cidx == -1:
                    break  # wait for more; whole block stays buffered
                inner = self._buf[:cidx]
                if self._mode == "calls":
                    calls.extend(parse_function_calls_block(inner))
                self._buf = self._buf[cidx + len(self._close_tag):]
                self._mode = "text"
                self._close_tag = ""
                progress = True
                continue

            # text mode
            idx = self._buf.find("<")
            if idx == -1:
                if self._buf:
                    out.append(self._buf)
                    self._buf = ""
                break
            if idx > 0:
                out.append(self._buf[:idx])
                self._buf = self._buf[idx:]

            # self._buf now starts with "<"
            opener = self._match_block_opener()
            if opener == "hold":
                if final:
                    out.append(self._buf)
                    self._buf = ""
                break
            if opener is not None:
                open_len, mode, close_tag = opener
                self._buf = self._buf[open_len:]
                self._mode = mode
                self._close_tag = close_tag
                progress = True
                continue

            stray = self._match_stray_tag()
            if stray == "hold":
                if final:
                    # Never completed — treat as benign text.
                    out.append(self._buf)
                    self._buf = ""
                break
            if stray is not None:
                # A complete recognized tag (e.g. <invoke ...>, </invoke>): drop it.
                self._buf = self._buf[stray:]
                progress = True
                continue

            # Benign "<" (not tool-call XML): emit and keep scanning.
            out.append("<")
            self._buf = self._buf[1:]
            progress = True

        return "".join(out), calls

    def _match_block_opener(self):
        """Classify a ``<``-prefixed buffer against the block openers.

        Returns ``(open_len, mode, close_tag)`` to enter a block, ``"hold"`` if a
        prefix opener is present but its ``>`` has not arrived yet, or ``None``.
        """
        for opener, (mode, close_tag) in _EXACT_OPENERS.items():
            if self._buf.startswith(opener):
                return (len(opener), mode, close_tag)
        for prefix, (mode, close_tag) in _PREFIX_OPENERS.items():
            if self._buf.startswith(prefix):
                gt = self._buf.find(">")
                if gt == -1:
                    return "hold"  # opening tag not closed yet
                return (gt + 1, mode, close_tag)
        return None

    def _match_stray_tag(self):
        """Classify a ``<``-prefixed buffer that is not a block opener.

        Returns:
          * an int length to drop, if a complete stray tag is present;
          * ``"hold"`` if it is (or could become) an incomplete recognized tag;
          * ``None`` if it is benign text.
        """
        starts_a_tag = any(self._buf.startswith(s) for s in _TAG_STARTS)
        if starts_a_tag:
            gt = self._buf.find(">")
            if gt == -1:
                return "hold"  # tag not closed yet
            return gt + 1      # length of the complete tag
        if _could_grow_into_tag(self._buf):
            return "hold"      # partial prefix of a recognized tag
        return None            # benign
