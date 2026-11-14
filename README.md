# CPSC-471 Programming Assignment

## Team members

- Peijun Zhao, Pzhoa1@csu.fullerton.edu
- Brandon Wu, wubstuff@csu.fullerton.edu
- Jovanna De La Trinidad, jovannadlt@csu.fullerton.edu
- Kamilo Ramirez, KamiloR7@csu.fullerton.edu
## Language

Python

## Running the server and client

From this directory, start the server:

```text
python serv.py 2121
```

In another terminal, connect the client:

```text
python cli.py localhost 2121
```

The client prompt supports `ls`, `get <filename>`, `put <filename>`, and
`quit`. File transfers use a separate active data connection for each
operation. The server reads and writes files in its current working directory;
the client reads and writes transfer files in its current working directory.
Filenames cannot contain whitespace.

## Protocol and tests

The control messages, data framing, and transfer ordering are documented in
[protocol.md](protocol.md).

Run the test suite with:

```text
python -m pytest -q
```

