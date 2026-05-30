"""
Minimal length-prefixed message framing for Privox main <-> inference worker IPC.

Wire format (per message):
    [4 bytes big-endian unsigned length N][N bytes payload]

A message payload is itself:
    [4 bytes big-endian header length H][H bytes UTF-8 JSON header][remaining bytes = binary blob]

The JSON header carries the control fields (cmd, fields, blob_dtype, ...).
The optional binary blob carries raw audio (float32) without JSON overhead so
multi-second recordings transfer cheaply.

This module has no heavy dependencies so it can be imported by both the light
main process and the CUDA-heavy worker process.
"""
from __future__ import annotations

import json
import socket
import struct
from typing import Any, Optional, Tuple

_LEN = struct.Struct(">I")


def _recv_exactly(sock: socket.socket, n: int) -> Optional[bytes]:
    """Read exactly n bytes from sock, or None if the peer closed early."""
    buf = bytearray()
    while len(buf) < n:
        try:
            chunk = sock.recv(n - len(buf))
        except (ConnectionError, OSError):
            return None
        if not chunk:
            return None
        buf.extend(chunk)
    return bytes(buf)


def send_message(sock: socket.socket, header: dict, blob: bytes = b"") -> None:
    """Send a (json header, binary blob) message with length-prefix framing."""
    header_bytes = json.dumps(header, ensure_ascii=False).encode("utf-8")
    payload = _LEN.pack(len(header_bytes)) + header_bytes + (blob or b"")
    frame = _LEN.pack(len(payload)) + payload
    sock.sendall(frame)


def recv_message(sock: socket.socket) -> Optional[Tuple[dict, bytes]]:
    """Receive one message. Returns (header_dict, blob_bytes) or None on disconnect."""
    raw_len = _recv_exactly(sock, _LEN.size)
    if raw_len is None:
        return None
    (payload_len,) = _LEN.unpack(raw_len)
    payload = _recv_exactly(sock, payload_len)
    if payload is None:
        return None
    if len(payload) < _LEN.size:
        return None
    (header_len,) = _LEN.unpack(payload[: _LEN.size])
    header_start = _LEN.size
    header_end = header_start + header_len
    header_bytes = payload[header_start:header_end]
    blob = payload[header_end:]
    try:
        header: dict[str, Any] = json.loads(header_bytes.decode("utf-8"))
    except Exception:
        header = {}
    return header, blob
