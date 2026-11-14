import socket
import threading

from ftp_common import recv_control_line, recv_frame, send_frame
from server_handlers import handle_put


def test_server_put_receives_binary_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    content = bytes(range(256)) * 400
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        listener.settimeout(5)

        server_control, client_control = socket.socketpair()
        server_control.settimeout(5)
        client_control.settimeout(5)
        failures = []

        def run_handler():
            try:
                handle_put(
                    server_control,
                    ("127.0.0.1", 1),
                    "uploaded.bin",
                    listener.getsockname()[1],
                )
            except Exception as error:
                failures.append(error)
            finally:
                server_control.close()

        thread = threading.Thread(target=run_handler, daemon=True)
        thread.start()
        data, _ = listener.accept()
        with data:
            assert recv_control_line(client_control) == "150 OK"
            for offset in range(0, len(content), 65536):
                send_frame(data, content[offset:offset + 65536])

        assert recv_control_line(client_control) == f"226 COMPLETE {len(content)}"
        thread.join(timeout=5)
        assert not thread.is_alive()
        assert failures == []
        assert (tmp_path / "uploaded.bin").read_bytes() == content
        client_control.close()
