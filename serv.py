#!/usr/bin/env python3
"""
serv.py — Simplified FTP server (control + data channels)

Usage:
    python3 serv.py <PORT>

Person B owns this file and `handle_get` in server_handlers.py.
Person A will deliver ftp_common.py (send_all, recv_all, send_frame,
recv_frame, parse_control_line, send_status, recv_control_line)
and implement handle_ls.
Person D will implement handle_put.

If ftp_common.py is not present, fallback helpers are used so this
file works standalone. Once ftp_common.py appears, it is used automatically.
"""

import socket
import sys
import threading
import traceback

# ---------------------------------------------------------------------------
# Shared helpers: prefer Person A's ftp_common.py, fall back to local versions
# ---------------------------------------------------------------------------
try:
    from ftp_common import (
        send_all,
        recv_all,
        send_frame,
        recv_frame,
        parse_control_line,
        send_status,
        recv_control_line,
    )
    USING_SHARED_COMMON = True
except ImportError as _e:
    USING_SHARED_COMMON = False
    print(f"[serv.py] ftp_common unavailable ({_e}); using fallback helpers")

    def send_all(sock, data):
        total = 0
        while total < len(data):
            sent = sock.send(data[total:])
            if sent == 0:
                raise ConnectionError("socket closed during send_all")
            total += sent
        return total

    def recv_all(sock, num_bytes):
        buf = b""
        while len(buf) < num_bytes:
            chunk = sock.recv(min(num_bytes - len(buf), 65536))
            if not chunk:
                break
            buf += chunk
        return buf

    def send_frame(sock, payload):
        header = str(len(payload)).zfill(10).encode("ascii")
        send_all(sock, header + payload)

    def recv_frame(sock):
        header = recv_all(sock, 10)
        if len(header) < 10:
            return None
        size = int(header.decode("ascii"))
        payload = recv_all(sock, size)
        if len(payload) < size:
            raise ConnectionError("incomplete frame payload")
        return payload

    def parse_control_line(line):
        parts = line.split()
        if not parts:
            return None, []
        return parts[0].upper(), parts[1:]

    def send_status(sock, status):
        send_all(sock, (status + "\n").encode("utf-8"))

    def recv_control_line(sock):
        buf = b""
        while not buf.endswith(b"\n"):
            ch = sock.recv(1)
            if not ch:
                return None
            buf += ch
        return buf.decode("utf-8", errors="replace").strip()


# Person A / Person D will replace the stubs inside server_handlers.py.
from server_handlers import handle_ls, handle_get, handle_put


# ---------------------------------------------------------------------------
# Per-session control loop
# ---------------------------------------------------------------------------
def handle_client(control_sock, client_addr):
    print(f"[serv.py] session start client={client_addr}")
    try:
        while True:
            line = recv_control_line(control_sock)
            if line is None:
                print(f"[serv.py] control EOF client={client_addr}")
                return
            if not line:
                continue

            cmd, args = parse_control_line(line)
            print(f"[serv.py] recv cmd={cmd} args={args} client={client_addr}")

            if cmd == "QUIT":
                send_status(control_sock, "200 BYE")
                print(f"[serv.py] QUIT SUCCESS client={client_addr}")
                return

            elif cmd == "LS":
                if len(args) != 1:
                    send_status(control_sock, "500 ERROR usage: LS <data_port>")
                    print(f"[serv.py] LS FAILURE bad args client={client_addr}")
                    continue
                try:
                    data_port = int(args[0])
                except ValueError:
                    send_status(control_sock, "500 ERROR invalid data port")
                    print(f"[serv.py] LS FAILURE bad port client={client_addr}")
                    continue
                handle_ls(control_sock, client_addr, data_port)

            elif cmd == "GET":
                if len(args) != 2:
                    send_status(control_sock, "500 ERROR usage: GET <filename> <data_port>")
                    print(f"[serv.py] GET FAILURE bad args client={client_addr}")
                    continue
                filename, port_str = args
                try:
                    data_port = int(port_str)
                except ValueError:
                    send_status(control_sock, "500 ERROR invalid data port")
                    print(f"[serv.py] GET FAILURE bad port client={client_addr}")
                    continue
                handle_get(control_sock, client_addr, filename, data_port)

            elif cmd == "PUT":
                if len(args) != 2:
                    send_status(control_sock, "500 ERROR usage: PUT <filename> <data_port>")
                    print(f"[serv.py] PUT FAILURE bad args client={client_addr}")
                    continue
                filename, port_str = args
                try:
                    data_port = int(port_str)
                except ValueError:
                    send_status(control_sock, "500 ERROR invalid data port")
                    print(f"[serv.py] PUT FAILURE bad port client={client_addr}")
                    continue
                handle_put(control_sock, client_addr, filename, data_port)

            else:
                send_status(control_sock, f"500 ERROR unknown command: {cmd}")
                print(f"[serv.py] {cmd} FAILURE unknown command client={client_addr}")

    except Exception:
        print(f"[serv.py] session exception client={client_addr}")
        traceback.print_exc()
    finally:
        try:
            control_sock.close()
        except OSError:
            pass
        print(f"[serv.py] session end client={client_addr}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main():
    if len(sys.argv) != 2:
        print("Usage: python3 serv.py <PORT>")
        sys.exit(1)

    try:
        port = int(sys.argv[1])
        if not (1 <= port <= 65535):
            raise ValueError
    except ValueError:
        print(f"Invalid port: {sys.argv[1]}")
        sys.exit(1)

    welcome_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    welcome_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    welcome_sock.bind(("", port))
    welcome_sock.listen(5)

    print(f"[serv.py] FTP server listening on port {port}")
    print(f"[serv.py] using {'shared' if USING_SHARED_COMMON else 'fallback'} ftp_common")

    try:
        while True:
            control_sock, client_addr = welcome_sock.accept()
            threading.Thread(
                target=handle_client,
                args=(control_sock, client_addr),
                daemon=True,
            ).start()
    except KeyboardInterrupt:
        print("\n[serv.py] shutting down")
    finally:
        welcome_sock.close()


if __name__ == "__main__":
    main()