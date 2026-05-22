#!/usr/bin/env python3
import http.server, socket, sys, os, signal, re, time, threading, gzip, zlib, select, json, subprocess
from http.client import HTTPConnection
from urllib.parse import urlparse, urlunparse

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
try{var k=Object.keys(localStorage);for(var i=0;i<k.length;i++){var v=localStorage.getItem(k[i]);if(v&&v.includes&&(v.includes(':9090')||v.includes(':9091'))){localStorage.removeItem(k[i]);}}}catch(e){}
var _f=window.fetch;
window.fetch=function(u,o){
if(typeof u==='string'){
if(u.charAt(0)==='/'&&!u.startsWith(P)){u=P+u;}
else if(u.startsWith('http')){
try{var _u=new URL(u,location.origin);if(_u.host===location.host||_u.port==='9090'||_u.port==='9091'){u=P+_u.pathname;if(_u.search)u+=_u.search;}}catch(e){}
}
}
return _f.call(this,u,o);
};
var _o=XMLHttpRequest.prototype.open;
XMLHttpRequest.prototype.open=function(m,u,s){
if(typeof u==='string'){
if(u.charAt(0)==='/'&&!u.startsWith(P)){arguments[1]=P+u;}
else if(u.startsWith('http')){
try{var _u=new URL(u,location.origin);if(_u.host===location.host||_u.port==='9090'||_u.port==='9091'){arguments[1]=P+_u.pathname;if(_u.search)arguments[1]+=_u.search;}}catch(e){}
}
}
return _o.apply(this,arguments);
};
var _ps=history.pushState;
history.pushState=function(s,t,u){
if(typeof u==='string'&&u.charAt(0)==='/'&&!u.startsWith(P)){u=P+u;}
return _ps.call(this,s,t,u);
};
var _rs=history.replaceState;
history.replaceState=function(s,t,u){
if(typeof u==='string'&&u.charAt(0)==='/'&&!u.startsWith(P)){u=P+u;}
return _rs.call(this,s,t,u);
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
    data = re.sub(rb'<base\s+href=["\']/', rb'<base href="' + p + rb'/', data, count=1)
    data = re.sub(rb'(src|href|action)=([\'"])/', rb'\1=\2' + p + rb'/', data)
    return data

def rewrite_js(data, prefix):
    p = prefix.encode()
    for old in [b'"/transmission/rpc"', b'"/transmission/web"', b'"/transmission/web/"', b'"/transmission/"',
                b"'/transmission/rpc'", b"'/transmission/web'", b"'/transmission/web/'", b"'/transmission/'",
                b"`/transmission/rpc`", b"`/transmission/web`", b"`/transmission/web/`", b"`/transmission/`"]:
        stripped = old[1:-1]
        new = old[:1] + p + stripped + old[-1:]
        data = data.replace(old, new)
    return data

def rewrite_location(value, prefix):
    if value.startswith("/"):
        if not value.startswith(prefix):
            return prefix + value
        return value
    elif value.startswith("http://") or value.startswith("https://"):
        parsed = urlparse(value)
        if parsed.path.startswith(prefix):
            return parsed.path
        elif parsed.path.startswith("/"):
            return prefix + parsed.path
    return value

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

UPDATE_REPO = "sushazhi/fnos-transmission"
UPDATE_API = "https://api.github.com"
UPDATE_PROXY = "https://ghfast.top/"
_update_status = {"updating": False, "progress": 0, "message": ""}
_update_lock = threading.Lock()
_cached_version = {"expires": 0, "data": None}

def _compare_version(v1, v2):
    p1 = [int(x) for x in v1.split('.')]
    p2 = [int(x) for x in v2.split('.')]
    for i in range(max(len(p1), len(p2))):
        n1 = p1[i] if i < len(p1) else 0
        n2 = p2[i] if i < len(p2) else 0
        if n2 > n1: return 1
        if n2 < n1: return -1
    return 0

def _fetch_latest_version():
    import urllib.request
    url = f"{UPDATE_API}/repos/{UPDATE_REPO}/releases/latest"
    req = urllib.request.Request(url, headers={"User-Agent": "fnos-transmission-updater", "Accept": "application/vnd.github.v3+json"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read())
    version = data.get("tag_name", "").lstrip("v")
    fpk_asset = None
    for a in data.get("assets", []):
        if a.get("name", "").endswith(".fpk") and "transmission" in a.get("name", ""):
            fpk_asset = a
            break
    return {
        "version": version,
        "changelog": data.get("body", ""),
        "publishedAt": data.get("published_at", ""),
        "releaseUrl": data.get("html_url", ""),
        "fpkUrl": fpk_asset.get("browser_download_url", "") if fpk_asset else "",
        "fpkSize": fpk_asset.get("size", 0) if fpk_asset else 0
    }

def _get_current_version():
    try:
        with open(CONFIG_PATH.replace("settings.json", "../manifest"), 'r') as f:
            for line in f:
                if line.strip().startswith("version"):
                    return line.split("=", 1)[1].strip()
    except Exception:
        pass
    v = os.environ.get("TRIM_APPVER", "")
    return v if v else "0.0.0"

def _validate_fpk(path):
    """检查文件是否为有效 fpk 而非 HTML 错误页"""
    try:
        with open(path, 'rb') as f:
            head = f.read(4)
            if head[:2] == b'\x1f\x8b' or head == b'PK\x03\x04':
                return True, ""
            return False, f"内容异常 ({repr(head)})"
    except Exception as e:
        return False, str(e)

def _download_fpk(url, dest, status, max_size=5*1024*1024):
    """
    下载 fpk 文件到 dest。
    参考 fnos-logmanager downloadFileWithProgress 模式。
    返回 (成功, 错误信息)
    """
    import urllib.request, urllib.error
    tmp = dest + ".part"
    # 清理残留
    if os.path.exists(tmp):
        os.remove(tmp)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        resp = urllib.request.urlopen(req, timeout=30)
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code} {e.reason}"
    except urllib.error.URLError as e:
        return False, f"网络错误: {e.reason}"
    except Exception as e:
        return False, f"连接失败: {e}"

    # 检查状态码
    if resp.status != 200:
        resp.close()
        return False, f"服务器返回 HTTP {resp.status}"

    # 检查 Content-Length
    total = int(resp.headers.get("Content-Length", 0))
    if total > max_size:
        resp.close()
        return False, f"文件过大 ({total//1024}KB > {max_size//1024}KB)"

    # 设置 socket 读超时
    try:
        resp.fp.raw._sock.settimeout(30)
    except Exception:
        pass

    downloaded = 0
    try:
        with open(tmp, 'wb') as f:
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                if downloaded > max_size:
                    resp.close()
                    os.remove(tmp)
                    return False, "下载内容超过大小限制"
                if total > 0:
                    pct = 10 + int(downloaded / total * 50)
                    status["progress"] = pct
                    status["message"] = f"正在下载... {downloaded//1024}KB/{total//1024}KB"
    except Exception as e:
        resp.close()
        if os.path.exists(tmp):
            os.remove(tmp)
        return False, f"下载中断: {e}"
    resp.close()

    if downloaded == 0:
        os.remove(tmp)
        return False, "下载文件为空"

    os.replace(tmp, dest)
    return True, ""

def _perform_update(fpk_url):
    global _update_status
    try:
        _update_status["message"] = "正在准备更新..."
        _update_status["progress"] = 5

        # 下载到 /tmp/ 目录（应用中心文件选择器可访问）
        update_dir = "/tmp"
        fpk_path = os.path.join(update_dir, "transmission-update.fpk")

        # 先用代理下载，失败后直连
        urls = [UPDATE_PROXY + fpk_url, fpk_url]
        success = False
        last_error = ""

        for idx, download_url in enumerate(urls):
            _update_status["message"] = "正在下载更新包..." if idx == 0 else "代理下载失败，尝试直连..."
            _update_status["progress"] = 10 if idx == 0 else 10

            ok, err = _download_fpk(download_url, fpk_path, _update_status)
            if ok:
                # 校验文件内容
                valid, reason = _validate_fpk(fpk_path)
                if valid:
                    success = True
                    break
                else:
                    last_error = f"文件校验失败: {reason}"
                    os.remove(fpk_path)
            else:
                last_error = err

        if not success:
            raise Exception(last_error or "下载失败")

        _update_status["message"] = "正在安装更新..."
        _update_status["progress"] = 70
        vol_match = re.search(r'/vol(\d+)/', update_dir)
        vol_num = vol_match.group(1) if vol_match else "1"
        config_env = os.path.join(update_dir, "config.env")
        with open(config_env, 'w') as f:
            f.write(f"wizard_data_action=keep\n")

        # 验证 fpk 文件
        if not os.path.exists(fpk_path):
            raise Exception(f"更新包文件不存在: {fpk_path}")
        fpk_size = os.path.getsize(fpk_path)
        sys.stderr.write(f"[update] fpk 已下载: {fpk_path} ({fpk_size} bytes)\n")

        # fnOS 安全限制：应用沙箱内无权限调用 appcenter-cli 自动安装
        # 提供 HTTP 下载链接，用户下载后手动上传应用中心安装
        _update_status["message"] = "下载完成！请点击下方按钮下载 fpk，然后前往 应用中心 → 手动安装 上传"
        _update_status["progress"] = 100
        _update_status["updating"] = False
        _update_status["downloadUrl"] = PREFIX + "/api/update/download"
    except Exception as e:
        _update_status["message"] = f"更新失败: {e}"
        _update_status["progress"] = 0
        _update_status["updating"] = False


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

    def _send_json(self, status, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _handle_api(self, path):
        if path == "/api/update/check":
            try:
                global _cached_version
                now = time.time()
                if _cached_version["data"] and _cached_version["expires"] > now:
                    result = _cached_version["data"]
                else:
                    info = _fetch_latest_version()
                    cur = _get_current_version()
                    has_update = _compare_version(cur, info["version"]) > 0
                    result = {
                        "success": True,
                        "currentVersion": cur,
                        "latestVersion": info["version"],
                        "hasUpdate": has_update,
                        "changelog": info["changelog"],
                        "publishedAt": info["publishedAt"],
                        "releaseUrl": info["releaseUrl"],
                        "fpkUrl": info["fpkUrl"],
                        "message": "发现新版本" if has_update else "已是最新版本"
                    }
                    _cached_version = {"expires": now + 300, "data": result}
                self._send_json(200, result)
            except Exception as e:
                self._send_json(500, {"success": False, "error": str(e)})
            return True

        if path == "/api/update/install":
            if self.command != "POST":
                self._send_json(405, {"success": False, "error": "Method not allowed"})
                return True
            with _update_lock:
                if _update_status["updating"]:
                    self._send_json(409, {"success": False, "error": "正在更新中，请稍候"})
                    return True
                try:
                    info = _fetch_latest_version()
                    if not info["fpkUrl"]:
                        self._send_json(400, {"success": False, "error": "未找到更新包"})
                        return True
                    _update_status["updating"] = True
                    _update_status["progress"] = 0
                    _update_status["message"] = "准备更新..."
                except Exception as e:
                    self._send_json(500, {"success": False, "error": str(e)})
                    return True
            self._send_json(200, {"success": True, "message": "开始下载更新"})
            t = threading.Thread(target=_perform_update, args=(info["fpkUrl"],))
            t.daemon = True
            t.start()
            return True

        if path == "/api/update/status":
            self._send_json(200, {"success": True, **_update_status})
            return True

        if path == "/api/update/download":
            fpk_path = "/tmp/transmission-update.fpk"
            if not os.path.exists(fpk_path):
                self._send_json(404, {"success": False, "error": "更新包不存在，请先点击一键更新"})
                return True
            try:
                sz = os.path.getsize(fpk_path)
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Disposition", "attachment; filename=transmission-update.fpk")
                self.send_header("Content-Length", str(sz))
                self.end_headers()
                with open(fpk_path, 'rb') as f:
                    while True:
                        chunk = f.read(65536)
                        if not chunk:
                            break
                        self.wfile.write(chunk)
            except Exception as e:
                self._send_json(500, {"success": False, "error": str(e)})
            return True

        return False

    def do_request(self):
        if self.path == PREFIX:
            self.send_response(301)
            self.send_header("Location", PREFIX + "/")
            self.end_headers()
            return

        path = self._strip_prefix()

        if path.startswith("/api/update/"):
            if self._handle_api(path):
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

        max_redirects = 5
        for _ in range(max_redirects):
            try:
                conn.request(self.command, path, body, headers)
                resp = conn.getresponse()
            except Exception as e:
                self.send_error(502, str(e))
                conn.close()
                return

            if resp.status in (301, 302, 303, 307, 308):
                loc = resp.getheader("Location", "")
                resp.read()
                conn.close()
                if not loc:
                    self.send_error(502, "redirect without location")
                    return
                if loc.startswith("http://") or loc.startswith("https://"):
                    parsed = urlparse(loc)
                    path = parsed.path or "/"
                    if parsed.query:
                        path += "?" + parsed.query
                elif loc.startswith("/"):
                    path = loc
                else:
                    path = path.rsplit("/", 1)[0] + "/" + loc
                conn = self._get_backend()
                body = None
                continue
            break
        else:
            self.send_error(502, "too many redirects")
            return

        try:
            all_resp_headers = resp.getheaders()
            is_html = any("text/html" in v for k, v in all_resp_headers if k.lower() == "content-type")
            is_js = any("javascript" in v for k, v in all_resp_headers if k.lower() == "content-type")
            content_encoding = next((v for k, v in all_resp_headers if k.lower() == "content-encoding"), None)

            resp_headers = []
            for key, value in all_resp_headers:
                kl = key.lower()
                if kl == "content-encoding" and (is_html or is_js):
                    continue
                if kl in ("transfer-encoding", "connection", "content-length"):
                    continue
                if kl in ("location", "content-location"):
                    value = rewrite_location(value, PREFIX)
                resp_headers.append((key, value))

            if is_html or is_js:
                data = resp.read()
                if content_encoding:
                    raw = decompress(data, content_encoding)
                    if raw is not None:
                        data = raw
                if is_html:
                    data = rewrite_html(data, PREFIX)
                if is_js:
                    data = rewrite_js(data, PREFIX)
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
