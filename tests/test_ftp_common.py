import socket
import unittest

from ftp_common import (
    send_all, recv_all, send_frame, recv_frame, parse_control_line,
    format_control_line, send_status, recv_control_line, MAX_CONTROL_BYTES,
)


class PartialSocket:
    """Force fragmented TCP-like reads and writes without timing assumptions."""
    def __init__(self, data=b''):
        self.data = bytearray(data)
        self.sent = bytearray()

    def send(self, data):
        count = min(2, len(data))
        self.sent.extend(data[:count])
        return count

    def recv(self, count):
        result = bytes(self.data[:min(count, 2)])
        del self.data[:len(result)]
        return result


class CommonTests(unittest.TestCase):
    def test_partial_binary_round_trip(self):
        payload = bytes(range(256)) * 4
        sender = PartialSocket()
        send_frame(sender, payload)
        self.assertEqual(sender.sent[:10], b'0000001024')
        receiver = PartialSocket(sender.sent)
        self.assertEqual(recv_frame(receiver), payload)
        self.assertIsNone(recv_frame(receiver))

    def test_empty_frame_is_not_eof(self):
        sender = PartialSocket()
        send_frame(sender, b'')
        receiver = PartialSocket(sender.sent)
        self.assertEqual(recv_frame(receiver), b'')
        self.assertIsNone(recv_frame(receiver))

    def test_multiple_frames(self):
        receiver = PartialSocket(b'0000000001a0000000001b')
        self.assertEqual(recv_frame(receiver), b'a')
        self.assertEqual(recv_frame(receiver), b'b')

    def test_bad_and_truncated_frames(self):
        for header in (b'-000000001', b'00000000 1', b'xxxxxxxxxx'):
            with self.subTest(header=header), self.assertRaises(ValueError):
                recv_frame(PartialSocket(header))
        for data in (b'000', b'0000000003ab'):
            with self.subTest(data=data), self.assertRaises(ConnectionError):
                recv_frame(PartialSocket(data))

    def test_recv_all_eof_and_zero(self):
        self.assertEqual(recv_all(PartialSocket(b'ab'), 4), b'ab')
        self.assertEqual(recv_all(PartialSocket(), 0), b'')
        with self.assertRaises(ValueError):
            recv_all(PartialSocket(), -1)

    def test_closed_send(self):
        class Closed(PartialSocket):
            def send(self, data):
                return 0
        with self.assertRaises(ConnectionError):
            send_all(Closed(), b'x')

    def test_control_format_and_parse(self):
        self.assertEqual(format_control_line('LS', 1234), 'LS 1234\n')
        self.assertEqual(parse_control_line(' get file 1234\r\n'),
                         ('GET', ['file', '1234']))
        self.assertEqual(parse_control_line('  '), (None, []))
        self.assertEqual(parse_control_line('BOGUS'), ('BOGUS', []))
        for text in ('LS\nQUIT', 'LS\x00', 'LS\rQUIT', 'LS\n\n', 'LS\r\r\n'):
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    parse_control_line(text)
                with self.assertRaises(ValueError):
                    format_control_line(text)

    def test_control_lines_and_status_over_socket(self):
        left, right = socket.socketpair()
        with left, right:
            left.settimeout(2)
            right.settimeout(2)
            send_status(left, '150 OK')
            send_all(left, b'  \t\n')
            send_all(left, b'226 COMPLETE 0\r\n')
            left.shutdown(socket.SHUT_WR)
            self.assertEqual(recv_control_line(right), '150 OK')
            self.assertEqual(recv_control_line(right), '')
            self.assertEqual(recv_control_line(right), '226 COMPLETE 0')
            self.assertIsNone(recv_control_line(right))

    def test_malformed_control(self):
        for data, error in ((b'LS', ConnectionError), (b'\xff\n', UnicodeError),
                            (b'LS\x00\n', ValueError),
                            (b'LS\r\r\n', ValueError),
                            (b'x' * MAX_CONTROL_BYTES, ValueError)):
            with self.subTest(data=data[:10]), self.assertRaises(error):
                recv_control_line(PartialSocket(data))


if __name__ == '__main__':
    unittest.main()
