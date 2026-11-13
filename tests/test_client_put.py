
import socket
import threading

import pytest

from client_commands import do_put
from ftp_common import recv_control_line, recv_frame, send_status


def start_mock_server():
    """Start a simulated FTP server for testing PUT."""

    ready = threading.Event()
    result = {}
    errors = []

    def server():
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
                listener.bind(("127.0.0.1", 0))
                listener.listen(1)
                listener.settimeout(5)

                result["port"] = listener.getsockname()[1]
                ready.set()

                with listener.accept()[0] as control:
                    control.settimeout(5)
                    command = recv_control_line(control)
                    parts = command.split()

                    assert parts[0] == "PUT"
                    assert len(parts) == 3

                    data_port = int(parts[2])

                    with socket.create_connection(
                        ("127.0.0.1", data_port), timeout=5
                    ) as data_sock:
                        send_status(control, "150 OK")

                        received = bytearray()

                        while True:
                            frame = recv_frame(data_sock)
                            if frame is None:
                                break
                            received.extend(frame)

                    result["filename"] = parts[1]
                    result["data"] = bytes(received)

                    send_status(
                        control,
                        f"226 COMPLETE {len(received)}"
                    )

        except Exception as e:
            errors.append(e)
            ready.set()

    thread = threading.Thread(target=server, daemon=True)
    thread.start()

    assert ready.wait(timeout=5), "Mock server failed to start"
    if errors:
        raise errors[0]

    return result["port"], thread, result, errors


def test_put_normal_file(tmp_path, monkeypatch):
    """Test uploading a small text file."""

    file = tmp_path / "hello.txt"
    content = b"Hello from Person C!"
    file.write_bytes(content)

    monkeypatch.chdir(tmp_path)

    port, thread, result, errors = start_mock_server()

    with socket.create_connection(("127.0.0.1", port)) as control:
        uploaded = do_put(control, file.name)

    thread.join(timeout=5)

    assert not thread.is_alive()
    assert not errors
    assert uploaded == len(content)
    assert result["data"] == content


def test_put_missing_file(tmp_path):
    """Test uploading a file that does not exist."""

    missing = tmp_path / "missing.txt"

    with pytest.raises(FileNotFoundError):
        do_put(None, str(missing))


def test_put_large_file(tmp_path, monkeypatch):
    """Test uploading a file larger than 64 KB."""

    file = tmp_path / "large.bin"
    content = bytes(range(256)) * 400
    file.write_bytes(content)

    monkeypatch.chdir(tmp_path)

    port, thread, result, errors = start_mock_server()

    with socket.create_connection(("127.0.0.1", port)) as control:
        uploaded = do_put(control, file.name)

    thread.join(timeout=5)

    assert not thread.is_alive()
    assert not errors
    assert uploaded == len(content)
    assert result["data"] == content
