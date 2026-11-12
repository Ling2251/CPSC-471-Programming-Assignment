"""Person A's LS command, ready for Person C's future client control loop."""

import socket
import sys
import os

from ftp_common import (
    format_control_line,
    recv_control_line,
    recv_frame,
    send_all,
    send_frame,
)


def do_ls(control_sock, *, output=None, timeout=10.0):
    """Print and return listing text using an already-connected IPv4 control socket.

    Person C should call do_ls(control_sock) for the user's `ls` command.
    A server 500 response raises RuntimeError and leaves control usable. Other
    failures close control because unread responses may leave it out of sync.
    OSError, ConnectionError, and ValueError propagate to the caller.
    """
    if output is None:
        output = sys.stdout
    old_timeout = control_sock.gettimeout()
    synchronized = False
    try:
        control_sock.settimeout(timeout)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.settimeout(timeout)
            listener.bind((control_sock.getsockname()[0], 0))
            listener.listen(1)
            port = listener.getsockname()[1]
            send_all(control_sock, format_control_line("LS", port).encode("utf-8"))
            status = recv_control_line(control_sock)
            if status is not None and status.startswith("500 ERROR "):
                synchronized = True
                raise RuntimeError(status)
            if status != "150 OK":
                raise ValueError(f"expected 150 OK, received {status!r}")
            data_sock, peer = listener.accept()
            with data_sock:
                data_sock.settimeout(timeout)
                if peer[0] != control_sock.getpeername()[0]:
                    raise ValueError("data connection came from a different server")
                payload = bytearray()
                while True:
                    frame = recv_frame(data_sock)
                    if frame is None:
                        break
                    payload.extend(frame)
            status = recv_control_line(control_sock)
            if status is not None and status.startswith("500 ERROR "):
                synchronized = True
                raise RuntimeError(status)
            parts = status.split() if status is not None else []
            if (len(parts) != 3 or parts[:2] != ["226", "COMPLETE"]
                    or not parts[2].isascii() or not parts[2].isdigit()
                    or int(parts[2]) != len(payload)):
                raise ValueError(f"invalid completion status: {status!r}")
            text = payload.decode("utf-8")
            synchronized = True
            output.write(text)
            return text
    finally:
        if synchronized:
            control_sock.settimeout(old_timeout)
        else:
            control_sock.close()

def do_put(control_sock, filename, timeout=10.0):
    """Upload a local file to the FTP server."""

    if not os.path.isfile(filename):
        raise FileNotFoundError(f"Local file not found: {filename}")

    if any(ch.isspace() for ch in filename):
        raise ValueError("Filenames containing spaces are not supported")

    old_timeout = control_sock.gettimeout()
    synchronized = False

    try:
        control_sock.settimeout(timeout)

        with open(filename, "rb") as file:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
                listener.settimeout(timeout)
                listener.bind((control_sock.getsockname()[0], 0))
                listener.listen(1)

                port = listener.getsockname()[1]

                command = format_control_line("PUT", filename, port)
                send_all(control_sock, command.encode("utf-8"))

                response = recv_control_line(control_sock)

                if response is not None and response.startswith("500 ERROR"):
                    synchronized = True
                    raise RuntimeError(response)

                if response != "150 OK":
                    raise ValueError(f"Unexpected server response: {response}")

                data_sock, peer = listener.accept()

                with data_sock:
                    data_sock.settimeout(timeout)

                    if peer[0] != control_sock.getpeername()[0]:
                        raise ValueError("Unexpected data connection source")

                    total_bytes = 0

                    while True:
                        chunk = file.read(65536)

                        if not chunk:
                            break

                        send_frame(data_sock, chunk)
                        total_bytes += len(chunk)

                response = recv_control_line(control_sock)
                parts = response.split() if response is not None else []

                if response is not None and response.startswith("500 ERROR"):
                    synchronized = True
                    raise RuntimeError(response)

                if (
                    len(parts) != 3
                    or parts[:2] != ["226", "COMPLETE"]
                    or not parts[2].isascii()
                    or not parts[2].isdigit()
                    or int(parts[2]) != total_bytes
                ):
                    raise ValueError(f"Invalid completion response: {response}")

                synchronized = True
                print(f"Uploaded {filename}: {total_bytes} bytes")
                return total_bytes

    finally:
        if synchronized:
            control_sock.settimeout(old_timeout)
        else:
            control_sock.close()