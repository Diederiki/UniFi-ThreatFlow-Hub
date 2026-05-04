"""Parse the [4-byte tag][4-byte BE length][zlib JSON] chunk format that
flows over UniFi's cloud-proxy WebRTC data channel.

Each MQTT/WebRTC peer concatenates one or more chunks per data-channel
message; logical messages may also span multiple data-channel messages.
The parser is stateful and yields fully-decoded JSON objects as soon as
enough bytes have accumulated.
"""
from __future__ import annotations

import json
import struct
import zlib
from typing import Iterator


class ChunkParser:
    def __init__(self) -> None:
        self._buf = bytearray()

    def feed(self, data: bytes) -> Iterator[dict]:
        """Append bytes; yield each fully-decoded JSON dict."""
        self._buf.extend(data)
        i = 0
        while i + 8 <= len(self._buf):
            length = struct.unpack(">I", self._buf[i + 4 : i + 8])[0]
            if length == 0 or i + 8 + length > len(self._buf):
                break  # need more bytes
            body = bytes(self._buf[i + 8 : i + 8 + length])
            try:
                txt = zlib.decompress(body).decode("utf-8")
                obj = json.loads(txt)
                if isinstance(obj, dict):
                    yield obj
            except (zlib.error, UnicodeDecodeError, json.JSONDecodeError):
                pass  # skip malformed; everything else still parseable
            i += 8 + length
        if i:
            del self._buf[:i]
