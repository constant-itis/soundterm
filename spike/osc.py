"""Minimal OSC 1.0 client — pure stdlib, no dependencies.

OSC is a trivial wire format: null-terminated strings padded to 4 bytes,
a comma-led type-tag string, then big-endian args. That's the whole spec we
need to drive scsynth. Keeping this dependency-free is deliberate — the real
Rust host will speak the same bytes.
"""
import socket
import struct


def _ostr(s: str) -> bytes:
    """Encode an OSC string: ASCII + NUL terminator, padded to a 4-byte boundary.
    The terminator is already part of the string, so a string whose length+NUL is
    already a multiple of 4 needs ZERO extra pad (the old `or 4` idiom wrongly
    added 4 here, shifting the body and corrupting every following arg)."""
    b = s.encode("ascii") + b"\x00"
    return b + b"\x00" * (-len(b) % 4)


def encode(address: str, *args) -> bytes:
    """Encode a single OSC message. Supports int (i), float (f), str (s), bytes (b)."""
    tags = ","
    body = b""
    for a in args:
        if isinstance(a, bool):
            raise TypeError("OSC has no bool type; pass 1/0")
        if isinstance(a, int):
            tags += "i"
            body += struct.pack(">i", a)
        elif isinstance(a, float):
            tags += "f"
            body += struct.pack(">f", a)
        elif isinstance(a, str):
            tags += "s"
            body += _ostr(a)
        elif isinstance(a, (bytes, bytearray)):
            # OSC blob: size prefix + data padded to a 4-byte boundary. Unlike a
            # string, a blob adds NO trailing pad when already aligned.
            tags += "b"
            blob = bytes(a)
            pad = (-len(blob)) % 4
            body += struct.pack(">i", len(blob)) + blob + b"\x00" * pad
        else:
            raise TypeError(f"unsupported OSC arg type: {type(a)}")
    return _ostr(address) + _ostr(tags) + body


def _dstr(data: bytes, i: int):
    """Decode a padded OSC string starting at offset i -> (str, next_offset)."""
    end = data.index(b"\x00", i)
    s = data[i:end].decode("ascii")
    nxt = end + (4 - (end - i) % 4)  # advance past the NUL + padding
    return s, nxt


def decode(data: bytes):
    """Decode a single OSC message -> (address, [args]). Enough for scsynth replies."""
    address, i = _dstr(data, 0)
    if i >= len(data) or data[i:i + 1] != b",":
        return address, []
    tags, i = _dstr(data, i)
    args = []
    for t in tags[1:]:
        if t == "i":
            args.append(struct.unpack_from(">i", data, i)[0]); i += 4
        elif t == "f":
            args.append(struct.unpack_from(">f", data, i)[0]); i += 4
        elif t == "s":
            s, i = _dstr(data, i); args.append(s)
        else:
            break  # unknown/blob tag — stop; we don't need it
    return address, args


class Client:
    """UDP OSC client aimed at one host:port (scsynth). Can also receive replies —
    scsynth answers async commands (/done, /fail) to the sender's socket."""

    def __init__(self, host: str = "127.0.0.1", port: int = 57110):
        self.addr = (host, port)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("", 0))  # bind so scsynth's replies come back to us

    def send(self, address: str, *args) -> None:
        self.sock.sendto(encode(address, *args), self.addr)

    def recv(self, timeout: float = 1.0):
        """Wait up to `timeout`s for one OSC message. Returns (address, args) or None."""
        self.sock.settimeout(timeout)
        try:
            data, _ = self.sock.recvfrom(65535)
        except socket.timeout:
            return None
        return decode(data)

    def wait_for(self, address: str, timeout: float = 3.0):
        """Block until a message with `address` arrives (returns its args), or raise
        on /fail / timeout. Drains unrelated messages in between."""
        import time as _t
        deadline = _t.monotonic() + timeout
        while _t.monotonic() < deadline:
            msg = self.recv(max(0.05, deadline - _t.monotonic()))
            if msg is None:
                continue
            addr, args = msg
            if addr == address:
                return args
            if addr == "/fail":
                raise RuntimeError(f"scsynth /fail: {args}")
        raise TimeoutError(f"timed out waiting for {address}")

    def close(self) -> None:
        self.sock.close()
