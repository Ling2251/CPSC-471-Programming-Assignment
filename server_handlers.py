"""
server_handlers.py — server-side command handlers

Person B owns `handle_get` (complete).
Person A will replace `handle_ls` stub.
Person D will replace `handle_put` stub.
"""

import socket

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
# handle_ls — STUB (Person A will implement)
# ===========================================================================
def handle_ls(control_sock, client_addr, data_port):
    # TODO(Person A): run `ls -l`, connect to (client_addr[0], data_port),
    #                 send output as framed data, close data socket,
    #                 send "226 COMPLETE <bytes>".
    send_status(control_sock, "500 ERROR LS not implemented yet")
    print(f"[handlers] LS FAILURE not implemented client={client_addr}")


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