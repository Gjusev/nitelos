"""Bounded strict JSON parsing (private module).

Parses exactly the RFC 8259 grammar (objects, arrays, strings, numbers,
true/false/null) with these ingestion rules from document 03:

- duplicate object keys are rejected and reported at the duplicated key's path;
- NaN/Infinity tokens are syntax errors and numbers that overflow to a
  non-finite float are rejected;
- nesting deeper than the caller's bound is rejected (containers count one
  level each; the root value is level 1);
- integer literals beyond Python's conversion limit are rejected as too large.

Error messages carry no input values, only a JSON-style path (``$`` root,
``.key`` members, ``[i]`` items).
"""

from __future__ import annotations

import math
from enum import StrEnum

_DIGITS = "0123456789"
_ESCAPES = {'"': '"', "\\": "\\", "/": "/", "b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t"}
_WHITESPACE = " \t\n\r"


class JsonErrorKind(StrEnum):
    SYNTAX = "SYNTAX"
    DUPLICATE_KEY = "DUPLICATE_KEY"
    NON_FINITE = "NON_FINITE"
    TOO_DEEP = "TOO_DEEP"
    TOO_LARGE = "TOO_LARGE"


class JsonError(ValueError):
    """Strict-JSON violation with a kind, a JSON-style path and a value-free message."""

    def __init__(self, kind: JsonErrorKind, path: str, message: str) -> None:
        super().__init__(f"{kind} at {path}: {message}")
        self.kind = kind
        self.path = path


class _Parser:
    def __init__(self, text: str, max_depth: int) -> None:
        self._text = text
        self._n = len(text)
        self._i = 0
        self._max_depth = max_depth

    def parse_document(self) -> object:
        value = self._value(1, "$")
        self._skip_ws()
        if self._i != self._n:
            raise JsonError(JsonErrorKind.SYNTAX, "$", "unexpected trailing characters")
        return value

    def _skip_ws(self) -> None:
        while self._i < self._n and self._text[self._i] in _WHITESPACE:
            self._i += 1

    def _value(self, depth: int, path: str) -> object:
        if depth > self._max_depth:
            raise JsonError(JsonErrorKind.TOO_DEEP, path, "nesting exceeds the allowed depth")
        self._skip_ws()
        if self._i >= self._n:
            raise JsonError(JsonErrorKind.SYNTAX, path, "unexpected end of input")
        ch = self._text[self._i]
        if ch == "{":
            return self._object(depth, path)
        if ch == "[":
            return self._array(depth, path)
        if ch == '"':
            return self._string(path)
        if ch == "t":
            return self._literal("true", True, path)
        if ch == "f":
            return self._literal("false", False, path)
        if ch == "n":
            return self._literal("null", None, path)
        if ch == "-" or ch in _DIGITS:
            return self._number(path)
        raise JsonError(JsonErrorKind.SYNTAX, path, "unexpected character")

    def _object(self, depth: int, path: str) -> dict[str, object]:
        self._i += 1  # '{'
        obj: dict[str, object] = {}
        self._skip_ws()
        if self._i < self._n and self._text[self._i] == "}":
            self._i += 1
            return obj
        while True:
            self._skip_ws()
            if self._i >= self._n or self._text[self._i] != '"':
                raise JsonError(JsonErrorKind.SYNTAX, path, "expected an object key")
            key = self._string(path)
            key_path = f"{path}.{key}"
            if key in obj:
                raise JsonError(JsonErrorKind.DUPLICATE_KEY, key_path, "duplicate object key")
            self._skip_ws()
            if self._i >= self._n or self._text[self._i] != ":":
                raise JsonError(JsonErrorKind.SYNTAX, key_path, "expected ':' after object key")
            self._i += 1
            obj[key] = self._value(depth + 1, key_path)
            self._skip_ws()
            if self._i >= self._n:
                raise JsonError(JsonErrorKind.SYNTAX, path, "unterminated object")
            ch = self._text[self._i]
            if ch == ",":
                self._i += 1
                continue
            if ch == "}":
                self._i += 1
                return obj
            raise JsonError(JsonErrorKind.SYNTAX, path, "expected ',' or '}' in object")

    def _array(self, depth: int, path: str) -> list[object]:
        self._i += 1  # '['
        items: list[object] = []
        self._skip_ws()
        if self._i < self._n and self._text[self._i] == "]":
            self._i += 1
            return items
        while True:
            items.append(self._value(depth + 1, f"{path}[{len(items)}]"))
            self._skip_ws()
            if self._i >= self._n:
                raise JsonError(JsonErrorKind.SYNTAX, path, "unterminated array")
            ch = self._text[self._i]
            if ch == ",":
                self._i += 1
                continue
            if ch == "]":
                self._i += 1
                return items
            raise JsonError(JsonErrorKind.SYNTAX, path, "expected ',' or ']' in array")

    def _literal(self, word: str, value: object, path: str) -> object:
        if self._text[self._i : self._i + len(word)] != word:
            raise JsonError(JsonErrorKind.SYNTAX, path, "unexpected character")
        self._i += len(word)
        return value

    def _string(self, path: str) -> str:
        self._i += 1  # '"'
        chunks: list[str] = []
        while True:
            if self._i >= self._n:
                raise JsonError(JsonErrorKind.SYNTAX, path, "unterminated string")
            ch = self._text[self._i]
            if ch == '"':
                self._i += 1
                return "".join(chunks)
            if ch == "\\":
                chunks.append(self._escape(path))
            elif ch < " ":
                raise JsonError(JsonErrorKind.SYNTAX, path, "control character in string")
            else:
                chunks.append(ch)
                self._i += 1

    def _escape(self, path: str) -> str:
        self._i += 1  # '\'
        if self._i >= self._n:
            raise JsonError(JsonErrorKind.SYNTAX, path, "unterminated escape")
        esc = self._text[self._i]
        if esc in _ESCAPES:
            self._i += 1
            return _ESCAPES[esc]
        if esc != "u":
            raise JsonError(JsonErrorKind.SYNTAX, path, "invalid escape")
        code = self._hex4(path)
        if 0xD800 <= code <= 0xDBFF:
            if self._text[self._i : self._i + 2] != "\\u":
                raise JsonError(JsonErrorKind.SYNTAX, path, "unpaired surrogate")
            self._i += 1  # land on the 'u' of the low escape for _hex4
            low = self._hex4(path)
            if not 0xDC00 <= low <= 0xDFFF:
                raise JsonError(JsonErrorKind.SYNTAX, path, "unpaired surrogate")
            return chr(0x10000 + ((code - 0xD800) << 10) + (low - 0xDC00))
        if 0xDC00 <= code <= 0xDFFF:
            raise JsonError(JsonErrorKind.SYNTAX, path, "unpaired surrogate")
        return chr(code)

    def _hex4(self, path: str) -> int:
        # self._i points at the 'u' of a \u escape
        digits = self._text[self._i + 1 : self._i + 5]
        if len(digits) != 4:
            raise JsonError(JsonErrorKind.SYNTAX, path, "incomplete unicode escape")
        try:
            code = int(digits, 16)
        except ValueError:
            raise JsonError(JsonErrorKind.SYNTAX, path, "invalid unicode escape") from None
        self._i += 5  # 'u' plus the four hex digits
        return code

    def _number(self, path: str) -> int | float:
        start = self._i
        if self._text[self._i] == "-":
            self._i += 1
        if self._i >= self._n:
            raise JsonError(JsonErrorKind.SYNTAX, path, "invalid number")
        ch = self._text[self._i]
        if ch == "0":
            self._i += 1
        elif ch in _DIGITS:
            while self._i < self._n and self._text[self._i] in _DIGITS:
                self._i += 1
        else:
            raise JsonError(JsonErrorKind.SYNTAX, path, "invalid number")
        is_float = False
        if self._i < self._n and self._text[self._i] == ".":
            is_float = True
            self._i += 1
            if self._i >= self._n or self._text[self._i] not in _DIGITS:
                raise JsonError(JsonErrorKind.SYNTAX, path, "invalid number")
            while self._i < self._n and self._text[self._i] in _DIGITS:
                self._i += 1
        if self._i < self._n and self._text[self._i] in "eE":
            is_float = True
            self._i += 1
            if self._i < self._n and self._text[self._i] in "+-":
                self._i += 1
            if self._i >= self._n or self._text[self._i] not in _DIGITS:
                raise JsonError(JsonErrorKind.SYNTAX, path, "invalid number")
            while self._i < self._n and self._text[self._i] in _DIGITS:
                self._i += 1
        text = self._text[start : self._i]
        if is_float:
            value = float(text)
            if not math.isfinite(value):
                raise JsonError(JsonErrorKind.NON_FINITE, path, "number is not finite")
            return value
        try:
            return int(text)
        except ValueError:
            raise JsonError(JsonErrorKind.TOO_LARGE, path, "integer literal is too large") from None


def parse_json(text: str, *, max_depth: int) -> object:
    """Parse ``text`` as strict JSON with the documented ingestion rules."""
    return _Parser(text, max_depth).parse_document()
