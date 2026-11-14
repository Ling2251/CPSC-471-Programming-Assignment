import socket
import threading

import pytest

import cli
from client_commands import do_get
from ftp_common import recv_control_line, send_frame, send_status


def start_mock_server(payload=None):
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
                    command = recv_control_line(control).split()
                    assert command[0] == "GET"
                    assert len(command) == 3

                    if payload is None:
                        send_status(control, "500 ERROR file unavailable")
                        assert recv_control_line(control) == "QUIT"
                        send_status(control, "200 BYE")
                        return

                    with socket.create_connection(
                        ("127.0.0.1", int(command[2])), timeout=5
                    ) as data:
                        send_status(control, "150 OK")
                        for offset in range(0, len(payload), 65536):
                            send_frame(data, payload[offset:offset + 65536])

                    send_status(control, f"226 COMPLETE {len(payload)}")
        except Exception as error:
            errors.append(error)
            ready.set()

    thread = threading.Thread(target=server, daemon=True)
    thread.start()
    assert ready.wait(timeout=5), "Mock server failed to start"
    if errors:
        raise errors[0]
    return result["port"], thread, errors


@pytest.mark.parametrize(
    "payload",
    [b"", bytes(range(256)) * 400],
    ids=["empty", "multiframe"],
)
def test_get_downloads_binary_file(tmp_path, monkeypatch, payload):
    monkeypatch.chdir(tmp_path)
    port, thread, errors = start_mock_server(payload)

    with socket.create_connection(("127.0.0.1", port), timeout=5) as control:
        assert do_get(control, "download.bin", timeout=5) == len(payload)

    thread.join(timeout=5)
    assert not thread.is_alive()
    assert not errors
    assert (tmp_path / "download.bin").read_bytes() == payload


def test_get_server_error_preserves_control_connection():
    port, thread, errors = start_mock_server()

    with socket.create_connection(("127.0.0.1", port), timeout=5) as control:
        with pytest.raises(RuntimeError, match="file unavailable"):
            do_get(control, "missing.bin", timeout=5)
        control.sendall(b"QUIT\n")
        assert recv_control_line(control) == "200 BYE"

    thread.join(timeout=5)
    assert not thread.is_alive()
    assert not errors


def test_cli_dispatches_get(monkeypatch, capsys):
    class FakeControl:
        def __init__(self):
            self.commands = bytearray()
            self.response = bytearray(b"200 BYE\n")

        def send(self, data):
            self.commands.extend(data)
            return len(data)

        def recv(self, size):
            result = bytes(self.response[:size])
            del self.response[:size]
            return result

        def close(self):
            pass

    control = FakeControl()
    calls = []
    commands = iter(["get remote.bin", "quit"])
    monkeypatch.setattr(cli.socket, "create_connection", lambda *args, **kwargs: control)
    monkeypatch.setattr(cli, "do_get", lambda sock, filename: calls.append((sock, filename)))
    monkeypatch.setattr("builtins.input", lambda prompt: next(commands))
    monkeypatch.setattr("sys.argv", ["cli.py", "localhost", "2121"])

    cli.main()

    assert calls == [(control, "remote.bin")]
    assert b"QUIT\n" in control.commands
    assert "200 BYE" in capsys.readouterr().out
