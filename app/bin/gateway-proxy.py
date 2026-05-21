#!/usr/bin/env python3
import http.server, socket, sys, os, signal, re, time, threading, gzip, zlib, select, json
from http.client import HTTPConnection

SOCK_PATH = sys.argv[1]
TARGET_HOST = sys.argv[2]
INITIAL_PORT = int(sys.argv[3])
CONFIG_PATH = sys.argv[4] if len(sys.argv) > 4 else None
PREFIX = "/app/transmission"

_current_port = INITIAL_PORT
_port_check_time = 0
_port_lock = threading.Lock()

INJECT_SCRIPT = b'''<script>
(function(){
var P="/app/transmission";
var _f=window.fetch;
window.fetch=function(u,o){
if(typeof u==='string'&&u.charAt(0)==='/'&&!u.startsWith(P)){u=P+u;}
return _f.call(this,u,o);
};
var _o=XMLHttpRequest.prototype.open;
XMLHttpRequest.prototype.open=function(m,u,s){
if(typeof u==='string'&&u.charAt(0)==='/'&&!u.startsWith(P)){arguments[1]=P+u;}
return _o.apply(this,arguments);
};
var _cw=window.WebSocket;
if(_cw){
window.WebSocket=function(u,p){
if(typeof u==='string'&&u.charAt(0)==='/'&&!u.startsWith(P)){
var _proto=location.protocol==='https:'?'wss:':'ws:';
u=_proto+'//'+location.host+P+u;
}
else if(typeof u==='string'&&u.startsWith('ws')){
var r=new RegExp('^(wss?)://([^/]+)(/.*)$');
var m=u.match(r);
if(m&&!m[3].startsWith(P)){u=m[1]+'://'+m[2]+P+m[3];}
}
return p?new _cw(u,p):new _cw(u);
};
window.WebSocket.prototype=_cw.prototype;
window.WebSocket.CONNECTING=_cw.CONNECTING;
window.WebSocket.OPEN=_cw.OPEN;
window.WebSocket.CLOSING=_cw.CLOSING;
window.WebSocket.CLOSED=_cw.CLOSED;
}
})();
</script>'''

def decompress(data, encoding):
    try:
        if encoding == 'gzip':
            return gzip.decompress(data)
        elif encoding == 'deflate':
            return zlib.decompress(data)
        elif encoding == 'br':
            import brotli
            return brotli.decompress(data)
    except Exception:
        pass
    return None

def rewrite_html(data, prefix):
    data = re.sub(rb'<head\b[^>]*>', lambda m: m.group(0) + INJECT_SCRIPT, data, count=1)
    p = prefix.encode()
    data = re.sub(rb'(src|href|action)=([\'"])/', rb'\1=\2' + p + rb'/', data)
    return data

def get_target_port():
    global _current_port, _port_check_time
    with _port_lock:
        now = time.time()
        if CONFIG_PATH and (now - _port_check_time) > 5:
            _port_check_time = now
            try:
                with open(CONFIG_PATH, 'r') as f:
                    try:
                        cfg = json.load(f)
                        port = cfg.get("rpc-port")
                        if port and isinstance(port, int) and port > 0:
                            _current_port = port
                    except json.JSONDecodeError:
                        pass
            except Exception:
                pass
        return _current_port

if os.path.exists(SOCK_PATH):
    os.unlink(SOCK_PATH)


def _tunnel_sock(client_sock, backend_sock):
    try:
        while True:
            r, _, _ = select.select([client_sock, backend_sock], [], [], 30)
            if not r:
                break
            for s in r:
                data = s.recv(65536)
                if not data:
                    return
                if s is client_sock:
                    backend_sock.sendall(data)
                else:
                    client_sock.sendall(data)
    except Exception:
        pass
    finally:
        try:
            client_sock.close()
        except Exception:
            pass
        try:
            backend_sock.close()
        except Exception:
            pass


class ProxyHandler(http.server.BaseHTTPRequestHandler):
    def _strip_prefix(self):
        path = self.path
        if path.startswith(PREFIX):
            path = path[len(PREFIX):] or "/"
        return path

    def _get_backend(self):
        port = get_target_port()
        return HTTPConnection(TARGET_HOST, port, timeout=30)

    def do_request(self):
        if self.path == PREFIX:
            self.send_response(301)
            self.send_header("Location", PREFIX + "/")
            self.end_headers()
            return

        upgrade = self.headers.get("Upgrade", "").lower()
        if upgrade == "websocket":
            self._handle_ws()
            return

        path = self._strip_prefix()
        conn = self._get_backend()

        headers = {}
        for key, value in self.headers.items():
            if key.lower() in ("host", "connection", "transfer-encoding", "accept-encoding"):
                continue
            headers[key] = value
        headers["Accept-Encoding"] = "gzip, deflate"

        content_length = self.headers.get("Content-Length")
        body = None
        if content_length:
            body = self.rfile.read(int(content_length))

        try:
            conn.request(self.command, path, body, headers)
            resp = conn.getresponse()
        except Exception as e:
            self.send_error(502, str(e))
            conn.close()
            return

        try:
            all_resp_headers = resp.getheaders()
            is_html = any("text/html" in v for k, v in all_resp_headers if k.lower() == "content-type")
            content_encoding = next((v for k, v in all_resp_headers if k.lower() == "content-encoding"), None)

            resp_headers = []
            for key, value in all_resp_headers:
                kl = key.lower()
                if kl == "content-encoding" and is_html:
                    continue
                if kl in ("transfer-encoding", "connection", "content-length"):
                    continue
                resp_headers.append((key, value))

            if is_html:
                data = resp.read()
                if content_encoding:
                    raw = decompress(data, content_encoding)
                    if raw is not None:
                        data = raw
                data = rewrite_html(data, PREFIX)
                self.send_response(resp.status)
                for key, value in resp_headers:
                    self.send_header(key, value)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            else:
                self.send_response(resp.status)
                for key, value in resp_headers:
                    self.send_header(key, value)
                self.end_headers()
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
        except Exception:
            pass
        finally:
            conn.close()

    def _handle_ws(self):
        path = self._strip_prefix()
        port = get_target_port()

        backend = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        backend.settimeout(10)
        try:
            backend.connect((TARGET_HOST, port))
        except Exception as e:
            backend.close()
            self.send_error(502, str(e))
            return

        ws_key = self.headers.get("Sec-WebSocket-Key", "")
        ws_ver = self.headers.get("Sec-WebSocket-Version", "13")
        ws_proto = self.headers.get("Sec-WebSocket-Protocol", "")
        origin = self.headers.get("Origin", "")

        req_line = "GET {} HTTP/1.1\r\n".format(path)
        req_line += "Host: {}:{}\r\n".format(TARGET_HOST, port)
        req_line += "Upgrade: websocket\r\n"
        req_line += "Connection: Upgrade\r\n"
        if ws_key:
            req_line += "Sec-WebSocket-Key: {}\r\n".format(ws_key)
        req_line += "Sec-WebSocket-Version: {}\r\n".format(ws_ver)
        if ws_proto:
            req_line += "Sec-WebSocket-Protocol: {}\r\n".format(ws_proto)
        if origin:
            req_line += "Origin: {}\r\n".format(origin)
        for key, value in self.headers.items():
            kl = key.lower()
            if kl in ("host", "connection", "upgrade", "sec-websocket-key",
                      "sec-websocket-version", "sec-websocket-protocol", "origin"):
                continue
            req_line += "{}: {}\r\n".format(key, value)
        req_line += "\r\n"

        try:
            backend.sendall(req_line.encode())
        except Exception as e:
            backend.close()
            self.send_error(502, str(e))
            return

        resp = b""
        while b"\r\n\r\n" not in resp:
            chunk = backend.recv(4096)
            if not chunk:
                backend.close()
                self.send_error(502, "backend closed")
                return
            resp += chunk

        hdr_end = resp.index(b"\r\n\r\n")
        hdr_raw = resp[:hdr_end].decode("utf-8", errors="replace")
        remaining = resp[hdr_end + 4:]

        status_line = hdr_raw.split("\r\n")[0]
        parts = status_line.split(" ", 2)
        status_code = int(parts[1]) if len(parts) >= 2 else 101

        resp_hdrs = []
        for line in hdr_raw.split("\r\n")[1:]:
            if ":" in line:
                k, v = line.split(":", 1)
                resp_hdrs.append((k.strip(), v.strip()))

        self.send_response(status_code)
        for k, v in resp_hdrs:
            self.send_header(k, v)
        self.end_headers()

        if remaining:
            self.wfile.write(remaining)
            self.wfile.flush()

        client_raw = self.connection
        backend.setblocking(True)
        client_raw.setblocking(True)

        t = threading.Thread(target=_tunnel_sock, args=(client_raw, backend))
        t.daemon = True
        t.start()

    def do_GET(self): self.do_request()
    def do_POST(self): self.do_request()
    def do_PUT(self): self.do_request()
    def do_DELETE(self): self.do_request()
    def do_HEAD(self): self.do_request()
    def do_PATCH(self): self.do_request()
    def do_OPTIONS(self): self.do_request()

    def log_message(self, format, *args):
        sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), format % args))


class ThreadedUnixHTTPServer(http.server.HTTPServer):
    address_family = socket.AF_UNIX

    def server_bind(self):
        self.socket.bind(self.server_address)
        os.chmod(self.server_address, 0o666)

    def process_request(self, request, client_address):
        t = threading.Thread(target=self._handle, args=(request, client_address))
        t.daemon = True
        t.start()

    def _handle(self, request, client_address):
        try:
            self.finish_request(request, client_address)
        except Exception:
            self.handle_error(request, client_address)
        finally:
            self.shutdown_request(request)


def cleanup(signum, frame):
    server.server_close()
    if os.path.exists(SOCK_PATH):
        os.unlink(SOCK_PATH)
    sys.exit(0)


server = ThreadedUnixHTTPServer(SOCK_PATH, ProxyHandler)
signal.signal(signal.SIGTERM, cleanup)
signal.signal(signal.SIGINT, cleanup)

while True:
    try:
        server.handle_request()
    except Exception:
        break

server.server_close()
if os.path.exists(SOCK_PATH):
    os.unlink(SOCK_PATH)
