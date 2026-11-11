import io
import socket
import threading
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import serv
from client_commands import do_ls
from ftp_common import recv_control_line, recv_frame, send_all, send_status
from server_handlers import handle_ls


class LSTests(unittest.TestCase):
    def start_session(self, handler=serv.handle_client):
        """Use real IPv4 TCP so active data connections match production."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind(('127.0.0.1', 0))
            listener.listen(1)
            client = socket.create_connection(listener.getsockname(), timeout=2)
            server, address = listener.accept()
        client.settimeout(2)
        server.settimeout(2)
        failures = []

        def run():
            try:
                with server:
                    handler(server, address)
            except Exception as error:
                failures.append(error)

        thread = threading.Thread(target=run, daemon=True)
        thread.start()

        def cleanup():
            client.close()
            thread.join(3)
            self.assertFalse(thread.is_alive(), 'server thread did not finish')
            self.assertEqual(failures, [])
        self.addCleanup(cleanup)
        return client

    def quit(self, client):
        send_all(client, b'QUIT\n')
        self.assertEqual(recv_control_line(client), '200 BYE')

    def test_real_listing_and_repeated_ls(self):
        self.assertTrue(serv.USING_SHARED_COMMON)
        client = self.start_session()
        for _ in range(2):
            output = io.StringIO()
            text = do_ls(client, output=output, timeout=2)
            self.assertIn('server_handlers.py', text)
            self.assertEqual(output.getvalue(), text)
            self.assertEqual(client.gettimeout(), 2)
        self.quit(client)

    def test_windows_fallback(self):
        with patch('server_handlers.shutil.which', return_value=None):
            client = self.start_session()
            text = do_ls(client, output=io.StringIO(), timeout=2)
            self.assertIn('server_handlers.py', text)
            self.quit(client)

    def test_existing_get_with_shared_helpers(self):
        # Exercise Person B's unchanged handler with empty and multi-frame data.
        for payload in (b'', bytes(range(256)) * 300):
            with self.subTest(size=len(payload)), tempfile.TemporaryDirectory() as directory:
                filename = 'sample.bin'
                with open(f'{directory}/{filename}', 'wb') as file:
                    file.write(payload)
                client = self.start_session()
                # Patch only file lookup so Windows temp paths with spaces do
                # not run into the protocol's existing filename restriction.
                real_open = open
                def open_sample(name, mode):
                    return real_open(f'{directory}/{name}', mode)
                with patch('server_handlers.open', side_effect=open_sample, create=True):
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
                        listener.settimeout(2)
                        listener.bind(('127.0.0.1', 0))
                        listener.listen(1)
                        send_all(client, f'GET {filename} {listener.getsockname()[1]}\n'.encode())
                        self.assertEqual(recv_control_line(client), '150 OK')
                        data, _ = listener.accept()
                        result = bytearray()
                        with data:
                            data.settimeout(2)
                            while True:
                                frame = recv_frame(data)
                                if frame is None:
                                    break
                                result.extend(frame)
                        self.assertEqual(result, payload)
                        self.assertEqual(recv_control_line(client),
                                         f'226 COMPLETE {len(payload)}')
                self.quit(client)

    def test_empty_and_multiframe_listing(self):
        for listing in ('', 'example.txt\n' * 10000, 'caf\u00e9.txt\n'):
            with self.subTest(length=len(listing)), \
                    patch('server_handlers.shutil.which', return_value='ls'), \
                    patch('server_handlers.subprocess.run',
                          return_value=SimpleNamespace(stdout=listing)):
                client = self.start_session()
                self.assertEqual(do_ls(client, output=io.StringIO(), timeout=2), listing)
                self.quit(client)

    def test_listing_error_preserves_control(self):
        with patch('server_handlers.shutil.which', side_effect=OSError('listing failed')):
            client = self.start_session()
            with self.assertRaisesRegex(RuntimeError, '500 ERROR listing failed'):
                do_ls(client, output=io.StringIO(), timeout=2)
            self.quit(client)

    def test_invalid_port_and_connect_failure(self):
        for port in (0, 65536):
            left, right = socket.socketpair()
            with left, right:
                handle_ls(left, ('127.0.0.1', 1), port)
                self.assertIn('500 ERROR', recv_control_line(right))
        with patch('server_handlers.socket.create_connection',
                   side_effect=OSError('connection refused')):
            left, right = socket.socketpair()
            with left, right:
                handle_ls(left, ('127.0.0.1', 1), 1234)
                self.assertIn('500 ERROR', recv_control_line(right))

    def test_malformed_transfer_closes_control(self):
        cases = [
            (b'notdigits!', None),
            (b'000', None),
            (b'0000000003ab', None),
            (b'0000000001a', '226 COMPLETE 2'),
            (b'', '226 COMPLETE nope'),
            (b'', None),
            (b'0000000001\xff', '226 COMPLETE 1'),
        ]
        for wire, final in cases:
            with self.subTest(wire=wire, final=final):
                def fake_server(control, address):
                    port = int(recv_control_line(control).split()[1])
                    with socket.create_connection((address[0], port), timeout=2) as data:
                        send_status(control, '150 OK')
                        send_all(data, wire)
                    if final:
                        send_status(control, final)
                client = self.start_session(fake_server)
                with self.assertRaises((ValueError, ConnectionError)):
                    do_ls(client, output=io.StringIO(), timeout=2)
                self.assertEqual(client.fileno(), -1)

    def test_transfer_error_status(self):
        def fake_server(control, address):
            port = int(recv_control_line(control).split()[1])
            with socket.create_connection((address[0], port), timeout=2):
                send_status(control, '150 OK')
            send_status(control, '500 ERROR transfer failed')
            self.assertEqual(recv_control_line(control), 'QUIT')
            send_status(control, '200 BYE')
        client = self.start_session(fake_server)
        with self.assertRaisesRegex(RuntimeError, 'transfer failed'):
            do_ls(client, output=io.StringIO(), timeout=2)
        self.quit(client)


if __name__ == '__main__':
    unittest.main()
