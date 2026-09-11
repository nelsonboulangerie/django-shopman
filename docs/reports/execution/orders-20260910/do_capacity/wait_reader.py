"""Bounded preparation check; never request business data or arbitrary hosts."""
import socket
import sys
import time

port = int(sys.argv[1])
assert port in {8016, 3005}
deadline = time.monotonic() + 60
while True:
    with socket.socket() as connection:
        if connection.connect_ex(('127.0.0.1', port)) == 0:
            break
    if time.monotonic() >= deadline:
        raise RuntimeError(f'Isolated reader preparation failed on {port}')
    time.sleep(.2)
