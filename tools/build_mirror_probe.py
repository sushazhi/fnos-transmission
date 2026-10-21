#!/usr/bin/env python3
"""build_mirror_probe - 构建期实测加速源，并生成要打进 fpk 的镜像清单

用法：
    python tools/build_mirror_probe.py --probe-url <sample-url> [--out app/bin/update-mirrors.txt]
    python tools/build_mirror_probe.py --self-test        # 离线自检，不联网

为什么在构建期实测而不是写死顺序
--------------------------------
加速源随时会挂或被墙，写死的顺序在发版当天可能整条链路都不通。构建期本来就
必须下载 transmission-daemon 与 SeedArk（都在 GitHub Releases），顺手对同一个
sample-url 的**第一个字节区间**做一次测速，就能得到当天的真实可用性：
  - 可用（拿到 206/200 且有字节）→ 收进清单，按实测速度排序
  - 不可用 → 不写进清单（应用内更新就不再浪费一次超时）
实在全挂时退回 gh_mirror.MIRRORS 的默认顺序（宁可给用户一个可能能用的兜底，
也不要打包一个空清单）。

生成的文件：app/bin/update-mirrors.txt（每行一个前缀，'#' 开头为注释）。
SeedArk 启动时读它；本仓库 build.py 下载资产时也用它。
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import gh_mirror  # noqa: E402

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_OUT = os.path.join(PROJECT_DIR, "app", "bin", gh_mirror.MIRROR_MANIFEST_NAME)


def log(msg):
    sys.stdout.write(str(msg) + "\n")
    sys.stdout.flush()


def probe(mirrors=None, sample_url="", rounds=1, timeout=10):
    """逐个镜像测速，返回 [(mirror, bytes_per_sec)]，按速度降序（失败为 0）。"""
    ms = list(gh_mirror.MIRRORS if mirrors is None else mirrors)
    rows = []
    for m in ms:
        speed = 0.0
        if sample_url:
            speed = gh_mirror._probe_speed(m + sample_url, rounds=rounds, timeout=timeout)
        rows.append((m, speed))
    rows.sort(key=lambda r: r[1], reverse=True)
    return rows


def main(argv=None):
    p = argparse.ArgumentParser(description="实测 GitHub 加速源并生成镜像清单")
    p.add_argument("--probe-url", default="", help="用于测速的 GitHub 资源地址（建议用本次要下载的 fpk）")
    p.add_argument("--out", default=DEFAULT_OUT, help="清单输出路径（默认 app/bin/update-mirrors.txt）")
    p.add_argument("--rounds", type=int, default=2, help="每个镜像测速轮数，取最快一次")
    p.add_argument("--timeout", type=float, default=10, help="单次测速超时（秒）")
    p.add_argument("--self-test", action="store_true", help="离线自检（不联网、不写文件）")
    args = p.parse_args(argv)

    if args.self_test:
        return self_test()

    rows = probe(sample_url=args.probe_url, rounds=args.rounds, timeout=args.timeout)
    for m, speed in rows:
        log("  %-32s %s" % (m, ("%.2f MB/s" % (speed / 1048576)) if speed > 0 else "不可用"))
    usable = [m for m, s in rows if s > 0]
    if not usable:
        log("  警告：所有加速源实测不可用，退回默认顺序（仍写入清单作为兜底）")
        usable = list(gh_mirror.MIRRORS)
        comment = "构建期实测：全部不可用，已回退默认顺序（%s）" % _now()
    else:
        dropped = [m for m, s in rows if s <= 0]
        comment = "构建期实测排序 %s" % _now()
        if dropped:
            comment += "；本次剔除不可用源：%s" % ", ".join(dropped)

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline="\n") as f:
        f.write(gh_mirror.render_manifest(usable, comment=comment))
    log("  镜像清单已写入 %s（%d 个源）" % (args.out, len(usable)))
    return 0


def _now():
    import datetime
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")


def self_test():
    """离线自检：覆盖解析/归一化/清单生成/URL 展开/坏数据防御。"""
    ok = True

    def check(name, cond, detail=""):
        nonlocal ok
        log(("  ok   " if cond else "  FAIL ") + name + ("" if cond else "  << " + detail))
        ok = ok and bool(cond)

    check("默认列表非空且无旧代理",
          gh_mirror.MIRRORS and not any(gh_mirror.is_obsolete(m) for m in gh_mirror.MIRRORS))
    check("首选为 gh-proxy.com", gh_mirror.MIRRORS[0] == "https://gh-proxy.com/",
          str(gh_mirror.MIRRORS[:1]))
    check("归一化补斜杠", gh_mirror.normalize_mirror("https://gh-proxy.com") == "https://gh-proxy.com/")
    check("归一化拒绝非 http", gh_mirror.normalize_mirror("ftp://x/") == "")
    check("归一化拒绝空", gh_mirror.normalize_mirror("  ") == "")

    text = "# c\nhttps://gh-proxy.com/\n\nhttps://gh.dpik.top/\nhttps://ghfast.top\nhttps://gh-proxy.com/\nbad line\n"
    parsed = gh_mirror.parse_mirrors(text)
    check("解析保序去重", parsed == ["https://gh-proxy.com/", "https://gh.dpik.top/", "https://ghfast.top/"],
          str(parsed))

    man = gh_mirror.render_manifest(["https://gh-proxy.com/"], comment="x")
    check("清单含注释与地址", "#" in man and man.strip().endswith("https://gh-proxy.com/"))

    urls = gh_mirror.build_urls("https://github.com/a/b/releases/download/v1/x.fpk",
                                mirrors=["https://m1/", "https://m2/"])
    check("URL 展开=镜像×2+直连",
          urls == ["https://m1/https://github.com/a/b/releases/download/v1/x.fpk",
                   "https://m2/https://github.com/a/b/releases/download/v1/x.fpk",
                   "https://github.com/a/b/releases/download/v1/x.fpk"], str(urls))

    # 清单读写往返：不存在时回落默认，旧代理被剔除
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "update-mirrors.txt")
        check("缺失清单回退默认", gh_mirror.load_manifest(p) == list(gh_mirror.MIRRORS))
        with open(p, "w", encoding="utf-8") as f:
            f.write("https://gh.dpik.top/\nhttps://ghfast.top/\n")
        check("加载清单剔除旧代理", gh_mirror.load_manifest(p) == ["https://ghfast.top/"],
              str(gh_mirror.load_manifest(p)))

        # 校验：错误魔数必须被拒
        bad = os.path.join(d, "bad.fpk")
        with open(bad, "wb") as f:
            f.write(b"<html>not a package</html>")
        good, reason = gh_mirror.verify_payload(bad, kind="fpk")
        check("错误页魔数被拒", not good, reason)

        # 分片边界：整除 / 余数 / 小于一片
        for size, chunk, want in ((16, 4, 4), (10, 4, 3), (3, 4, 1)):
            got = (size + chunk - 1) // chunk
            check("分片数 size=%d chunk=%d" % (size, chunk), got == want, "%d != %d" % (got, want))

    log("self-test %s" % ("PASSED" if ok else "FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
