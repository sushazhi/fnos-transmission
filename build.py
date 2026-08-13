#!/usr/bin/env python3
"""
build.py - Transmission for fnOS 统一打包脚本（跨平台，替代 build.ps1）

用法:
    python build.py [--app-version 4.1.3.2.1] [--transmission-version 4.1.3] [--arch arm64|amd64]
    python build.py --list-versions

特性:
    - 自动检测操作系统 (Windows/Linux)，选择对应的 fnpack 构建工具
    - 参数与 build.ps1 兼容
    - 使用内置 zipfile / tarfile 解压，无需外部工具
"""
import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import urllib.request
import zipfile
import re

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
BUILD_DIR = os.path.join(PROJECT_DIR, ".local-build")
MANIFEST_FILE = os.path.join(PROJECT_DIR, "manifest")

FNPACK_BASE = "https://static2.fnnas.com/fnpack/fnpack-1.2.3"
TRANSMISSION_RELEASES_URL = "https://api.github.com/repos/transmission/transmission/releases"
GITHUB_RELEASES_URL = "https://github.com/sushazhi/fnos-transmission/releases/download"
WEBUI_API_URL = "https://api.github.com/repos/sushazhi/transmission-web/releases/latest"
WEBUI_BASE = "https://ghfast.top/https://github.com/sushazhi/transmission-web/releases/download"

# 下载代理
MAIN_PROXY = "https://gh-proxy.com/"
BINARY_PROXY = "https://ghfast.top/"


def log(msg, color="cyan"):
    sys.stdout.write(msg + "\n")
    sys.stdout.flush()


# 官方 fnpack 支持的平台映射（实测，参考 https://developer.fnnas.com/docs/cli/fnpack/）
#   Windows  : windows-amd64
#   Linux    : linux-amd64 / linux-arm
#   macOS    : darwin-amd64 / darwin-arm64
# 注意：Linux arm64 的官方文件名是 "linux-arm"（非 linux-arm64），已实测验证
def get_platform():
    """返回 'windows' / 'linux' / 'darwin'（macOS）。"""
    s = platform.system().lower()
    if s.startswith("win"):
        return "windows"
    if s.startswith("darwin"):
        return "darwin"
    return "linux"


def get_platform_arch():
    """返回当前机器的 CPU 架构标识（amd64 / arm64）。"""
    m = platform.machine().lower()
    if m in ("aarch64", "arm64", "armv8l", "arm"):
        return "arm64"
    return "amd64"


def get_fnpack_url(arch):
    """根据平台和架构返回 fnpack 下载地址，覆盖 Windows/Linux/macOS。

    - 构建工具 fnpack 必须用【当前开发机】的平台，而非目标应用平台
    - 因此这里用 get_platform() + get_platform_arch() 自动检测开发机
    """
    plat = get_platform()
    if plat == "windows":
        fnpack_arch = "amd64"
    elif plat == "darwin":
        # macOS Apple Silicon 用 arm64，Intel 用 amd64
        fnpack_arch = get_platform_arch()
    else:  # linux
        # Linux arm64 官方文件名为 linux-arm
        fnpack_arch = "arm" if get_platform_arch() == "arm64" else "amd64"
    return f"{FNPACK_BASE}-{plat}-{fnpack_arch}"


def download_proxy(url, out_file, description):
    """依次尝试 MAIN_PROXY -> BINARY_PROXY -> 直连。"""
    url_list = [MAIN_PROXY + url, BINARY_PROXY + url, url]
    for i, u in enumerate(url_list):
        try:
            if os.path.exists(out_file):
                os.remove(out_file)
            log(f"    Trying {u[:70]}...", "gray")
            req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=180) as resp:
                data = resp.read()
            if data and len(data) > 0:
                with open(out_file, "wb") as f:
                    f.write(data)
                log(f"  Downloaded {description}", "green")
                return True
        except Exception as e:
            log(f"    fail: {str(e)[:60]}", "red")
    if os.path.exists(out_file):
        os.remove(out_file)
    log(f"  ERROR: Failed to download {description}", "red")
    return False


def fetch_json(url):
    """拉取 GitHub API JSON。"""
    req = urllib.request.Request(url, headers={"User-Agent": "build.py"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def read_manifest_version():
    with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("version"):
                return line.split("=", 1)[1].strip()
    return ""


def copy_tree(src, dst):
    if os.path.exists(src):
        if os.path.isdir(src):
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)


def extract_zip(zip_path, dest_dir):
    with zipfile.ZipFile(zip_path, "r") as z:
        z.extractall(dest_dir)


def extract_tar(tar_path, dest_dir):
    with tarfile.open(tar_path, "r:*") as t:
        t.extractall(dest_dir)


def get_daemon_candidates(target_version, arch):
    return [
        f"transmission-daemon-{target_version}-{arch}",
        f"transmission-daemon-{target_version}",
        "transmission-daemon",
    ]


def get_lib_candidates(target_version, arch):
    return [
        f"libminiupnpc.so.17-{target_version}-{arch}",
        f"libminiupnpc.so.17-{target_version}",
        "libminiupnpc.so.17",
    ]


def main():
    parser = argparse.ArgumentParser(description="Transmission for fnOS 统一打包脚本")
    parser.add_argument("--app-version", "-v", default="", help="应用版本号（默认读 manifest，覆盖输出文件名）")
    parser.add_argument("--transmission-version", "-t", default="", help="指定 transmission-daemon 版本")
    parser.add_argument("--arch", "-a", default="arm64", choices=["arm64", "amd64"], help="目标架构")
    parser.add_argument("--list-versions", action="store_true", help="列出可用的 transmission 版本")
    args = parser.parse_args()

    arch = args.arch
    manifest_version = read_manifest_version()
    if not manifest_version:
        log("ERROR: 无法读取 manifest 版本号", "red")
        sys.exit(1)

    app_version = args.app_version.strip() or manifest_version
    log(f"App version: {app_version}", "cyan")

    # 默认 transmission 版本 = 应用版本前 3 段
    parts = app_version.split(".")
    default_tr_ver = ".".join(parts[:3]) if len(parts) >= 3 else app_version

    if args.list_versions:
        log("Fetching available transmission versions...", "yellow")
        try:
            releases = fetch_json(TRANSMISSION_RELEASES_URL)
            log("", "cyan")
            log("Available transmission versions:", "cyan")
            for rel in releases[:10]:
                ver = rel.get("tag_name", "").lstrip("v")
                log(f"  - {ver}", "gray")
        except Exception as e:
            log(f"ERROR: {e}", "red")
        return

    log(f"Target architecture: {arch}", "cyan")
    log(f"Platform: {get_platform()}", "cyan")

    target_version = args.transmission_version.strip() or default_tr_ver
    log(f"Transmission version: {target_version}", "cyan")

    log("========================================", "cyan")
    log(f"  Transmission for fnOS - Local Build", "cyan")
    log(f"  Version: {app_version}  Arch: {arch}", "cyan")
    log("========================================", "cyan")
    log("", "cyan")

    # [1/6] 构建目录
    log("[1/6] Setting up build directory...", "yellow")
    for d in ["app/bin", "app/lib", "app/ui", "cmd", "config", "wizard"]:
        os.makedirs(os.path.join(BUILD_DIR, d), exist_ok=True)
    log("  Build directory ready", "green")

    # [2/6] 复制项目文件
    log("[2/6] Copying project files...", "yellow")
    for sub in ["cmd", "config", "wizard"]:
        src = os.path.join(PROJECT_DIR, sub)
        if os.path.isdir(src):
            copy_tree(src, os.path.join(BUILD_DIR, sub))
    shutil.copy2(MANIFEST_FILE, BUILD_DIR)
    for icon in ["ICON.PNG", "ICON_256.PNG"]:
        p = os.path.join(PROJECT_DIR, icon)
        if os.path.exists(p):
            shutil.copy2(p, BUILD_DIR)
    log("  Project files copied", "green")

    # [3/6] transmission-daemon
    log("[3/6] Preparing transmission-daemon...", "yellow")
    daemon_target = os.path.join(BUILD_DIR, "app", "bin", "transmission-daemon")
    daemon_done = False
    for name in get_daemon_candidates(target_version, arch):
        cache = os.path.join(BUILD_DIR, name)
        if os.path.exists(cache) and os.path.getsize(cache) > 0:
            shutil.copy2(cache, daemon_target)
            log(f"  Using cached binary: {name}", "green")
            daemon_done = True
            break
        url = f"{GITHUB_RELEASES_URL}/v{target_version}/{name}"
        log(f"  Trying {name}...", "gray")
        if download_proxy(url, cache, name):
            shutil.copy2(cache, daemon_target)
            daemon_done = True
            break
    if not daemon_done:
        log(f"  ERROR: Failed to download transmission-daemon for {arch} (release v{target_version})", "red")
        sys.exit(1)

    # [4/6] libminiupnpc
    log("[4/6] Preparing libminiupnpc...", "yellow")
    lib_target = os.path.join(BUILD_DIR, "app", "lib", "libminiupnpc.so.17")
    lib_done = False
    for name in get_lib_candidates(target_version, arch):
        cache = os.path.join(BUILD_DIR, name)
        if os.path.exists(cache) and os.path.getsize(cache) > 0:
            shutil.copy2(cache, lib_target)
            log(f"  Using cached: {name}", "green")
            lib_done = True
            break
        url = f"{GITHUB_RELEASES_URL}/v{target_version}/{name}"
        log(f"  Trying {name}...", "gray")
        if download_proxy(url, cache, name):
            shutil.copy2(cache, lib_target)
            lib_done = True
            break
    if not lib_done:
        log(f"  Warning: libminiupnpc.so.17 not available for {arch} in release v{target_version}", "yellow")

    # [5/6] WebUI
    log("[5/6] Preparing WebUI...", "yellow")
    webui_version = ""
    try:
        rel = fetch_json(WEBUI_API_URL)
        webui_version = rel.get("tag_name", "").lstrip("v")
        log(f"  Latest WebUI version: v{webui_version}", "gray")
    except Exception:
        log("  Warning: Failed to fetch WebUI version, using cached/default", "yellow")
        webui_version = "0.0.9"

    webui_file = f"transmission-web-v{webui_version}.zip"
    webui_cache = os.path.join(BUILD_DIR, webui_file)
    ui_target = os.path.join(BUILD_DIR, "app", "ui")
    if os.path.exists(webui_cache) and os.path.getsize(webui_cache) > 0:
        log("  Using cached WebUI", "green")
    else:
        log("  Downloading WebUI...", "yellow")
        url = f"{WEBUI_BASE}/v{webui_version}/{webui_file}"
        if not download_proxy(url, webui_cache, webui_file):
            log("  ERROR: Failed to download WebUI", "red")
            sys.exit(1)

    log("  Extracting WebUI...", "gray")
    if webui_file.endswith(".zip"):
        extract_zip(webui_cache, ui_target)
    else:
        extract_tar(webui_cache, ui_target)

    # transmission-web zip 通常解压出一个 transmission/ 目录，将其内容上移
    trans_dir = os.path.join(ui_target, "transmission")
    if os.path.isdir(trans_dir):
        for item in os.listdir(trans_dir):
            src = os.path.join(trans_dir, item)
            shutil.move(src, ui_target)
        shutil.rmtree(trans_dir, ignore_errors=True)

    # 注入更新检查
    log("  Injecting update check...", "gray")
    index_html = os.path.join(ui_target, "index.html")
    if os.path.exists(index_html):
        with open(index_html, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        inject = (
            f"    <script>\n"
            f"        window.TRANSMISSION_APP_VERSION = '{app_version}';\n"
            f"    </script>\n"
            f"    <script src=\"update-check.js\"></script>\n"
        )
        if "</body>" in content:
            content = content.replace("</body>", inject + "</body>", 1)
            with open(index_html, "w", encoding="utf-8") as f:
                f.write(content)
            log(f"  Update check injected (v{app_version})", "green")
        else:
            log("  Warning: Could not find </body> tag", "yellow")
    else:
        log(f"  Warning: index.html not found at {index_html}", "yellow")

    # 复制附加 UI 文件
    for sub in ["config", "images", "update-check.js"]:
        p = os.path.join(PROJECT_DIR, "app", "ui", sub)
        if os.path.exists(p):
            copy_tree(p, os.path.join(ui_target, sub))
    # 复制 gateway-proxy.py
    proxy_src = os.path.join(PROJECT_DIR, "app", "bin", "gateway-proxy.py")
    if os.path.exists(proxy_src):
        shutil.copy2(proxy_src, os.path.join(BUILD_DIR, "app", "bin", "gateway-proxy.py"))
    log("  WebUI ready", "green")

    # [6/6] 构建 fpk
    log("[6/6] Building package...", "yellow")
    fnpack_url = get_fnpack_url(arch)
    fnpack_name = fnpack_url.rsplit("/", 1)[-1]
    fnpack_path = os.path.join(BUILD_DIR, fnpack_name)
    if os.path.exists(fnpack_path) and os.path.getsize(fnpack_path) > 0:
        log("  Using cached fnpack", "green")
    else:
        log("  Downloading fnpack...", "yellow")
        if not download_proxy(fnpack_url, fnpack_path, "fnpack"):
            sys.exit(1)
    if get_platform() != "windows":
        os.chmod(fnpack_path, 0o755)

    fpk_out = os.path.join(BUILD_DIR, "transmission.fpk")
    if os.path.exists(fpk_out):
        os.remove(fpk_out)

    log("  Running fnpack build...", "gray")
    old_cwd = os.getcwd()
    os.chdir(BUILD_DIR)
    try:
        if get_platform() == "windows":
            proc = subprocess.run([fnpack_path, "build", "."], capture_output=True)
        else:
            proc = subprocess.run(["./" + fnpack_name, "build", "."], capture_output=True)
    finally:
        os.chdir(old_cwd)

    if not os.path.exists(fpk_out):
        log("  ERROR: Build failed", "red")
        if proc.stderr:
            log("  " + proc.stderr.decode("utf-8", "replace")[:2000], "red")
        if proc.stdout:
            log("  " + proc.stdout.decode("utf-8", "replace")[:2000], "red")
        sys.exit(1)

    final_name = f"transmission-{app_version}-{arch}.fpk"
    shutil.move(fpk_out, os.path.join(PROJECT_DIR, final_name))
    log("  Build successful!", "green")

    log("", "cyan")
    log("========================================", "green")
    log("  Build Complete!", "green")
    log(f"  Output: {final_name}", "green")
    log("========================================", "green")


if __name__ == "__main__":
    main()
