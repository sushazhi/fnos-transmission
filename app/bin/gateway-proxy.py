#!/usr/bin/env python3
import http.server, socket, sys, os, signal, re, time, threading, gzip, zlib, select, json, subprocess
import platform as _platform
from http.client import HTTPConnection
from urllib.parse import urlparse, urlunparse

SOCK_PATH = sys.argv[1]
TARGET_HOST = sys.argv[2]
INITIAL_PORT = int(sys.argv[3])
CONFIG_PATH = sys.argv[4] if len(sys.argv) > 4 else None
PREFIX = "/app/transmission"

# 架构检测（模块级）
_RAW_ARCH = _platform.machine().lower()
if _RAW_ARCH in ('aarch64', 'arm64', 'armv8l'):
    CURRENT_ARCH = 'arm64'
else:
    CURRENT_ARCH = 'amd64'

_current_port = INITIAL_PORT
_port_check_time = 0
_port_lock = threading.Lock()

INJECT_SCRIPT = '''<script>
(function(){
var P="/app/transmission";
try{var k=Object.keys(localStorage);for(var i=0;i<k.length;i++){var v=localStorage.getItem(k[i]);if(v&&v.includes&&(v.includes(':9090')||v.includes(':9091'))){localStorage.removeItem(k[i]);}}}catch(e){}
window.TRANSMISSION_APP_ARCH = "__ARCH__";
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
</script>
<script>
(function(){
if(window.self===window.top){return;}
var P="/app/transmission";
var _dlPath="";
var _dlPathDisplay="";
/* ===== fnOS SDK（Penpal 最小桥接） ===== */
var __trSdk=(function(){
var connected=false,methods={},pending={},msgId=1,listeners={};
function connect(){window.parent.postMessage({penpal:"syn"},"*");setTimeout(function(){if(!connected){window.__TR_SDK_READY=true;window.dispatchEvent(new Event("tr-sdk-ready"));}},1500);}
window.addEventListener("message",function(ev){
var d=ev.data;if(!d||!d.penpal)return;
if(d.penpal==="synAck"){methods=d.methodNames||[];window.parent.postMessage({penpal:"ack",methodNames:[],config:{}},"*");connected=true;window.__TR_SDK_READY=true;window.dispatchEvent(new Event("tr-sdk-ready"));}
else if(d.penpal==="reply"){var cb=pending[d.id];if(cb){delete pending[d.id];if(d.resolution==="fulfilled"){cb.resolve(d.returnValue);}else{cb.reject(new Error((d.returnValue&&d.returnValue.message)||"call failed"));}}}
});
function call(methodName,args){return new Promise(function(resolve,reject){var id=msgId++;pending[id]={resolve:resolve,reject:reject};var payload={penpal:"call",id:id,methodName:methodName,args:args||[]};if(!connected){setTimeout(function(){connect();},0);}window.parent.postMessage(payload,"*");});}
function has(m){return connected&&methods.indexOf(m)>-1;}
return {
get ready(){return connected;},isWeb:true,has:has,call:call,
$on:function(evt,cb){listeners[evt]=listeners[evt]||[];listeners[evt].push(cb);return function(){};},
$off:function(evt,cb){var l=listeners[evt];if(l){var i=l.indexOf(cb);if(i>-1)l.splice(i,1);}},
$notify:function(opts){return call("$notify",[opts||{}]);},
getPlatformConfig:function(){return call("getPlatformConfig",[]);},
setTitle:function(t){return call("setTitle",[t]);},
openFileManager:function(p){return call("openFileManager",[p]);},
convertPath:function(p,l){return call("convertPath",[p,l]);},
pickUserFile:function(opts){return call("pickUserFile",[opts||{}]);},
pickSharedFile:function(opts){return call("pickSharedFile",[opts||{}]);}
};
})();
var sdk=__trSdk;
setTimeout(function(){window.parent.postMessage({penpal:"syn"},"*");},0);
/* ===== 获取下载路径 ===== */
fetch(P+"/api/download-path").then(function(r){return r.json();}).then(function(d){
if(d.success&&d.path){_dlPath=d.path;_dlPathDisplay=d.displayPath||d.path;
if(!d.hasACL){console.warn("[TR] 下载目录权限不足:",d.path);}
var fb=document.getElementById("tr-openfolder-btn");if(fb)fb.title="打开下载目录: "+_dlPathDisplay;}
}).catch(function(){});
/* ===== 通知 ===== */
function _trNotify(t,m){
var colors={success:"#22c55e",error:"#ef4444",warning:"#f59e0b",info:"#3b82f6"};
var icons={success:"✓",error:"✕",warning:"!",info:"ℹ"};
var c=colors[t]||"#3b82f6";
var el=document.createElement("div");
el.style.position="fixed";el.style.top="16px";el.style.right="16px";el.style.zIndex="2147483647";
el.style.display="flex";el.style.alignItems="center";el.style.gap="10px";el.style.maxWidth="360px";
el.style.padding="12px 16px";el.style.background="rgba(30,32,38,0.95)";el.style.borderLeft="4px solid "+c;
el.style.borderRadius="8px";el.style.color="#fff";el.style.fontSize="13px";el.style.boxShadow="0 8px 24px rgba(0,0,0,0.35)";
var icon=document.createElement("span");icon.style.width="18px";icon.style.height="18px";icon.style.flexShrink="0";
icon.style.borderRadius="50%";icon.style.background=c;icon.style.color="#fff";icon.style.display="flex";
icon.style.alignItems="center";icon.style.justifyContent="center";icon.style.fontSize="12px";icon.style.fontWeight="bold";
icon.textContent=icons[t]||"ℹ";
var txt=document.createElement("span");txt.style.flex="1";txt.style.wordBreak="break-all";txt.textContent=m;
el.appendChild(icon);el.appendChild(txt);document.body.appendChild(el);
setTimeout(function(){if(el.parentNode)el.parentNode.removeChild(el);},3500);
}
/* ===== 按钮注入 ===== */
function _trAddBtn(){
try{
var fe=window.frameElement;if(!fe)return;
var h=fe.closest(".trim-ui__app-layout--window");
if(h){h=h.querySelector(".trim-ui__app-layout--header");if(h){
var r=h.querySelector(":scope > div:last-child");
if(r&&!r.querySelector("#tr-pickfolder-btn")){
/* 选择下载目录按钮 */
var c=document.createElement("div");
c.id="tr-pickfolder-btn";c.title="选择下载目录";
c.className="flex h-full w-base shrink-0 cursor-pointer items-center justify-center px-[15px] text-[var(--semi-color-text-0)] hover:bg-[var(--semi-color-fill-0)]";
c.innerHTML='<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24"><path fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 5v14m-7-7h14"/></svg>';
c.onclick=function(e){e.stopPropagation();
var P="/app/transmission";
var opts={multiple:false,directory:true,title:"选择下载目录",okText:"确认选择",sidebarGroup:["myFiles","otherShare","favorites"]};
var doPick=function(){
var sel=sdk&&sdk.pickUserFile?sdk.pickUserFile.bind(sdk):null;
if(!sel){_trNotify("error","文件选择器不可用");return;}
sel(opts).then(function(res){
var p=null;
if(Array.isArray(res)){p=res[0];}
else if(res&&res.data){p=Array.isArray(res.data)?res.data[0]:res.data;}
else if(res&&res.paths&&res.paths.length){p=res.paths[0];}
if(!p){_trNotify("warning","未选择目录");return;}
fetch(P+"/api/set-save-path",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({path:p})}).then(function(r){return r.json();}).then(function(r2){
if(r2.success){_trNotify("success",r2.applied?("下载目录已设置为: "+p):("配置已保存，请重启应用后生效"));}
else{_trNotify("error","设置失败: "+(r2.error||"未知错误"));}
}).catch(function(){_trNotify("error","设置失败，网络错误");});
}).catch(function(err){
var m=(err&&err.message)||"无法打开文件选择器";
if(m.indexOf("cancel")>-1||m.indexOf("canceled")>-1){return;}
_trNotify("error","选择目录失败: "+m);
});
};
if(!sdk.ready){setTimeout(doPick,800);}else{doPick();}
};
r.insertBefore(c,r.firstChild);
/* 打开下载目录按钮 */
var f=document.createElement("div");
f.id="tr-openfolder-btn";f.title="打开下载目录";
f.className="flex h-full w-base shrink-0 cursor-pointer items-center justify-center px-[15px] text-[var(--semi-color-text-0)] hover:bg-[var(--semi-color-fill-0)]";
f.innerHTML='<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24"><path fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2 6a2 2 0 0 1 2-2h5l2 2h9a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V6z"/></svg>';
f.onclick=function(e){e.stopPropagation();
var P="/app/transmission";
fetch(P+"/api/download-path").then(function(r){return r.json();}).then(function(d){
if(d.success&&d.path){
sdk.openFileManager(d.path).catch(function(){
var inp=document.createElement("textarea");inp.value=d.path;inp.style.position="fixed";inp.style.opacity="0";
document.body.appendChild(inp);inp.select();document.execCommand("copy");document.body.removeChild(inp);
_trNotify("error","打开失败，下载目录路径已复制: "+d.path);
});
}else{_trNotify("error","无法获取下载目录路径");}
}).catch(function(){_trNotify("error","获取下载目录失败");});
};
r.insertBefore(f,r.firstChild);
}
}
}
}catch(e){}
}
if(document.readyState==="complete"){_trAddBtn();}else{window.addEventListener("load",_trAddBtn);}
setTimeout(_trAddBtn,2000);setTimeout(_trAddBtn,6000);
})();
</script>'''.encode('utf-8')

# 注入当前架构到前端
INJECT_SCRIPT = INJECT_SCRIPT.replace(b"__ARCH__", CURRENT_ARCH.encode("ascii"))

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

# ---------------------------------------------------------------------------
# fnOS 开放 API 桥接（文件选择器 / 打开文件管理器）
# ---------------------------------------------------------------------------
_TRIM_SOCK = "/var/run/trim_open_gateway_apiscope.socket"

def _call_trim_api(req_name, data=None):
    """调用 fnOS 后端开放 API，返回响应中的 data 或 None"""
    api_token = os.environ.get("TRIM_API_TOKEN", "")
    if not api_token:
        return None
    body = json.dumps({
        "req": req_name,
        "appName": "transmission",
        "data": data or {},
    })
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(5)
        sock.connect(_TRIM_SOCK)
        req = (
            "POST /api/v1/trimapp HTTP/1.1\r\n"
            "Host: localhost\r\n"
            "Authorization: Bearer %s\r\n"
            "Content-Type: application/json\r\n"
            "Content-Length: %d\r\n"
            "Connection: close\r\n"
            "\r\n"
            "%s"
        ) % (api_token, len(body), body)
        sock.sendall(req.encode())
        resp = b""
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            resp += chunk
        sock.close()
        header_end = resp.find(b"\r\n\r\n")
        if header_end < 0:
            return None
        resp_body = resp[header_end + 4:]
        result = json.loads(resp_body)
        if result.get("code") == 0:
            return result.get("data")
        return None
    except Exception:
        return None


def _read_config_download_dir():
    """从 settings.json 读取 download-dir"""
    try:
        if CONFIG_PATH and os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, 'r') as f:
                cfg = json.load(f)
            return cfg.get("download-dir", "")
    except Exception:
        pass
    return ""


def _set_config_download_dir(new_path):
    """更新 settings.json 中的 download-dir（持久化，重启后仍生效）"""
    try:
        if CONFIG_PATH and os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, 'r') as f:
                cfg = json.load(f)
            cfg["download-dir"] = new_path
            with open(CONFIG_PATH, 'w') as f:
                json.dump(cfg, f, indent=4, ensure_ascii=False)
            return True
    except Exception:
        pass
    return False


def _call_transmission_rpc(method, arguments):
    """调用 Transmission RPC（JSON-RPC），自动处理 X-Transmission-Session-Id。
    返回 (ok, response_dict)。"""
    port = get_target_port()
    try:
        # 先 GET 获取 session id
        conn = HTTPConnection(TARGET_HOST, port, timeout=15)
        conn.request("GET", "/transmission/rpc")
        resp = conn.getresponse()
        resp.read()
        session_id = resp.getheader("X-Transmission-Session-Id", "")
        conn.close()

        payload = json.dumps({"method": method, "arguments": arguments or {}})
        headers = {
            "Content-Type": "application/json",
            "X-Transmission-Session-Id": session_id,
        }
        conn = HTTPConnection(TARGET_HOST, port, timeout=15)
        conn.request("POST", "/transmission/rpc", body=payload, headers=headers)
        resp = conn.getresponse()
        data = resp.read()
        status = resp.status
        conn.close()
        try:
            return status == 200, json.loads(data)
        except Exception:
            return status == 200, None
    except Exception:
        return False, None


if os.path.exists(SOCK_PATH):
    os.unlink(SOCK_PATH)

UPDATE_REPO = "sushazhi/fnos-transmission"
UPDATE_API = "https://api.github.com"
UPDATE_PROXY = "https://gh-proxy.com/"
UPDATE_PROXIES = ["https://gh-proxy.com/", "https://v4.gh-proxy.org/", "https://ghfast.top/"]
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
    arch = CURRENT_ARCH
    fpk_asset = None
    fpk_suffix = f"-{arch}.fpk"
    for a in data.get("assets", []):
        name = a.get("name", "")
        if name.endswith(fpk_suffix) and "transmission" in name:
            fpk_asset = a
            break
    # fallback：无当前架构资产时，取任意 transmission fpk
    if not fpk_asset:
        for a in data.get("assets", []):
            name = a.get("name", "")
            if name.endswith(".fpk") and "transmission" in name:
                fpk_asset = a
                break
    return {
        "version": version,
        "changelog": data.get("body", ""),
        "publishedAt": data.get("published_at", ""),
        "releaseUrl": data.get("html_url", ""),
        "fpkUrl": fpk_asset.get("browser_download_url", "") if fpk_asset else "",
        "fpkSize": fpk_asset.get("size", 0) if fpk_asset else 0,
        "arch": arch
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

def _verify_fpk_version(fpk_path, expected_version):
    """验证 fpk 内部的 manifest 版本号是否匹配"""
    try:
        import gzip
        with gzip.open(fpk_path, 'rb') as f:
            data = f.read()
        text = data.decode('utf-8', errors='replace')
        for line in text.split('\n'):
            line = line.strip()
            if line.startswith('version'):
                ver = line.split('=')[1].strip()
                if ver == expected_version:
                    return True, ""
                return False, f"版本不匹配: 期望 {expected_version}, 实际 {ver}"
    except Exception:
        pass
    # 尝试 zip 格式
    try:
        import zipfile
        with zipfile.ZipFile(fpk_path, 'r') as zf:
            for name in zf.namelist():
                if 'manifest' in name or name == 'manifest':
                    content = zf.read(name).decode('utf-8', errors='replace')
                    for line in content.split('\n'):
                        line = line.strip()
                        if line.startswith('version'):
                            ver = line.split('=')[1].strip()
                            if ver == expected_version:
                                return True, ""
                            return False, f"版本不匹配: 期望 {expected_version}, 实际 {ver}"
    except Exception:
        pass
    return True, ""  # 无法验证则放行（兼容未知格式）

def _perform_update(fpk_url):
    global _update_status
    try:
        _update_status["message"] = "正在准备更新..."
        _update_status["progress"] = 5

        # 下载到 /tmp/ 目录（应用中心文件选择器可访问）
        update_dir = "/tmp"
        fpk_path = os.path.join(update_dir, "transmission-update.fpk")

        # 多级代理优先，全部失败后直连
        urls = [p + fpk_url for p in UPDATE_PROXIES] + [fpk_url]
        success = False
        last_error = ""

        for idx, download_url in enumerate(urls):
            _update_status["message"] = "正在下载更新包..." if idx == 0 else "代理下载失败，尝试直连..."
            _update_status["progress"] = 10 if idx == 0 else 10

            ok, err = _download_fpk(download_url, fpk_path, _update_status)
            if ok:
                # 校验文件头（gzip/zip 魔数）
                valid, reason = _validate_fpk(fpk_path)
                if not valid:
                    last_error = f"文件校验失败: {reason}"
                    os.remove(fpk_path)
                    continue
                # 校验文件大小是否匹配 GitHub release
                expected_size = _update_status.get("fpkSize", 0)
                actual_size = os.path.getsize(fpk_path)
                if expected_size and actual_size != expected_size:
                    last_error = f"文件大小不匹配: 期望 {expected_size}, 实际 {actual_size}"
                    os.remove(fpk_path)
                    continue
                # 校验 manifest 版本号
                expected_ver = _update_status.get("version", "")
                if expected_ver:
                    match, reason = _verify_fpk_version(fpk_path, expected_ver)
                    if not match:
                        last_error = reason
                        os.remove(fpk_path)
                        continue
                success = True
                break
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
        # 解析查询参数（debug=1 用于调试模式强制刷新缓存）
        qs = ""
        if "?" in path:
            path, qs = path.split("?", 1)
        params = {}
        if qs:
            for p in qs.split("&"):
                if "=" in p:
                    k, v = p.split("=", 1)
                    params[k] = v
                else:
                    params[p] = ""
        is_debug = params.get("debug") == "1"

        if path == "/api/download-path":
            try:
                save_path = _read_config_download_dir()
                result = {"success": True, "path": save_path, "displayPath": save_path, "hasACL": True}
                if save_path:
                    # 路径转换：得到语义路径用于显示
                    try:
                        display = _call_trim_api("trim.file.convertPath", {
                            "path": [save_path],
                            "language": "zh-CN",
                        })
                        if display and display.get("status") == 0:
                            sem = display.get("result", [{}])[0].get("semanticPath", "")
                            if sem:
                                result["displayPath"] = sem
                    except Exception:
                        pass
                    # 权限检查
                    try:
                        uid = self.headers.get("X-Trim-Userid", "")
                        if uid:
                            acl = _call_trim_api("trim.file.checkUserACL", {
                                "uid": int(uid),
                                "path": save_path,
                            })
                            if acl and isinstance(acl, list) and len(acl) > 0:
                                item = acl[0]
                                result["hasACL"] = bool(item.get("readable") or item.get("writable"))
                    except Exception:
                        pass
                self._send_json(200, result)
            except Exception as e:
                self._send_json(500, {"success": False, "error": str(e)})
            return True

        if path == "/api/set-save-path":
            try:
                length = int(self.headers.get("Content-Length", 0))
                if length <= 0:
                    self._send_json(400, {"success": False, "error": "缺少请求体"})
                    return True
                req_body = self.rfile.read(length).decode("utf-8")
                data = json.loads(req_body)
                new_path = (data.get("path") or "").strip()
                if not new_path:
                    self._send_json(400, {"success": False, "error": "路径不能为空"})
                    return True
                if not os.path.isdir(new_path):
                    try:
                        os.makedirs(new_path, exist_ok=True)
                    except Exception:
                        self._send_json(400, {"success": False, "error": "目录不存在且无法创建: %s" % new_path})
                        return True
                # 持久化到 settings.json
                saved = _set_config_download_dir(new_path)
                # 通过 Transmission RPC 实时生效（无需重启）
                ok, _resp = _call_transmission_rpc("session-set", {"download-dir": new_path})
                self._send_json(200, {
                    "success": True,
                    "path": new_path,
                    "applied": ok,
                    "note": "" if ok else "配置已保存，但实时应用失败，可能需重启应用生效",
                })
            except Exception as e:
                self._send_json(500, {"success": False, "error": str(e)})
            return True

        if path == "/api/update/check":
            try:
                global _cached_version
                now = time.time()
                if not is_debug and _cached_version["data"] and _cached_version["expires"] > now:
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
                        "arch": CURRENT_ARCH,
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
                    _update_status["version"] = info["version"]
                    _update_status["fpkSize"] = info["fpkSize"]
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
                ver = _update_status.get("version") or _get_current_version()
                filename = f"transmission-{ver}-{CURRENT_ARCH}.fpk"
                sz = os.path.getsize(fpk_path)
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Disposition", f"attachment; filename={filename}")
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

        if path.startswith("/api/"):
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
