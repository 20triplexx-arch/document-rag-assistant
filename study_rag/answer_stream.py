"""Incremental JSON array reader. It exposes only complete JSON values."""
from __future__ import annotations

import json


class AnswerArrayReader:
    def __init__(self, field, on_item):
        self.field, self.on_item = field, on_item
        self.buffer, self.position, self.state, self.key = "", 0, "root", None
        self.decoder = json.JSONDecoder()

    def feed(self, delta):
        self.buffer += delta
        if len(self.buffer) > 256_000:
            raise ValueError("Response exceeded capacity")
        while True:
            while self.position < len(self.buffer) and self.buffer[self.position].isspace():
                self.position += 1
            if self.position >= len(self.buffer) or self.state == "done":
                return
            char = self.buffer[self.position]
            if self.state == "root":
                if char != "{":
                    raise ValueError("Response root is not an object")
                self.position += 1; self.state = "key"
            elif self.state == "key":
                if char == "}":
                    self.state = "done"; return
                try:
                    key, end = self.decoder.raw_decode(self.buffer, self.position)
                except json.JSONDecodeError:
                    return
                if not isinstance(key, str):
                    raise ValueError("Invalid object key")
                self.key, self.position, self.state = key, end, "colon"
            elif self.state == "colon":
                if char != ":":
                    raise ValueError("Missing object colon")
                self.position += 1; self.state = "array" if self.key == self.field else "value"
            elif self.state == "value":
                try:
                    _, end = self.decoder.raw_decode(self.buffer, self.position)
                except json.JSONDecodeError:
                    return
                self.position, self.state = end, "separator"
            elif self.state == "separator":
                if char == "}":
                    self.state = "done"; return
                if char != ",":
                    raise ValueError("Missing object separator")
                self.position += 1; self.state = "key"
            elif self.state == "array":
                if char != "[":
                    raise ValueError("Answer units are not an array")
                self.position += 1; self.state = "item"
            elif self.state == "item":
                if char == "]":
                    self.state = "done"; return
                # Units must be objects. Waiting on a partial string/number can
                # otherwise expose a value before the network token is complete.
                if char != "{":
                    raise ValueError("Answer unit is not an object")
                try:
                    item, end = self.decoder.raw_decode(self.buffer, self.position)
                except json.JSONDecodeError:
                    return
                self.on_item(item)
                self.position, self.state = end, "item_separator"
            elif self.state == "item_separator":
                if char == "]":
                    self.state = "done"; return
                if char != ",":
                    raise ValueError("Missing answer separator")
                self.position += 1; self.state = "item"
