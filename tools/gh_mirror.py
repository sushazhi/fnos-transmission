#!/usr/bin/env python3
"""gh_mirror - GitHub 下载加速源（单一事实源）

这个模块被三处共用：
  1) build.py            本地/CI 构建时下载 transmission-daemon、SeedArk、fpk 资产
  2) build_mirror_probe.py  打包前实测各加速源，选出可用子集写进 fpk
  3) （打包后的 SeedArk）  读取 app/bin/update-mirrors.txt，用于应用内一键更新

为什么要有这个文件
------------------
之前加速源地址散落在 build.py / gateway-proxy.py / SeedArk update.go / CI workflow
四处，改一次要同步改四个地方，漏改就会让「构建能下、应用内更新不能下」。现在
地址与顺序只在这里定义，其它地方要么 import，要么读取由这里生成的清单文件。

选源依据（2026-10-21 实测，16MB fpk，单连接）
--------------------------------------------
  gh-proxy.com        多轮 0.95~6.4 MB/s，最稳，首选
  v4.gh-proxy.org     与 gh-proxy.com 同一后端（ETag / x-cache-hits 完全一致），
                      只能当节点切换，不能当灾备
  ghfast.top          独立运营，抖动大
  ghproxy.imciel.com  独立运营，速度中等
  直连                 境外链路/无墙环境通常最快，且不经第三方中转：
                       因此**永远先试直连**，直连慢到超时才切加速源
  已淘汰 gh.dpik.top   实测 279 KB/s，且 API 侧 403

一个重要发现：单连接速度被节点限流，但**并发多连接（哪怕是同一个镜像）能拿到
数倍带宽**；且所有候选镜像都支持 Range（206 + Content-Range），ETag 也一致。
所以下载侧的正确做法是「分片并发 + 多镜像轮转」，而不是「串行试镜像、谁快用谁」。

下载顺序（2026-10 调整）
------------------------
**直连优先，超时才上加速源**：
  1. 先用 Range 探测直连：拿到 206 + 正确大小即认为直连可用 → 全部带宽给直连；
  2. 直连探测超时 / 被拒 / 返回 HTML 错误页 / 明显龟速（探测窗口内低于
     DIRECT_MIN_SPEED）→ 判定这条链路不通，改走加速源（按 MIRRORS 顺序）；
  3. 分片下载中直连卡住（无数据超时或被墙的静默限速）→ 该片改派到加速源，
     并整次下载把直连降级，不再分配新分片；
  4. 直连与加速源都失败才报错。
直连的代价是「不通时要白等一次超时」，所以直连探测超时刻意取得很短
（DIRECT_PROBE_TIMEOUT），用秒级代价换掉「明明直连更快却先绕代理」的一跳。

本模块只用标准库，不引入任何依赖。
"""
import hashlib
import os
import re
import socket
import threading
import time
import urllib.error
import urllib.request

# ---------------------------------------------------------------------------
# 加速源列表（顺序即优先级：构建与更新都按此顺序轮转/兜底）
# ---------------------------------------------------------------------------
MIRRORS = (
    "https://gh-proxy.com/",
    "https://v4.gh-proxy.org/",
    "https://ghfast.top/",
    "https://ghproxy.imciel.com/",
)

# 打包进 fpk 的清单文件名（放在 app/bin/ 下，与 seedark 同级）。
# SeedArk 启动时优先读它；文件不存在或为空则退回其内置默认列表。
MIRROR_MANIFEST_NAME = "update-mirrors.txt"

# 旧代理，仅用于「把旧清单升级成新清单」时识别并剔除
_OBSOLETE_MIRRORS = ("https://gh.dpik.top/",)

CONTENT_RANGE_RE = re.compile(r"bytes\s+(\d+)-(\d+)/(\d+)$")
MIRROR_RE = re.compile(r"^https?://[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%-]+$")
FPK_MAX_SIZE = 100 * 1024 * 1024      # 100 MB，与应用内更新侧的上限一致
TOTAL_TIMEOUT = 120                    # 单次下载总时长上限（秒）
SOCKET_TIMEOUT = 30                    # 单流下载的单次读超时（秒）
PROBE_TIMEOUT = 12                     # 镜像 Range 探测超时（秒）
DIRECT_PROBE_TIMEOUT = 4               # 直连 Range 探测超时（秒）：直连不通时要尽快认输，别让用户白等
DIRECT_MIN_SPEED = 32 * 1024           # 直连探测窗口内的最低速度（B/s），低于它判为「连得上但被限死」
DIRECT_STALL_TIMEOUT = 8               # 分片阶段直连的「无数据」超时（秒）：比镜像更严，卡住立刻让位


def normalize_mirror(raw):
    """归一化单个镜像地址：去空白、补结尾斜杠；非法返回空串。"""
    s = (raw or "").strip()
    if not s:
        return ""
    if not MIRROR_RE.match(s):
        return ""
    if not s.endswith("/"):
        s += "/"
    return s


def parse_mirrors(text):
    """解析清单文本：每行一个地址，# 开头为注释；非法行丢弃；保持顺序去重。

    先按 \r\n / \r 归一：清单可能是 Windows 上编辑后打进去的，
    残留的 \r 会让最后一行地址变成 ".../\r"，看起来能用、实际请求全挂。
    """
    out = []
    seen = set()
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        m = normalize_mirror(line)
        if m and m not in seen:
            seen.add(m)
            out.append(m)
    return out


def is_obsolete(mirror):
    return normalize_mirror(mirror) in _OBSOLETE_MIRRORS


def render_manifest(mirrors, comment=None):
    """生成清单文件文本（带说明头，便于人在 NAS 上直接看）。"""
    lines = [
        "# fnOS 应用更新加速源（自动生成，勿手改；改建 tools/gh_mirror.py 的 MIRRORS）",
        "# 每行一个前缀：镜像地址 + 原始 GitHub 资源地址即为可下载地址",
    ]
    if comment:
        for c in str(comment).splitlines():
            lines.append("# " + c)
    lines.extend(normalize_mirror(m) for m in mirrors if normalize_mirror(m))
    return "\n".join(lines) + "\n"


def load_manifest(path):
    """读取清单文件；不存在/不可读时返回默认列表。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            got = [m for m in parse_mirrors(f.read()) if not is_obsolete(m)]
        if got:
            return got
    except OSError:
        pass
    return list(MIRRORS)


def build_urls(url, mirrors=None, direct_first=True):
    """把一个 GitHub 资源地址展开成候选下载地址：默认**直连在前**，镜像按顺序跟在后面。

    direct_first=True（默认）：[url, 镜像1+url, 镜像2+url, ...]
    direct_first=False       ：[镜像1+url, ..., url]（旧行为，直连兜底）
    """
    ms = list(MIRRORS if mirrors is None else mirrors)
    urls = [m + url for m in ms]
    if direct_first:
        return [url] + urls
    urls.append(url)
    return urls


def ordered_sources(url, mirrors=None):
    """下载源序列，元素为空串表示「直连」：("" , 镜像1, 镜像2, ...)。

    与 build_urls 同源，只是用空串表示直连（分片/单流内部统一用「前缀 + url」拼地址）。
    """
    ms = list(MIRRORS if mirrors is None else mirrors)
    return [""] + [m for m in ms if m]


def source_url(source, url):
    """把「源」还原成可请求地址；空串即直连。"""
    return (source + url) if source else url


def _is_direct(source):
    return not source


def sort_mirrors_fastest(mirrors=None, sample_url=None, rounds=1, timeout=10):
    """按实测速度给镜像排序（用于构建期动态选择，而非写死顺序）。

    无 sample_url 或全部失败时返回原顺序 —— 排序只是优化，任何情况都不能让构建
    因为「测速失败」而失败。
    """
    ms = list(MIRRORS if mirrors is None else mirrors)
    if not sample_url:
        return ms
    speeds = {}
    for m in ms:
        speeds[m] = _probe_speed(m + sample_url, rounds=rounds, timeout=timeout)
    ranked = [m for m in sorted(ms, key=lambda x: speeds.get(x, 0.0), reverse=True)
              if speeds.get(m, 0.0) > 0]
    failed = [m for m in ms if speeds.get(m, 0.0) <= 0]
    return ranked + failed


def _probe_speed(url, rounds=1, timeout=10, window=256 * 1024):
    """用 Range 请求取一小段，算平均速度（字节/秒）；失败返回 0。

    window 取 256KB：只要够区分「能用 / 不能用」即可。窗口越大越容易把「慢但能用」
    的源误判成不可用（构建期实测里 512KB 窗口曾把正常源判成超时）。
    """
    best = 0.0
    for _ in range(max(1, rounds)):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "Mozilla/5.0",
                              "Range": "bytes=0-%d" % (window - 1),
                              "Cache-Control": "no-cache"})
            t0 = time.time()
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if resp.status not in (200, 206):
                    continue
                n = len(resp.read(window))
            dt = time.time() - t0
            if n > 0 and dt > 0:
                best = max(best, n / dt)
        except Exception:
            continue
    return best


# ---------------------------------------------------------------------------
# 校验
# ---------------------------------------------------------------------------
def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_payload(path, expected_sha256="", expected_size=0, kind="fpk"):
    """校验下载结果：存在、大小、魔数（fpk 为 gzip/zip）、可选 SHA-256。

    返回 (ok, reason)。校验失败时调用方必须删除该文件 —— 加速源链路是第三方中转，
    「看起来下完了」不等于「内容正确」，尤其是代理返回 200 + 错误页的情况。
    """
    if not os.path.isfile(path):
        return False, "文件不存在"
    size = os.path.getsize(path)
    if size == 0:
        return False, "下载内容为空"
    if expected_size > 0 and size != expected_size:
        return False, "文件大小不匹配（期望 %d 字节，实际 %d 字节）" % (expected_size, size)
    with open(path, "rb") as f:
        head = f.read(2)
    if kind == "fpk":
        gz = head[:2] == b"\x1f\x8b"
        zipped = head[:2] == b"PK"
        if not gz and not zipped:
            return False, "内容异常（不是 gzip/zip 包，可能是代理返回的错误页）"
    elif kind == "elf":
        with open(path, "rb") as f:
            if f.read(4) != b"\x7fELF":
                return False, "内容异常（不是 ELF 可执行文件）"
    elif kind == "none":
        pass  # 只校验存在性/大小/摘要（如 .tar.gz，允许任意魔数）
    else:
        return False, "未知校验类型 %r" % (kind,)
    if expected_sha256:
        got = sha256_of(path)
        if got.lower() != expected_sha256.strip().lower():
            return False, "SHA-256 不一致（下载链路可能被替换）"
    return True, ""


# ---------------------------------------------------------------------------
# 下载
# ---------------------------------------------------------------------------
class DownloadError(Exception):
    """下载失败，消息可直接展示给用户/构建日志。"""


def download(url, dest, mirrors=None, description="", expected_sha256="",
             expected_size=0, kind="fpk", user_agent="fnos-transmission-build",
             use_mirrors=True, log=None, max_size=FPK_MAX_SIZE,
             total_timeout=TOTAL_TIMEOUT, direct_first=True):
    """带加速源轮转的下载：默认**先直连**，直连失败/超时才按顺序试镜像。

    与旧实现的区别：
      - 每个源失败后**立即切下一个**，并记录失败原因（旧实现只打印最后一条）；
      - 下完立刻做大小/魔数/SHA-256 校验，校验不过同样切下一个源，而不是把
        坏文件当成成功留给调用方；
      - 先写 .part 再原子改名，任何失败都不会留下半成品。
    返回 (ok, reason)。
    """
    emit = log or (lambda *_: None)
    tmp = dest + ".part"
    url_list = build_urls(url, mirrors, direct_first=direct_first) if use_mirrors else [url]
    errors = []
    for idx, u in enumerate(url_list):
        direct = u == url
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
            emit("    Trying %s%s" % ("直连 " if direct and use_mirrors else "", u[:78]))
            _fetch_single(u, tmp, user_agent=user_agent, max_size=max_size,
                          total_timeout=total_timeout, emit=emit,
                          socket_timeout=DIRECT_STALL_TIMEOUT if direct and use_mirrors else SOCKET_TIMEOUT)
            ok, reason = verify_payload(tmp, expected_sha256, expected_size, kind)
            if not ok:
                errors.append("%s: %s" % (u[:60], reason))
                emit("    fail: %s" % (reason,))
                os.remove(tmp)
                continue
            os.replace(tmp, dest)
            emit("  Downloaded %s" % (description or os.path.basename(dest),))
            return True, ""
        except DownloadError as e:
            errors.append("%s: %s" % (u[:60], e))
            emit("    fail: %s" % (e,))
        except Exception as e:  # noqa: BLE001 - 任何异常都不能中断轮转
            errors.append("%s: %s" % (u[:60], e))
            emit("    fail: %s" % (str(e)[:100],))
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)
    return False, " | ".join(errors[-3:]) if errors else "所有加速源均失败"


def _fetch_single(url, dest, user_agent, max_size, total_timeout, emit,
                  socket_timeout=SOCKET_TIMEOUT):
    req = urllib.request.Request(url, headers={"User-Agent": user_agent})
    try:
        resp = urllib.request.urlopen(req, timeout=socket_timeout)
    except urllib.error.HTTPError as e:
        raise DownloadError("HTTP %d %s" % (e.code, e.reason))
    except urllib.error.URLError as e:
        raise DownloadError("网络错误: %s" % (e.reason,))
    except (socket.timeout, TimeoutError):
        raise DownloadError("连接超时")
    with resp:
        if resp.status not in (200, 206):
            raise DownloadError("服务器返回 HTTP %d" % resp.status)
        total = int(resp.headers.get("Content-Length", 0) or 0)
        if total > max_size:
            raise DownloadError("文件过大（%.1fMB）" % (total / 1024 / 1024))
        started = time.time()
        got = 0
        with open(dest, "wb") as f:
            while True:
                if time.time() - started > total_timeout:
                    raise DownloadError("下载超时（%ds）" % total_timeout)
                chunk = resp.read(262144)
                if not chunk:
                    break
                f.write(chunk)
                got += len(chunk)
                if got > max_size:
                    raise DownloadError("内容超过大小上限")
        if got == 0:
            raise DownloadError("下载内容为空")


# ---------------------------------------------------------------------------
# 分片并发下载（与应用内更新（SeedArk）同一策略的本地实现，供构建/CI 用）
# ---------------------------------------------------------------------------
# 为什么要分片
# -------------
# 单连接被节点限流：同一 16MB fpk 单流实测 0.3–0.5 MB/s（最慢一轮只有 0.11 MB/s，
# 还出现过 85s 的停滞分片）。而每个代理都支持 Range（206 + Content-Range），
# ETag 在所有候选镜像上完全一致 —— 于是「并发多连接 + 跨镜像分摊分片」能把
# 单连接限流摊平，并且天然具备容灾：某个镜像某个分片卡住，只影响那一片。
#
# 容错优先级（依次降级，任何一步失败都不能把坏文件当成功）：
#   1. 并行分片（默认并发 8）；某片失败/超时 → 换镜像重试
#   2. 某镜像反复失败 → 本次下载内把它降级（不再分配给新分片）
#   3. 并行整体失败 → 回退单流顺序下载（镜像按顺序 + 直连兜底）
#   4. 最终一律做 大小 + 魔数 + SHA-256 校验
CHUNK_SIZE = 1 * 1024 * 1024      # 单片 1MB：片数要明显多于 worker，慢片才只损失 1/16
CHUNK_WORKERS = 8
MAX_CHUNKS = 96                   # 分片数上限：片太小反而增加请求开销与失败面
CHUNK_READ_TIMEOUT = 20          # 单个分片「无数据」超时（秒）：卡住的连接要尽快被判死，而不是拖到总超时
MIRROR_DEGRADE_AFTER = 2         # 某镜像连续失败 N 次即在本次下载中降级
DIRECT_DEGRADE_AFTER = 2         # 直连分片超时 N 次即在本次下载中降级（改走加速源），
                                 # 比镜像更早放弃：直连不通时每次重试都要白等一个超时
# 墙钟改派：一片的正常成本 ≈ 片字节 / 全局估计速度，超过「成本 × 系数」仍未完成就
# 取消这条连接并改派到别的镜像。实测镜像会「能下但极慢」而不报错，只靠重试等不到它。
HEDGE_FIRST = 8.0                # 首次改派放宽（容忍瞬时抖动）
HEDGE_NEXT = 4.0                 # 二次收紧（已经派过还慢，就是真慢）
HEDGE_FLOOR = 4.0                # 墙钟下限（秒），避免高延迟链路上被反复打断
BASELINE_SPEED = 256 * 1024      # 单连接基线速度（实测 0.3–0.5 MB/s，取偏保守值）
FALLBACK_FACTOR = 1.1            # 平均单连接速度低于基线 × 该系数 → 判并行无收益
FALLBACK_MIN_WATCH = 4.0         # 增量自检最短观察期（秒）
SPEED_ALPHA = 0.4                # 镜像速度 EWMA 平滑系数
SPEED_SLOW_RATIO = 0.25          # 慢于中位数 1/4 即降级
SPEED_MIN_SAMPLES = 2            # 冷启动保护：每镜像至少 2 个样本才参与速度降级


def download_parallel(url, dest, mirrors=None, chunk=CHUNK_SIZE, workers=CHUNK_WORKERS,
                      expected_sha256="", expected_size=0, description="",
                      user_agent="fnos-transmission-build", log=None,
                      max_size=FPK_MAX_SIZE, max_chunk_retries=3, kind="fpk",
                      direct_first=True):
    """Range 分片 + 多源并发下载（先直连，超时才用加速源）；Range 不可用时回退单流。

    返回 (ok, reason)。成功后目标文件已原子落位；失败时不留 .part / 半成品。
    """
    emit = log or (lambda *_: None)
    tmp = dest + ".part"

    # 必须做：旧产物或旧 .part 先清掉，否则「上次的文件」会被当成「本次成功结果」
    for p in (tmp, dest):
        if os.path.exists(p):
            os.remove(p)

    ms = [m for m in (MIRRORS if mirrors is None else mirrors) if m]
    if not direct_first:
        # 旧行为（加速源优先、直连兜底）：显式要才走这条
        shim = _probe_range(ms, url, user_agent)
        if shim is None:
            emit("    加速源不支持 Range 分片，回退单流下载")
            return download(url, dest, mirrors=ms, description=description,
                            expected_sha256=expected_sha256, expected_size=expected_size,
                            kind=kind, user_agent=user_agent, log=log,
                            max_size=max_size, direct_first=False)
        sources, (size, etag) = list(ms), shim
    else:
        # 直连优先：先给直连一个很短的 Range 探测窗口。
        # 直连不通（超时/拒绝/非 206/错误页/龟速）就**不让它参与分片** —— 否则
        # 8 个 worker 会轮流卡死在同一条不通的链路上，把加速源也一起拖慢。
        got = _probe_source("", url, user_agent, timeout=DIRECT_PROBE_TIMEOUT,
                            min_speed=DIRECT_MIN_SPEED)
        if isinstance(got, tuple):
            sources, (size, etag) = [""] + ms, got
            emit("    直连可用，优先走直连（其余 %d 个加速源仅作分片容灾）" % len(ms))
        else:
            emit("    直连不可用（%s），改走加速源" % (got.reason,))
            shim = _probe_range(ms, url, user_agent)
            if shim is None:
                emit("    加速源也不支持 Range 分片，回退单流下载")
                return download(url, dest, mirrors=ms, description=description,
                                expected_sha256=expected_sha256, expected_size=expected_size,
                                kind=kind, user_agent=user_agent, log=log,
                                max_size=max_size, direct_first=True)
            sources, (size, etag) = list(ms), shim
    if size <= 0 or size > max_size:
        return False, "文件大小异常（%d 字节）" % size
    if expected_size > 0 and size != expected_size:
        return False, "远端大小 %d 与期望 %d 不一致（镜像可能缓存了旧文件）" % (size, expected_size)

    # 分片数自适应：小文件少切，大文件按 MAX_CHUNKS 抬高单片大小，避免请求风暴
    if (size + chunk - 1) // chunk > MAX_CHUNKS:
        chunk = (size + MAX_CHUNKS - 1) // MAX_CHUNKS
    nchunks = (size + chunk - 1) // chunk
    plan = [(i * chunk, min((i + 1) * chunk, size) - 1) for i in range(nchunks)]
    done = [False] * nchunks
    lock = threading.Lock()
    failures = []
    written = [0]
    started_at = time.time()
    degraded = set()
    streaks = dict((m, 0) for m in sources)   # 空串=直连，和镜像一样记账
    speed = {}       # 源 -> EWMA 速度（B/s）
    samples = {}     # 源 -> 成功分片数
    live = [0]       # 当前在跑的连接数（增量自检用）

    def median_speed():
        vals = [speed[m] for m in speed if samples.get(m, 0) >= SPEED_MIN_SAMPLES]
        if not vals:
            return 0.0
        vals.sort()
        return vals[len(vals) // 2]

    def pick_source(index, attempt):
        """按分片轮转分配源（源码里空串=直连）；跳过已降级的源，全部降级时仍兜底轮转。

        直连优先的语义：只要直连还没被降级，它就是队列里的第一顺位，
        分片先给直连；直连卡住/被墙后才轮到加速源接手。
        """
        candidates = [m for m in sources if m not in degraded]
        if not candidates:
            candidates = list(sources)
        return candidates[(index + attempt) % len(candidates)]

    def hedge_timeout(need, attempt, source=""):
        """单片墙钟上限：正常成本 = 片字节 / 全局速度（无样本时用基线兜底）。

        直连再额外收紧一档：直连「连得上但被丢包」时不会报错，只会静默慢下来，
        等它自然超时等于整次下载都被拖住；宁可早点把这一片改派给加速源。
        """
        sp = median_speed() or BASELINE_SPEED
        cost = need / float(sp)
        d = cost * (HEDGE_FIRST if attempt == 0 else HEDGE_NEXT)
        if _is_direct(source):
            d = min(d, DIRECT_STALL_TIMEOUT)
        return max(HEDGE_FLOOR, d)

    def arrange_abort():
        """并行是否真的比单流快？比对口径：平均单连接速度 vs 单连接基线。

        不能用「已下字节 / 速度」外推总时长——那是按已并发速度线性外推，天然得出
        「你没赢」。只有「每条连接都比基线还慢」才说明并发没带来收益，此时单流不会更差。
        """
        with lock:
            w = written[0]
            if w * 4 < size:            # 进度不足 25%，样本太少
                return False
            if len([1 for m in samples if samples.get(m, 0) >= SPEED_MIN_SAMPLES]) == 0:
                return False
        elapsed = time.time() - started_at
        watch = max(FALLBACK_MIN_WATCH, size / float(BASELINE_SPEED) / 4.0)
        if elapsed < watch:
            return False
        sp = median_speed()
        if sp <= 0:
            return False
        with lock:
            conns = max(1, live[0])
        per_conn = sp / conns
        return per_conn < BASELINE_SPEED * FALLBACK_FACTOR

    def fetch_chunk(index):
        start, end = plan[index]
        need = end - start + 1
        last = None
        attempts = max_chunk_retries * max(1, len(sources))
        for attempt in range(attempts):
            if abort[0]:
                raise DownloadError("并行下载已被判为无收益")
            m = pick_source(index, attempt)
            target = source_url(m, url)
            started = time.time()
            try:
                data = _fetch_range(target, start, end, etag, user_agent,
                                    timeout=min(CHUNK_READ_TIMEOUT, hedge_timeout(need, attempt, m)))
            except Exception as e:  # noqa: BLE001 - 换源重试，原因留最后一次
                last = e
                with lock:
                    if _is_timeout(e):
                        # 镜像「慢」只改派，不记失败；但**直连**慢/卡住一律记账：
                        # 直连不通报的是 timeout，不在这里降级它，其余分片还会轮流撞它。
                        if _is_direct(m):
                            streaks[m] = streaks.get(m, 0) + 1
                            if streaks[m] >= DIRECT_DEGRADE_AFTER and m not in degraded:
                                degraded.add(m)
                                emit("    直连分片超时 %d 次，本次下载内改走加速源" % streaks[m])
                    else:
                        streaks[m] = streaks.get(m, 0) + 1
                        if streaks[m] >= MIRROR_DEGRADE_AFTER and m not in degraded:
                            degraded.add(m)
                            emit("    镜像 %s 连续失败 %d 次，本次下载内降级" % (m or "直连", streaks[m]))
                time.sleep(min(0.2 * (attempt + 1), 1.5))
                continue
            dt = time.time() - started
            try:
                with lock:
                    with open(tmp, "r+b") as f:
                        f.seek(start)
                        f.write(data)
                    done[index] = True
                    written[0] += need
                    streaks[m] = 0
                    v = need / dt if dt > 0 else 0.0
                    if m in speed:
                        speed[m] = (1 - SPEED_ALPHA) * speed[m] + SPEED_ALPHA * v
                    else:
                        speed[m] = v
                    samples[m] = samples.get(m, 0) + 1
                    med = median_speed()
                    if med > 0:
                        for mm in list(speed):
                            if samples.get(mm, 0) >= SPEED_MIN_SAMPLES and speed[mm] < med * SPEED_SLOW_RATIO:
                                if mm not in degraded:
                                    degraded.add(mm)
                                    emit("    %s 明显偏慢，本次下载内降级" % ("直连" if _is_direct(mm) else "镜像 " + mm,))
                    emit("    分片 %d/%d（%s，%.1f/%.1fMB）" % (
                        index + 1, nchunks, "直连" if _is_direct(m) else m.replace("https://", "").strip("/"),
                        written[0] / 1048576, size / 1048576))
            except OSError as e:
                last = e
                time.sleep(0.2)
                continue
            return True
        raise DownloadError("分片 %d（bytes %d-%d）重试后仍失败: %s" % (index, start, end, last))

    abort = [False]
    with open(tmp, "wb") as f:
        f.truncate(size)

    queue_lock = threading.Lock()
    next_index = [0]

    def runner():
        while True:
            with queue_lock:
                i = next_index[0]
                next_index[0] += 1
            if i >= nchunks or abort[0]:
                return
            with lock:
                live[0] += 1
            try:
                fetch_chunk(i)
            except Exception as e:  # noqa: BLE001
                with lock:
                    failures.append(str(e))
            finally:
                with lock:
                    live[0] -= 1

    threads = []
    for _ in range(max(1, min(workers, nchunks))):
        t = threading.Thread(target=runner, daemon=True)
        t.start()
        threads.append(t)

    # 监视线程：并行无收益时尽早叫停，交给下面的单流回退（单流同样直连优先）
    def monitor():
        while not abort[0] and any(t.is_alive() for t in threads):
            time.sleep(0.5)
            if arrange_abort():
                abort[0] = True
                emit("    并行未提速（平均单连接 %.0f KB/s < 基线 %.0f KB/s），回退单流"
                     % (median_speed() / 1024, BASELINE_SPEED / 1024))
                return
    mt = threading.Thread(target=monitor, daemon=True)
    mt.start()
    for t in threads:
        t.join()
    abort[0] = True
    mt.join(timeout=1.0)

    if abort[0] and not all(done):
        if os.path.exists(tmp):
            os.remove(tmp)
        return download(url, dest, mirrors=ms, description=description,
                        expected_sha256=expected_sha256, expected_size=expected_size,
                        kind=kind, user_agent=user_agent, log=log, max_size=max_size,
                        direct_first=direct_first)

    missing = sum(1 for d in done if not d)
    if failures or missing:
        if os.path.exists(tmp):
            os.remove(tmp)
        reason = "分片下载未完成（缺失 %d/%d 片）: %s" % (
            missing, nchunks, "; ".join(failures[:3]) or "存在缺失分片")
        # 真正的失败（重试耗尽）不回退单流：单流只会更慢还多等一轮。
        # 上面「并行无收益」的自动回退是另一回事（单流确实可能更快）。
        return False, reason

    ok, reason = verify_payload(tmp, expected_sha256, size, kind)
    if not ok:
        os.remove(tmp)
        return False, reason
    os.replace(tmp, dest)
    emit("  下载完成 %s（%d 片 / %d 并发）" % (
        description or os.path.basename(dest), nchunks, len(threads)))
    return True, ""


def _is_timeout(exc):
    """是否「慢」（超时/取消）而不是「坏」（5xx、偏移不符、长度不符）。"""
    if isinstance(exc, (socket.timeout, TimeoutError)):
        return True
    msg = str(exc)
    return "超时" in msg or "timed out" in msg


class _ProbeFail(object):
    """探测失败的原因（用对象而不是 None，方便把「为什么不用直连」写进日志）。"""

    __slots__ = ("reason",)

    def __init__(self, reason):
        self.reason = reason


def _probe_source(source, url, user_agent, timeout=None, min_speed=0):
    """探测单个源（空串=直连）能否做 Range 分片：可用返回 (size, etag)，否则 _ProbeFail。

    比 _probe_range 严格的地方（正是直连需要的判据）：
      - 必须 206 + 合法 Content-Range（代理错误页常是 200 + HTML，直接判死）；
      - 探测窗口要真的读到字节，且速度不低于 min_speed（「连得上但被限死」等于不可用，
        否则它会被 8 个 worker 分摊成一堆超时，比不用它还慢）。
    """
    timeout = timeout or PROBE_TIMEOUT
    window = 64 * 1024
    target = source_url(source, url)
    try:
        req = urllib.request.Request(target, headers={
            "User-Agent": user_agent, "Range": "bytes=0-%d" % (window - 1),
            "Cache-Control": "no-cache"})
        t0 = time.time()
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status != 206:
                return _ProbeFail("不支持分片（HTTP %d）" % resp.status)
            rng = parse_content_range(resp.headers.get("Content-Range", ""))
            if rng is None:
                return _ProbeFail("Content-Range 缺失或非法")
            body = resp.read(window)
            dt = time.time() - t0
            etag = resp.headers.get("ETag", "")
    except urllib.error.HTTPError as e:
        return _ProbeFail("HTTP %d" % e.code)
    except urllib.error.URLError as e:
        return _ProbeFail("网络错误: %s" % (e.reason,))
    except (socket.timeout, TimeoutError):
        return _ProbeFail("%gs 内无响应（超时）" % timeout)
    except Exception as e:  # noqa: BLE001
        return _ProbeFail(str(e)[:60])
    if not body:
        return _ProbeFail("探测窗口无数据")
    speed = len(body) / dt if dt > 0 else 0.0
    if min_speed and speed < min_speed:
        return _ProbeFail("速度仅 %.0f KB/s，低于 %.0f KB/s 门槛" % (speed / 1024, min_speed / 1024))
    return rng[2], ("" if etag.startswith("W/") else etag)


def _probe_range(mirrors, url, user_agent):
    """探测总大小与 ETag 基线；不支持 Range 或全部失败返回 None。"""
    for m in list(mirrors) + [""]:
        try:
            req = urllib.request.Request(
                (m + url) if m else url,
                headers={"User-Agent": user_agent, "Range": "bytes=0-0",
                         "Cache-Control": "no-cache"})
            with urllib.request.urlopen(req, timeout=PROBE_TIMEOUT) as resp:
                body = resp.read(1)
                if resp.status != 206:
                    continue  # 该镜像不支持 Range，换下一个探测
                cr = resp.headers.get("Content-Range", "").strip()
                parsed = parse_content_range(cr)
                if not parsed or len(body) != 1:
                    continue
                etag = resp.headers.get("ETag", "")
                # 总长度取自 Content-Range 的 /total；start 不一定是 0（bytes=0-0 也
                # 可能被回成别的区间），所以不能用 start 猜大小。
                return parsed[2], ("" if etag.startswith("W/") else etag)
        except Exception:
            continue
    return None


def parse_content_range(value):
    """'bytes 0-99/1000' -> (0, 99, 1000)；'' / '*' 总长度或格式非法返回 None。"""
    m = CONTENT_RANGE_RE.match((value or "").strip())
    if not m:
        return None
    start, end, total = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if end < start or total <= end:
        return None
    return start, end, total


def _fetch_range(url, start, end, etag, user_agent, timeout=CHUNK_READ_TIMEOUT):
    """取一个分片并做三重校验：206 + Content-Range 精确匹配 + ETag 与基线一致。

    任何一项不符都抛错，由调用方换镜像重试 —— 这正是「分片来自不同镜像」还能
    保证一致性的原因：ETag 相同说明各镜像背后是同一份对象。
    """
    req = urllib.request.Request(url, headers={
        "User-Agent": user_agent, "Range": "bytes=%d-%d" % (start, end),
        "Cache-Control": "no-cache"})
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        raise DownloadError("HTTP %d" % e.code)
    except urllib.error.URLError as e:
        raise DownloadError("网络错误: %s" % (e.reason,))
    except (socket.timeout, TimeoutError):
        raise DownloadError("分片读取超时（%ds 无数据）" % timeout)
    with resp:
        if resp.status != 206:
            raise DownloadError("非 206 响应（HTTP %d）" % resp.status)
        if etag:
            got = resp.headers.get("ETag", "")
            if got and got != etag:
                raise DownloadError("ETag 变化（%s != %s）" % (got, etag))
        rng = parse_content_range(resp.headers.get("Content-Range", ""))
        if rng is None:
            raise DownloadError("Content-Range 缺失或非法")
        if rng[0] != start or rng[1] != end:
            raise DownloadError("Content-Range 偏移不符（%d-%d != %d-%d）" % (rng[0], rng[1], start, end))
        want = end - start + 1
        buf = bytearray()
        while len(buf) < want:
            piece = resp.read(want - len(buf))
            if not piece:
                break
            buf.extend(piece)
    if len(buf) != want:
        raise DownloadError("分片长度不符（%d != %d）" % (len(buf), want))
    return bytes(buf)
