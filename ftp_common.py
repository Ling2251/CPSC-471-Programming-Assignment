"""Shared byte framing and newline-delimited control messages."""

HEADER_SIZE = 10
MAX_CONTROL_BYTES = 65536


def send_all(sock, data):
    """Send every byte, returning the byte count; raise on a broken socket."""
    view = memoryview(data)
    total = 0
    while total < len(view):
        sent = sock.send(view[total:])
        if sent == 0:
            raise ConnectionError("socket closed during send_all")
        total += sent
    return total


def recv_all(sock, num_bytes):
    """Receive up to num_bytes; a short result means the peer closed."""
    if num_bytes < 0:
        raise ValueError("negative byte count")
    result = bytearray()
    while len(result) < num_bytes:
        chunk = sock.recv(min(num_bytes - len(result), 65536))
        if not chunk:
            break
        result.extend(chunk)
    return bytes(result)


def send_frame(sock, payload):
    """Send a binary payload preceded by exactly ten ASCII length digits."""
    if len(payload) > 9999999999:
        raise ValueError("payload exceeds ten-digit frame length")
    send_all(sock, f"{len(payload):010d}".encode("ascii"))
    send_all(sock, payload)


def recv_frame(sock):
    """Return bytes (including b''); None means clean EOF between frames."""
    header = recv_all(sock, HEADER_SIZE)
    if not header:
        return None
    if len(header) != HEADER_SIZE:
        raise ConnectionError("incomplete frame header")
    if not all(48 <= digit <= 57 for digit in header):
        raise ValueError("frame header must contain ten ASCII digits")
    size = int(header)
    payload = recv_all(sock, size)
    if len(payload) != size:
        raise ConnectionError("incomplete frame payload")
    return payload


def parse_control_line(line):
    """Return (uppercase command/status, argument list); blank gives (None, [])."""
    # Remove one optional wire terminator, not arbitrary trailing delimiters.
    if line.endswith("\n"):
        line = line[:-1]
        if line.endswith("\r"):
            line = line[:-1]
    if "\r" in line or "\n" in line or "\x00" in line:
        raise ValueError("embedded control-message delimiter")
    parts = line.split()
    return (parts[0].upper(), parts[1:]) if parts else (None, [])


def format_control_line(command, *args):
    """Build a newline-terminated string, e.g. format_control_line('LS', port).

    A complete status string may be passed as the sole argument.
    """
    parts = [str(command), *(str(arg) for arg in args)]
    if any(any(ch in part for ch in "\r\n\x00") for part in parts):
        raise ValueError("embedded control-message delimiter")
    text = " ".join(parts).strip()
    if not text:
        raise ValueError("empty control message")
    result = text + "\n"
    if len(result.encode("utf-8")) > MAX_CONTROL_BYTES:
        raise ValueError("control message too long")
    return result


def send_status(sock, status):
    """Send an existing server status string using the shared line format."""
    return send_all(sock, format_control_line(status).encode("utf-8"))


def recv_control_line(sock):
    """Read one UTF-8 line without consuming the next; None means clean EOF."""
    result = bytearray()
    while len(result) < MAX_CONTROL_BYTES:
        char = sock.recv(1)
        if not char:
            if result:
                raise ConnectionError("incomplete control line")
            return None
        result.extend(char)
        if char == b"\n":
            line = result.decode("utf-8")
            parse_control_line(line)
            # Match serv.py's original whitespace-only line handling.
            return line.strip()
    raise ValueError("control message too long")
