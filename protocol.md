# Simplified FTP protocol

The persistent IPv4 TCP control connection carries UTF-8 lines terminated by LF
(`\n`). Receivers also accept CRLF. No greeting is sent. One command completes
before the next is issued. Commands are case insensitive; arguments are split
on whitespace, so filenames containing spaces are not supported.

| Command | Meaning |
| --- | --- |
| `LS <data_port>` | List the server process's current directory |
| `GET <filename> <data_port>` | Download a file |
| `PUT <filename> <data_port>` | Upload a file |
| `QUIT` | End the control session |

Data ports must be integers from 1 to 65535. GET is implemented by Person B;
PUT currently remains Person D's server stub. The future client loop and PUT
client belong to Person C; the GET client belongs to Person D.

## Connection and status ordering

1. The client binds and listens on its local IPv4 address and an ephemeral port.
2. It sends the command including that port over control.
3. The server prepares the source and connects to the control peer's IP at that
   port. This is an active data connection, including for PUT.
4. The server sends `150 OK` only after connecting. The client reads this status
   before accepting the queued connection, so an initial error never requires
   an accept. The listening backlog allows this ordering.
5. The sender transfers zero or more frames and closes the data connection.
6. The server sends `226 COMPLETE <bytes>` after data closes. Bytes counts only
   payload bytes, excluding headers; the receiver checks the count.

`500 ERROR <reason>` reports a failure, either before 150 or during a transfer.
The reason occupies one line. A client must not report success without a valid
226 and matching byte count. `QUIT` returns `200 BYE` and closes control.
Unknown commands and incorrect arguments return 500. Existing serv.py accepts
extra QUIT arguments and checks port syntax but not range; LS checks range.

## Binary data framing and EOF

Each frame is exactly ten ASCII decimal digits, zero padded, followed by that
many raw payload bytes. Example: `0000000003` followed by `abc`. Frames may be
split across any number of TCP reads/writes. GET and LS send chunks of at most
65536 payload bytes; the framing itself permits lengths up to 9999999999.
Receivers accumulate incrementally; the current helpers return whole frames
and do not impose a smaller size limit, so use trusted peers.

EOF between frames ends a transfer. There is no end-marker frame. An empty
frame (`0000000000`) returns `b''` and does not mean EOF; `recv_frame()` returns
`None` only for clean EOF. EOF in a header or payload raises ConnectionError.
Non-digit headers raise ValueError. Empty transfers may send no frames.

Control EOF between lines returns None; EOF inside a line raises
ConnectionError. Invalid UTF-8, embedded delimiters/NUL, and lines exceeding
65536 wire bytes are rejected. Blank lines parse as `(None, [])` and the
existing server ignores them. Parsing returns `(uppercase_token, args)` and
does not enforce command arity, which is the control loop's responsibility.

## LS and shared interfaces

LS returns UTF-8 `ls -l` output (default hidden-file exclusion). If no `ls`
executable exists, a Python fallback lists mode, link count, numeric owner/group,
size, modification time, and name. The fallback omits the Unix block-total line;
Windows permissions and ownership metadata differ from Unix. A failed existing
ls executable produces 500 rather than silently switching formats.

`do_ls(control_sock, *, output=None, timeout=10.0)` takes an already-connected
IPv4 control socket, prints to output (default stdout), and returns listing text.
Person C can call it for the interactive `ls` command. It does not create a
control connection or implement the prompt. Catch RuntimeError for a received
500 (control remains usable), and OSError/ConnectionError/ValueError for local
or protocol failures (control closes to avoid reusing an uncertain stream).
The previous control timeout is restored after a synchronized exchange.

Shared signatures:

- `send_all(sock, data)` returns bytes sent, raising on socket failure.
- `recv_all(sock, num_bytes)` returns up to that many bytes; short means EOF.
- `send_frame(sock, payload)` sends a bytes-like payload.
- `recv_frame(sock)` returns payload bytes or None as described above.
- `parse_control_line(line)` takes text and returns token plus argument list.
- `format_control_line(command, *args)` returns newline-terminated text.
- `send_status(sock, status)` sends a full status string as UTF-8.
- `recv_control_line(sock)` returns text without the terminator or None.

Sockets are blocking unless their caller sets a timeout. LS uses ten-second
timeouts by default. The shared module exports every name imported by serv.py,
so Person B's loop and GET automatically use it without edits. No authentication,
encryption, or sandbox for filesystem access is provided by this course protocol.
