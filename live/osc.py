"""Minimal OSC 1.0 client — pure stdlib, no dependencies. Shared by the spike
and the live REPL. The Rust host will speak the same bytes.

Hard-won: OSC string padding is `(-len(bytes+NUL)) % 4`. The classic
`(4 - len%4) or 4` idiom adds a spurious 4 bytes when already aligned, which
silently corrupts every following argument.
"""
import socket
import struct


def _ostr(s: str) -> bytes:
    b = s.encode("ascii") + b"\x00"
    return b + b"\x00" * (-len(b) % 4)


def encode(address: str, *args) -> bytes:
    """Encode one OSC message. Supports int (i), float (f), str (s), bytes (b)."""
    tags = ","
    body = b""
    for a in args:
        if isinstance(a, bool):
            raise TypeError("OSC has no bool type; pass 1/0")
        if isinstance(a, int):
            tags += "i"; body += struct.pack(">i", a)
        elif isinstance(a, float):
            tags += "f"; body += struct.pack(">f", a)
        elif isinstance(a, str):
            tags += "s"; body += _ostr(a)
        elif isinstance(a, (bytes, bytearray)):
            tags += "b"
            blob = bytes(a)
            body += struct.pack(">i", len(blob)) + blob + b"\x00" * (-len(blob) % 4)
        else:
            raise TypeError(f"unsupported OSC arg type: {type(a)}")
    return _ostr(address) + _ostr(tags) + body


def _dstr(data: bytes, i: int):
    end = data.index(b"\x00", i)
    return data[i:end].decode("ascii"), end + (4 - (end - i) % 4)


def decode(data: bytes):
    """Decode one OSC message -> (address, [args]). Enough for scsynth replies."""
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
            break
    return address, args


class Client:
    """UDP OSC client aimed at one host:port (scsynth), able to receive replies."""

    def __init__(self, host: str = "127.0.0.1", port: int = 57110):
        self.addr = (host, port)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("", 0))

    def send(self, address: str, *args) -> None:
        self.sock.sendto(encode(address, *args), self.addr)

    def recv(self, timeout: float = 1.0):
        self.sock.settimeout(timeout)
        try:
            data, _ = self.sock.recvfrom(65535)
        except socket.timeout:
            return None
        return decode(data)

    def wait_for(self, address: str, timeout: float = 3.0):
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
