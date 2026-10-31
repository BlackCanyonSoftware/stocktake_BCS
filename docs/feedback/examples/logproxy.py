"""Tiny CONNECT proxy on 127.0.0.1:PORT that logs the requested host and then either refuses (mode=refuse) or tunnels (mode=pass).
usage: logproxy.py PORT MODE LOGFILE"""
import select
import socket
import sys
import threading

port, mode, logfile = int(sys.argv[1]), sys.argv[2], sys.argv[3]
lock = threading.Lock()


def log(s):
    with lock, open(logfile, "a") as f:
        f.write(s + "\n")


def handle(c):
    try:
        data = b""
        while b"\r\n\r\n" not in data:
            chunk = c.recv(4096)
            if not chunk:
                return
            data += chunk
        first = data.split(b"\r\n")[0].decode()
        log(first)
        if mode == "hang":
            import time
            time.sleep(300)
            return
        if mode == "refuse" or not first.startswith("CONNECT"):
            c.sendall(b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\n\r\n")
            return
        host, p = first.split()[1].rsplit(":", 1)
        up = socket.create_connection((host, int(p)), timeout=20)
        c.sendall(b"HTTP/1.1 200 Connection established\r\n\r\n")
        socks = [c, up]
        while True:
            r, _, _ = select.select(socks, [], [], 30)
            if not r:
                break
            for s in r:
                d = s.recv(65536)
                if not d:
                    return
                (up if s is c else c).sendall(d)
    except Exception as e:  # noqa: BLE001
        log(f"error {e}")
    finally:
        c.close()


srv = socket.socket()
srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind(("127.0.0.1", port))
srv.listen(50)
while True:
    conn, _ = srv.accept()
    threading.Thread(target=handle, args=(conn,), daemon=True).start()
