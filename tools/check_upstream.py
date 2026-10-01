#!/usr/bin/env python3
"""检查上游 transmission/transmission 是否有新版本，有则把 manifest 改到位。

为什么需要这个脚本
------------------
本仓库是飞牛 fnOS 的适配层：上游 Transmission 只提供源码 tarball（构建 workflow 从
releases/download/v<版本> 取源码，在 Alpine 容器里 musl 全静态编译 transmission-daemon）。
所以「升级上游」在本仓库里等价于「改几个数字」，而不是「合并上游 diff」。改动点少，
但互相关联，漏掉任何一处都会留下不一致的产物：

  1. manifest  version    —— x.y.z.N；x.y.z 必须等于上游版本，N 是适配层修订号
  2. manifest  changelog  —— 版本说明（同时是 Release notes 的来源）
  3. README.md 徽章        —— badge/Transmission-x.y.z-blue
  4. README.md 开源项目表  —— 「| [Transmission](...) | x.y.z | ...」那一行

3/4 漏改不会让构建失败，但 CI 打包的是仓库根目录，README.md 会进 fpk，于是
「随包分发的文档写着一个过时的上游版本号」—— 属于静默失真。所以本脚本对这两处
也做**严格匹配**：匹配不到就报错退出，绝不悄悄跳过。宁可让这次自动发版失败
（下个月还会再来一次），也不要发一个文档对不上的包。

版本号规则
----------
    上游 4.1.3 + 适配层第 4 次修订  ->  4.1.3.4
    上游发新版本 4.1.4              ->  4.1.4.0（修订号归零）
    上游没变但要重打包（--force）    ->  4.1.3.5（修订号 +1）

用法
----
    python3 tools/check_upstream.py --detect        # 只检查，不改任何文件
    python3 tools/check_upstream.py --apply         # 检查并应用（无更新则不改动）
    python3 tools/check_upstream.py --apply --force # 上游无更新也按当前上游重打一次
    python3 tools/check_upstream.py --apply --upstream-version 4.1.4

在 GitHub Actions 里会把结果写进 $GITHUB_OUTPUT
（update / newer / upstream_version / app_version / tag / reason），供后续步骤使用；
本地运行时该环境变量不存在，写输出就是空操作。
"""
import json
import os
import re
import sys
import urllib.request

# Windows 控制台默认 GBK，本脚本会打印中文；不设置的话本地调试会 UnicodeEncodeError。
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST_PATH = os.path.join(PROJECT_DIR, "manifest")
README_PATH = os.path.join(PROJECT_DIR, "README.md")

UPSTREAM_REPO = "transmission/transmission"
RELEASES_LATEST_API = "https://api.github.com/repos/%s/releases/latest" % UPSTREAM_REPO
TAGS_API = "https://api.github.com/repos/%s/tags?per_page=100" % UPSTREAM_REPO

# 上游 tag 形态：4.1.3 / v4.1.3。带后缀的（4.1.4-beta.1）一律不认 ——
# 自动流水线只跟正式版本，预发布要不要跟由人决定。
VER_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")

# changelog 最多保留几条版本条目。manifest 的 desc 与 changelog 都会进包内 manifest、
# 都会显示在应用中心里，不封顶的话会一直长下去。
MAX_CHANGELOG_ENTRIES = 5

# README 里两处对外可见的版本标注。各自必须**恰好匹配一处**，否则报错退出。
README_BADGE_RE = re.compile(r"(badge/Transmission-)(\d+\.\d+\.\d+)(-blue)")
README_TABLE_RE = re.compile(
    r"(?m)^(\| \[Transmission\]\(https://github\.com/transmission/transmission\) \| )"
    r"(\d+\.\d+\.\d+)( \|)"
)

# manifest 的单行结构：key = value（保留等号两侧空白，避免改写后对齐变样）
MANIFEST_LINE_RE = re.compile(
    r"^(?P<key>[A-Za-z_][A-Za-z0-9_]*)(?P<sep>\s*=\s*)(?P<val>.*)$"
)


def log(msg=""):
    sys.stdout.write(str(msg) + "\n")
    sys.stdout.flush()


# ---------------------------------------------------------------------------
# 基础工具
# ---------------------------------------------------------------------------

def parse_ver(s):
    m = VER_RE.match((s or "").strip())
    return tuple(int(x) for x in m.groups()) if m else None


def ver_str(v):
    return ".".join(str(x) for x in v)


def api_get(url, token=None):
    headers = {"User-Agent": "fnos-transmission-check-upstream",
               "Accept": "application/vnd.github+json"}
    if token:
        # 只为抬高限流额度（匿名 60 次/小时）；不需要任何额外权限。
        headers["Authorization"] = "Bearer %s" % token
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def upstream_latest(token):
    """取上游最新正式版本号。

    releases/latest 是权威来源 —— 上游用 Release 发版，构建 workflow 也是从
    releases/download/v<版本> 取源码 tarball，两者必须指同一个版本。tags 只作兜底
    （万一上游先打 tag、后发 Release，中间这段时间也不至于误判「无更新」）。
    """
    errors = []
    try:
        rel = api_get(RELEASES_LATEST_API, token)
        v = parse_ver(rel.get("tag_name", ""))
        if v:
            return v
        errors.append("releases/latest 的 tag_name 不是正式版本号: %r"
                      % rel.get("tag_name"))
    except Exception as e:
        errors.append("releases/latest 读取失败: %s" % e)

    try:
        tags = api_get(TAGS_API, token)
        vs = [parse_ver(t.get("name", "")) for t in tags]
        vs = [v for v in vs if v]
        if vs:
            return max(vs)
        errors.append("tags 里没有正式版本号")
    except Exception as e:
        errors.append("tags 读取失败: %s" % e)

    raise RuntimeError("; ".join(errors))


def upstream_versions(token):
    """列出上游所有正式版本号（来自 tags）。仅用于校验人工传入的 --upstream-version。"""
    tags = api_get(TAGS_API, token)
    vs = [parse_ver(t.get("name", "")) for t in tags]
    return set(v for v in vs if v)


def read_text(path):
    # newline="" 不做行尾转换，原样读进来；配合 write_text 可以保证
    # 「只改内容、不动行尾」，不会因为脚本在 Windows 上跑而把 LF 变成 CRLF。
    with open(path, "r", encoding="utf-8", newline="") as f:
        return f.read()


def write_text(path, text):
    # 先写同目录下的临时文件再 os.replace 顶替：os.replace 在同一文件系统内是原子的，
    # 所以不会出现「写了一半的 manifest」——那种半截文件会让下一次运行读到坏版本号。
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# manifest 读写
# ---------------------------------------------------------------------------

def manifest_version(text):
    m = re.search(r"(?m)^version\s*=\s*(\S+)\s*$", text)
    if not m:
        raise SystemExit("ERROR: manifest 里读不到 version")
    return m.group(1)


def split_app_version(s):
    """把应用版本拆成 (上游三元组, 适配层修订号)。

    只接受 3 段（4.1.3）或 4 段（4.1.3.4）全数字形态；其它形态直接报错，
    不要猜 —— 猜错会写出一个既不是上游版本、也无法与 tag 对应的号。
    """
    parts = s.split(".")
    if len(parts) not in (3, 4) or not all(p.isdigit() for p in parts):
        raise SystemExit(
            "ERROR: manifest 的 version=%r 不是 3 段或 4 段全数字形态，无法自动推算"
            "（期望形如 4.1.3 或 4.1.3.4）。\n"
            "       这是**故意**不猜：猜错会写出一个既不对应上游、也无法与 tag 对应的版本号。\n"
            "       处理方式：把 manifest 的 version 改成「上游 x.y.z + 适配层修订号 N」形态"
            "（如 4.1.4.0），再手动 workflow_dispatch 重跑本 workflow。" % s)
    up = tuple(int(x) for x in parts[:3])
    rev = int(parts[3]) if len(parts) == 4 else 0
    return up, rev


def split_lines_keepends(text):
    # 只在 \n 处切分（str.splitlines 还会在 \v \f \u2028 等处切，manifest 用不着）
    return re.split(r"(?<=\n)", text)


def set_manifest_key(text, key, value):
    """按行改写 manifest 的某个键，保留等号两侧空白与行尾。

    用逐行替换而不是对整段文本做 re.sub：desc / changelog 都是超长单行，
    连续两次整段替换时第二次的偏移会失效。
    """
    lines = split_lines_keepends(text)
    # value 是原样插进行内的：一旦含换行就会凭空多出一行 manifest 内容，而 hits 仍是 1，
    # 下面的唯一性守卫拦不住。当前所有调用点的 value 都不含换行，这里只是把「不可能」
    # 变成「写坏之前就报错」。
    if "\n" in value or "\r" in value:
        raise SystemExit("ERROR: manifest 的 %s 值含换行，拒绝写入: %r" % (key, value))
    hits = 0
    for i, line in enumerate(lines):
        m = MANIFEST_LINE_RE.match(line.rstrip("\r\n"))
        if not m or m.group("key") != key:
            continue
        eol = "\r\n" if line.endswith("\r\n") else ("\n" if line.endswith("\n") else "")
        lines[i] = "%s%s%s%s" % (m.group("key"), m.group("sep"), value, eol)
        hits += 1
    if hits != 1:
        raise SystemExit("ERROR: manifest 里 %s 匹配到 %d 行，应为 1 行" % (key, hits))
    return "".join(lines)


def split_changelog(value):
    """把 changelog 拆成 (抬头, [版本条目...])。

    现网形态：`更新日志<br>v4.1.3.4:<br>1. …<br>2. …`
    条目边界 = `<br>` 后面紧跟 `v<数字>.<数字>.<数字>`。
    """
    m = re.search(r"<br>v\d+\.\d+\.\d+", value)
    if not m:
        return value, []
    head = value[: m.start()]
    rest = value[m.start():]
    entries = [e for e in re.split(r"(?=<br>v\d+\.\d+\.\d+)", rest) if e.strip()]
    return head, entries


def make_changelog_entry(app_version, upstream_version, is_new_upstream):
    if is_new_upstream:
        items = [
            "Transmission 上游升级到 %s：transmission-daemon 于 Alpine 容器内 musl 全静态"
            "编译，CI 自动重建 arm64/amd64 双架构" % upstream_version,
            "WebUI 面板（SeedArk）在构建时自动取最新 release，无需改 manifest",
            "本条目由 GitHub Actions 月末检查上游后自动生成",
        ]
    else:
        items = [
            "按当前上游 %s 重新打包发布（适配层修订号 +1），daemon 与面板沿用同一上游版本"
            % upstream_version,
            "本条目由 GitHub Actions 手动强制触发（--force）",
        ]
    body = "".join("<br>%d. %s" % (i, t) for i, t in enumerate(items, 1))
    return "<br>v%s:%s" % (app_version, body)


def bump_manifest(text, app_version, upstream_version, is_new_upstream):
    cur = manifest_version(text)
    if cur == app_version:
        log("  manifest: version 已是 %s，changelog 保持不变" % app_version)
        return text, False

    # 末尾的 \r 不算值的一部分：CRLF 检出时 (?m)$ 匹配在 \n 前，而 `.` 会吃掉 \r，
    # 不剥掉的话 set_manifest_key 再补一次行尾就写成了 `...\r\r\n`。
    m = re.search(r"(?m)^changelog[ \t]*=[ \t]*(.*?)[ \t\r]*$", text)
    if not m:
        raise SystemExit("ERROR: manifest 里读不到 changelog 行")

    head, entries = split_changelog(m.group(1))
    # 裁剪（只留最近 MAX_CHANGELOG_ENTRIES 条）完全依赖上面那个 `<br>v\d+\.\d+\.\d+` 形态。
    # 若有人手写了一条不带 v 前缀的条目，entries 会解析成空，于是「只追加、永不裁剪」，
    # MAX_CHANGELOG_ENTRIES 静默失效 —— 值只会越来越长。这里把它显式说出来。
    if not entries and "<br>" in m.group(1):
        log(" 警告: changelog 里有 <br> 但没有可识别的 `v<数字>.<数字>.<数字>` 条目，"
            "本次只追加不裁剪（%d 条上限未生效）" % MAX_CHANGELOG_ENTRIES)
    entry = make_changelog_entry(app_version, upstream_version, is_new_upstream)
    # 抬头为空（changelog 原本没有版本条目）时不要把开头那个 <br> 带进去，
    # 否则会写出 `<br>v4.1.4.0:…` 这种以分隔符开头的值。
    # 用切片而不是 str.lstrip("<br>")：lstrip 的参数是字符集合，
    # 会连带吃掉 'b'/'r' 等字符（这里恰好不触发，但不能靠运气）。
    if not head.strip():
        value = (entry[4:] if entry.startswith("<br>") else entry) \
            + "".join(entries[: MAX_CHANGELOG_ENTRIES - 1])
    else:
        value = head + entry + "".join(entries[: MAX_CHANGELOG_ENTRIES - 1])

    text = set_manifest_key(text, "version", app_version)
    text = set_manifest_key(text, "changelog", value)
    log("  manifest: version %s -> %s，changelog 追加条目（共保留 %d 条）"
        % (cur, app_version, min(len(entries) + 1, MAX_CHANGELOG_ENTRIES)))
    return text, True


# ---------------------------------------------------------------------------
# README 版本标注
# ---------------------------------------------------------------------------

def rewrite_readme(text, upstream_version):
    new, n1 = README_BADGE_RE.subn(r"\g<1>%s\g<3>" % upstream_version, text)
    if n1 != 1:
        raise SystemExit(
            "ERROR: README 徽章里的 Transmission 版本号匹配到 %d 处，应为 1 处。"
            "README 的版本标注被改写过？请同步更新 tools/check_upstream.py 的正则"
            "（README_BADGE_RE），否则会发出文档与实际上游版本不符的包。" % n1)

    new, n2 = README_TABLE_RE.subn(r"\g<1>%s\g<3>" % upstream_version, new)
    if n2 != 1:
        raise SystemExit(
            "ERROR: README 开源项目表里的 Transmission 版本号匹配到 %d 处，应为 1 处。"
            "README 的版本标注被改写过？请同步更新 tools/check_upstream.py 的正则"
            "（README_TABLE_RE），否则会发出文档与实际上游版本不符的包。" % n2)

    log("  README: 徽章与开源项目表 -> Transmission %s" % upstream_version)
    return new


# ---------------------------------------------------------------------------
# GitHub Actions 输出
# ---------------------------------------------------------------------------

def emit_outputs(pairs):
    out = os.environ.get("GITHUB_OUTPUT", "").strip()
    for k, v in pairs.items():
        log("  output %s=%s" % (k, v))
        if out:
            with open(out, "a", encoding="utf-8") as f:
                f.write("%s=%s\n" % (k, v))


# ---------------------------------------------------------------------------

def main():
    args = sys.argv[1:]
    detect_only = "--detect" in args
    apply_changes = "--apply" in args
    force = "--force" in args
    if not detect_only and not apply_changes:
        log(__doc__)
        sys.exit(2)

    want = ""
    if "--upstream-version" in args:
        i = args.index("--upstream-version")
        if i + 1 >= len(args):
            raise SystemExit("ERROR: --upstream-version 后面缺少版本号")
        want = args[i + 1]
        if not parse_ver(want):
            raise SystemExit("ERROR: --upstream-version 不是合法版本号: %r" % want)
        want = ver_str(parse_ver(want))

    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""

    manifest_text = read_text(MANIFEST_PATH)
    readme_text = read_text(README_PATH)
    cur_app = manifest_version(manifest_text)
    cur_up, cur_rev = split_app_version(cur_app)

    log("=" * 56)
    log(" 上游版本检查 - Transmission for fnOS")
    log(" 上游仓库  : %s" % UPSTREAM_REPO)
    log(" 当前版本  : %s（上游 %s + 适配层修订 %d）" % (cur_app, ver_str(cur_up), cur_rev))
    log("=" * 56)

    if want:
        # 人工指定的版本必须在上游真实存在，否则会把一个**永远构建不出来**的版本号
        # 提交进 main：build-and-release.yml 随后拉
        # releases/download/v<版本>/transmission-<版本>.tar.xz 会 404，job 变红，
        # 而 main 上的 version 已经改了 —— 下个月末运行读它判定「无更新」，不会再纠正。
        # 所以这里宁可直接失败，也不写下一个拉不到源码的版本号。
        try:
            known = upstream_versions(token)
        except Exception as e:
            raise SystemExit(
                "ERROR: 无法从上游取得版本列表来校验 --upstream-version %s，本次检查失败: %s\n"
                "       （校验不了就不写：写错版本号的代价是它永远构建不出来）"
                % (ver_str(parse_ver(want)), e))
        wv = parse_ver(want)
        if wv not in known:
            near = ", ".join(ver_str(v) for v in sorted(known)[-6:]) or "（空）"
            raise SystemExit(
                "ERROR: --upstream-version %s 在上游 %s 的 tag 里不存在，拒绝使用。\n"
                "       上游最近版本: %s\n"
                "       注意：即使 tag 存在，也需该版本已发布 Release（构建要从 Release 下载源码包）。"
                % (ver_str(wv), UPSTREAM_REPO, near))
        latest = wv
    else:
        try:
            latest = upstream_latest(token)
        except Exception as e:
            # 取不到上游版本 = 「这次检查失败」，绝不能当成「无更新」静默跳过。
            raise SystemExit("ERROR: 无法确定上游最新版本，本次检查失败: %s" % e)
    log(" 上游最新  : %s" % ver_str(latest))

    if latest < cur_up:
        log(" 注意：上游最新 %s 低于 manifest 里的上游版本 %s，按「无更新」处理（不降级）"
            % (ver_str(latest), ver_str(cur_up)))

    newer = latest > cur_up
    update = newer or force

    if newer:
        app_version = "%s.0" % ver_str(latest)
    elif force:
        app_version = "%s.%d" % (ver_str(cur_up), cur_rev + 1)
    else:
        app_version = cur_app
    tag = "v%s" % app_version

    if newer:
        reason = "上游有新版本 %s -> %s" % (ver_str(cur_up), ver_str(latest))
    elif force:
        reason = "上游无新版本，--force 按当前上游 %s 重打一次" % ver_str(cur_up)
    else:
        reason = "上游无新版本（仍为 %s），跳过" % ver_str(latest)

    log(" 判定      : %s" % ("有新版本" if newer else "已是最新"))
    log(" 目标      : 上游 v%s -> 应用版本 %s（tag %s）"
        % (ver_str(latest if newer else cur_up), app_version, tag))
    log(" 说明      : %s" % reason)

    # update = 「上游确实有更新（或 --force）」，无论哪种模式都如实反映事实。
    # applied = 「这次真的改了文件」；--detect 是本地干跑，永远为 false。
    # 分开两个输出是为了让 `--detect` 的调用方既能知道「有更新」，
    # 又不会被误当成「已经改过了」。
    applied = update and not detect_only

    emit_outputs({
        "update": "true" if update else "false",
        "applied": "true" if applied else "false",
        "newer": "true" if newer else "false",
        "upstream_version": ver_str(latest if newer else cur_up),
        "current_upstream_version": ver_str(cur_up),
        "app_version": app_version,
        "tag": tag,
        "reason": reason,
    })

    if not update:
        log("")
        log(" 上游无更新 —— 未改动任何文件，跳过本次发版。")
        return

    if detect_only:
        log("")
        log(" --detect：只检查，未改动任何文件。")
        return

    log("")
    log("[1/4] 改 manifest（version + changelog）...")
    new_manifest, changed = bump_manifest(
        manifest_text, app_version, ver_str(latest if newer else cur_up), newer)

    log("[2/4] 同步 README 的版本标注 ...")
    # 无论这次是不是新上游都对齐一遍：rewrite_readme 只把标注改成「目标上游版本」，
    # 已经是目标值时结果与原文逐字节相同、不会触发写入。
    # 这样即使上一次运行在写 manifest 之后、写 README 之前崩掉（两个文件不一致），
    # 下一次运行也能自愈 —— 只在上游变化时才修，会让 README 永远停在旧版本。
    target_up = ver_str(latest if newer else cur_up)
    new_readme = rewrite_readme(readme_text, target_up)
    if new_readme == readme_text:
        log("  README 标注已是 %s，无需改动" % target_up)

    log("[3/4] 写文件 ...")
    # 先写 README 再写 manifest：manifest 是「事实来源」，让它的更新最后落地，
    # 中途崩掉时宁可 README 领先（下次运行会自愈）也不要 manifest 领先而 README 落后。
    if new_readme != readme_text:
        write_text(README_PATH, new_readme)
    write_text(MANIFEST_PATH, new_manifest)
    log("  已写入 manifest%s" % ("、README.md" if new_readme != readme_text else ""))

    log("[4/4] 自证 ...")
    got = manifest_version(read_text(MANIFEST_PATH))
    if got != app_version:
        raise SystemExit("ERROR: 写完后 manifest version=%r != 目标 %r" % (got, app_version))
    log("  manifest version 已确认为 %s" % got)

    log("")
    log(" 完成：上游 v%s，应用版本 %s（tag %s）%s"
        % (ver_str(latest if newer else cur_up), app_version, tag,
           "，manifest 已更新" if changed else "，manifest 版本未变"))


if __name__ == "__main__":
    main()
