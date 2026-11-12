
import socket
import sys

from client_commands import do_ls, do_put
from ftp_common import format_control_line, recv_control_line, send_all


def main():
    # Check command-line arguments
    if len(sys.argv) != 3:
        print("Usage: python cli.py <server> <port>")
        sys.exit(1)

    server = sys.argv[1]

    try:
        port = int(sys.argv[2])
        if not 1 <= port <= 65535:
            raise ValueError
    except ValueError:
        print("Error: Invalid port number")
        sys.exit(1)

    # Establish TCP control connection
    try:
        control_sock = socket.create_connection(
            (server, port), timeout=10
        )

    except socket.gaierror:
        print(f"Error: Could not resolve server hostname '{server}'")
        sys.exit(1)

    except ConnectionRefusedError:
        print(f"Error: Connection refused by {server}:{port}")
        sys.exit(1)

    except socket.timeout:
        print(f"Error: Connection to {server}:{port} timed out")
        sys.exit(1)

    except OSError as e:
        print(f"Error: Could not connect to server: {e}")
        sys.exit(1)

    print(f"Connected to {server}:{port}")

    # Keep control connection open for multiple commands
    try:
        while True:
            try:
                user_input = input("ftp> ").strip()
            except EOFError:
                user_input = "quit"

            if not user_input:
                continue

            parts = user_input.split()
            command = parts[0].lower()
            args = parts[1:]

            # LS - List server directory
            if command == "ls":
                if args:
                    print("Usage: ls")
                    continue

                try:
                    do_ls(control_sock)
                except RuntimeError as e:
                    print(f"LS failed: {e}")

            # GET - Download file from server
            elif command == "get":
                if len(args) != 1:
                    print("Usage: get <filename>")
                    continue

                # Person D will implement do_get()
                print("GET is not implemented yet.")

            # PUT - Upload local file to server
            elif command == "put":
                if len(args) != 1:
                    print("Usage: put <filename>")
                    continue

                try:
                    do_put(control_sock, args[0])

                except FileNotFoundError as e:
                    print(f"Error: {e}")

                except RuntimeError as e:
                    print(f"Upload failed: {e}")

            # QUIT - Disconnect from server
            elif command == "quit":
                if args:
                    print("Usage: quit")
                    continue

                send_all(
                    control_sock,
                    format_control_line("QUIT").encode("utf-8")
                )

                response = recv_control_line(control_sock)

                if response == "200 BYE":
                    print("200 BYE")
                else:
                    print(f"Unexpected server response: {response}")

                break

            # Unknown command
            else:
                print(f"Unknown command: {command}")

    except (OSError, ConnectionError, ValueError) as e:
        print(f"Connection or protocol error: {e}")
        print("FTP session terminated.")

    except KeyboardInterrupt:
        print("\nClient interrupted.")

    finally:
        control_sock.close()
        print("Disconnected from server.")


if __name__ == "__main__":
    main()
