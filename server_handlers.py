"""
server_handlers.py — server-side command handlers

Person B owns `handle_get` (complete).
Person A will replace `handle_ls` stub.
Person D will replace `handle_put` stub.
"""

import socket
import os
import shutil
import stat
import subprocess
from datetime import datetime

# Prefer Person A's ftp_common helpers; fall back to local ones
try:
    from ftp_common import send_all, send_frame, send_status
except ImportError:
    def send_all(sock, data):
        total = 0
        while total < len(data):
            sent = sock.send(data[total:])
            if sent == 0:
                raise ConnectionError("socket closed during send_all")
            total += sent
        return total

    def send_frame(sock, payload):
        header = str(len(payload)).zfill(10).encode("ascii")
        send_all(sock, header + payload)

    def send_status(sock, status):
        send_all(sock, (status + "\n").encode("utf-8"))


# ===========================================================================
# handle_ls — Person A's implementation
# ===========================================================================
def handle_ls(control_sock, client_addr, data_port):
    """Send the current directory's long listing over an active data connection."""
    try:
        if not 1 <= int(data_port) <= 65535:
            raise ValueError("invalid data port")
        ls_path = shutil.which("ls")
        if ls_path:
            result = subprocess.run(
                [ls_path, "-l"], capture_output=True, text=True,
                errors="replace", check=True, timeout=10,
            )
            listing = result.stdout
        else:
            # Windows may have no ls executable. Keep long-listing information
            # using Python; numeric IDs/permissions are platform dependent.
            lines = []
            with os.scandir(".") as entries:
                for entry in sorted(entries, key=lambda item: item.name):
                    if entry.name.startswith("."):
                        continue
                    info = entry.stat(follow_symlinks=False)
                    modified = datetime.fromtimestamp(info.st_mtime).strftime("%b %d %H:%M")
                    lines.append(
                        f"{stat.filemode(info.st_mode)} {info.st_nlink} "
                        f"{info.st_uid} {info.st_gid} {info.st_size:>8} "
                        f"{modified} {entry.name}\n"
                    )
            listing = "".join(lines)
        payload = listing.encode("utf-8")
        # Match GET: connect before 150, close data before 226.
        with socket.create_connection((client_addr[0], int(data_port)), timeout=10) as data_sock:
            send_status(control_sock, "150 OK")
            for offset in range(0, len(payload), 65536):
                send_frame(data_sock, payload[offset:offset + 65536])
        send_status(control_sock, f"226 COMPLETE {len(payload)}")
        print(f"[handlers] LS SUCCESS {len(payload)} bytes client={client_addr}")
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        # Exception text must stay on one control line.
        reason = " ".join(str(error).split()) or type(error).__name__
        try:
            send_status(control_sock, f"500 ERROR {reason}")
        except OSError:
            pass
        print(f"[handlers] LS FAILURE {reason} client={client_addr}")


# ===========================================================================
# handle_get — Person B's implementation (complete)
# ===========================================================================
def handle_get(control_sock, client_addr, filename, data_port):
    """
    Serve GET <filename> <data_port>.

    Flow:
      1. Open file "rb" → on error send 500, no data connection.
      2. Connect to (client_ip, data_port) → on error send 500.
      3. Send 150 OK.
      4. Stream 64 KB chunks with `send_frame`.
      5. Close data socket.
      6. Send "226 COMPLETE <bytes>".
    """
    data_sock = None
    file_obj = None
    try:
        # 1) open file first
        try:
            file_obj = open(filename, "rb")
        except OSError as e:
            send_status(control_sock, f"500 ERROR cannot open {filename}: {e.strerror}")
            print(f"[handlers] GET FAILURE {filename} open error: {e}")
            return

        # 2) connect to client's data port BEFORE 150 OK
        try:
            data_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            data_sock.settimeout(10.0)
            data_sock.connect((client_addr[0], int(data_port)))
        except (OSError, ValueError) as e:
            send_status(control_sock, f"500 ERROR data connect failed: {e}")
            print(f"[handlers] GET FAILURE {filename} data connect: {e}")
            return

        # 3) now announce readiness
        send_status(control_sock, "150 OK")

        # 4) stream frames
        total = 0
        while True:
            chunk = file_obj.read(65536)
            if not chunk:
                break
            send_frame(data_sock, chunk)
            total += len(chunk)

        # 5) close data socket first so client sees EOF before 226
        try:
            data_sock.close()
        finally:
            data_sock = None

        # 6) final status on control channel
        send_status(control_sock, f"226 COMPLETE {total}")
        print(f"[handlers] GET SUCCESS {filename} {total} bytes client={client_addr}")

    except Exception as e:
        try:
            send_status(control_sock, f"500 ERROR {e}")
        except OSError:
            pass
        print(f"[handlers] GET FAILURE {filename}: {e}")

    finally:
        if file_obj is not None:
            try:
                file_obj.close()
            except OSError:
                pass
        if data_sock is not None:
            try:
                data_sock.close()
            except OSError:
                pass


# ===========================================================================
# handle_put — STUB (Person D will implement)
# ===========================================================================
def handle_put(control_sock, client_addr, filename, data_port):
    # TODO(Person D): connect to (client_addr[0], data_port), receive frames
    #                 until EOF, write file "wb", close data socket,
    #                 send "226 COMPLETE <bytes>".
    send_status(control_sock, "500 ERROR PUT not implemented yet")
    print(f"[handlers] PUT FAILURE not implemented client={client_addr}")