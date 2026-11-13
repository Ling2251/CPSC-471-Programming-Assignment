"""Person A's LS command, ready for Person C's future client control loop."""

import socket
import sys

from ftp_common import format_control_line, recv_control_line, recv_frame, send_all


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

# control_sock : connection already open to the server
# filename : the name of the file the user wants to download
# timeout : how long a socket operation can wait before giving up
def do_get(control_sock, filename, *, timeout=10.0) : 
    # download filename from the server using an existing control connection
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener :        # create TCP socket
        listener.settimeout(timeout)
        listener.bind((control_sock.getsockname()[0], 0))                       # asks the operating system to choose an available port (local IP address)
        listener.listen(1)                                                      # waiting for the socket to accept connection

        port = listener.getsockname()[1]                                        # makes sure the listener is closed when you're done
        print(f"Listening for file data on port {port}")

        command = format_control_line("GET", filename, port)
        send_all(control_sock, command.encode("utf-8"))

        status = recv_control_line(control_sock)

        if status is not None and status.startswith("500 ERROR ") : 
            raise RuntimeError(status)

        if status != "150 OK" :
            raise ValueError (f"Expected 150 OK, received {status!r}")
