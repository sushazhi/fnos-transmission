#!/usr/bin/env python3
"""
build.py - Transmission for fnOS 统一打包脚本（跨平台，替代 build.ps1）

用法:
    python build.py [--app-version 4.1.3.2.1] [--transmission-version 4.1.3] [--arch arm64|amd64]
    python build.py --trpanel-src ../trpanel            # 从本地 trpanel 源码构建 WebUI
    python build.py --trpanel-src ../trpanel --skip-frontend   # 复用已构建的前端产物
    python build.py --list-versions

特性:
    - 自动检测操作系统 (Windows/Linux)，选择对应的 fnpack 构建工具
    - 参数与 build.ps1 兼容
    - WebUI (trpanel) 默认从 sushazhi/trpanel 最新 release 下载，无需本地 Go/Node 工具链
    - 也可用 --trpanel-src 从本地源码构建（需 Go + pnpm 11+），或 --webui-binary 指定预编译二进制
"""
import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import urllib.request

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
BUILD_DIR = os.path.join(PROJECT_DIR, ".local-build")
MANIFEST_FILE = os.path.join(PROJECT_DIR, "manifest")

FNPACK_BASE = "https://static2.fnnas.com/fnpack/fnpack-1.2.3"
TRANSMISSION_RELEASES_URL = "https://api.github.com/repos/transmission/transmission/releases"
GITHUB_RELEASES_URL = "https://github.com/sushazhi/fnos-transmission/releases/download"

# trpanel（Transmission 管理面板，Go+React 单二进制）发布仓库
TRPANEL_RELEASES_URL = "https://api.github.com/repos/sushazhi/trpanel/releases/latest"

# 下载代理
MAIN_PROXY = "https://gh-proxy.com/"
BINARY_PROXY = "https://ghfast.top/"


_ANSI_COLORS = {"cyan": "96", "green": "92", "yellow": "93", "red": "91", "gray": "90"}

def log(msg, color="cyan"):
    # TTY 下输出 ANSI 颜色，重定向/管道下输出纯文本
    code = _ANSI_COLORS.get(color, "")
    if code and sys.stdout.isatty():
        sys.stdout.write(f"\033[{code}m{msg}\033[0m\n")
    else:
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


def get_fnpack_url():
    """根据开发机平台返回 fnpack 下载地址，覆盖 Windows/Linux/macOS。

    注意：构建工具 fnpack 必须用【当前开发机】的平台，而非目标应用平台，
    因此这里用 get_platform() + get_platform_arch() 自动检测开发机。
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


def download_trpanel(arch, out_path):
    """从 sushazhi/trpanel 最新 release 下载对应架构的 tar.gz 并解压出 trpanel 二进制。

    产物命名：trpanel-v<ver>-linux-<arch>.tar.gz，解压后为单个可执行文件 trpanel。
    返回 (ok, error_message)。
    """
    try:
        rel = fetch_json(TRPANEL_RELEASES_URL)
    except Exception as e:
        return False, f"获取 trpanel 最新 release 失败: {e}"
    tag = rel.get("tag_name", "").lstrip("v")
    if not tag:
        return False, "trpanel release 缺少 tag_name"
    asset_name = f"trpanel-v{tag}-linux-{arch}.tar.gz"
    asset_url = None
    for a in rel.get("assets", []):
        if a.get("name") == asset_name:
            asset_url = a.get("browser_download_url")
            break
    if not asset_url:
        names = [a.get("name") for a in rel.get("assets", [])]
        return False, f"trpanel release v{tag} 中未找到 {asset_name}（可用: {names}）"

    tarball = os.path.join(BUILD_DIR, asset_name)
    if os.path.exists(tarball) and os.path.getsize(tarball) > 0:
        log(f"  Using cached tarball: {asset_name}", "green")
    else:
        log(f"  Downloading trpanel v{tag} ({asset_name})...", "gray")
        if not download_proxy(asset_url, tarball, asset_name):
            return False, f"下载 {asset_name} 失败"

    # 解压 tar.gz，取出 trpanel 二进制
    extract_dir = os.path.join(BUILD_DIR, f"trpanel-extract-{arch}")
    shutil.rmtree(extract_dir, ignore_errors=True)
    os.makedirs(extract_dir, exist_ok=True)
    try:
        import tarfile
        with tarfile.open(tarball, "r:gz") as tf:
            # Python 3.14+ 默认过滤 tar 归档，显式指定 data 过滤器以兼容旧版本
            try:
                tf.extractall(extract_dir, filter="data")
            except TypeError:
                tf.extractall(extract_dir)
    except Exception as e:
        return False, f"解压 {asset_name} 失败: {e}"

    # 在解压目录中定位 trpanel 可执行文件
    found = None
    for root, _dirs, files in os.walk(extract_dir):
        for f in files:
            if f == "trpanel":
                found = os.path.join(root, f)
                break
        if found:
            break
    if not found or not os.path.isfile(found) or os.path.getsize(found) == 0:
        return False, f"解压后未找到 trpanel 可执行文件（{asset_name}）"
    shutil.copy2(found, out_path)
    log(f"  trpanel v{tag} extracted to {os.path.basename(out_path)}", "green")
    return True, ""


def _run_cmd(cmd, cwd=None, env=None):
    """运行子进程命令。Windows 下 pnpm 等是 .cmd 包装脚本，需经 shell 才能执行。"""
    if os.name == "nt" and str(cmd[0]).lower().endswith((".cmd", ".bat")):
        return subprocess.run(subprocess.list2cmdline(cmd), shell=True, cwd=cwd, env=env, capture_output=True)
    return subprocess.run(cmd, cwd=cwd, env=env, capture_output=True)


def _tail(proc, n=500):
    """截取子进程输出的末尾，便于在报错时展示关键日志。"""
    out = (proc.stdout or b"") + (proc.stderr or b"")
    return out.decode("utf-8", "replace")[-n:]


def build_trpanel_from_src(src_dir, arch, out_path, skip_frontend=False):
    """从本地 trpanel 源码目录构建 linux trpanel 二进制。

    流程与 trpanel 官方 Dockerfile 一致：
      1) frontend: pnpm install --frozen-lockfile && pnpm build  -> frontend/dist
      2) 复制 frontend/dist -> backend/web/dist（Go 侧通过 //go:embed web/dist 内嵌）
      3) backend: CGO_ENABLED=0 GOOS=linux GOARCH=<arch> go build -trimpath ./cmd/server

    skip_frontend=True 时跳过第 1 步，复用 frontend/dist（优先）或 backend/web/dist 现有产物。
    返回 (ok, error_message)。
    """
    backend_dir = os.path.join(src_dir, "backend")
    frontend_dir = os.path.join(src_dir, "frontend")
    web_dist = os.path.join(backend_dir, "web", "dist")

    if not os.path.isfile(os.path.join(backend_dir, "cmd", "server", "main.go")):
        return False, f"在 {src_dir} 中未找到 backend/cmd/server/main.go（不是有效的 trpanel 源码目录）"

    # ---- 前端（可选跳过，复用已构建产物）----
    if skip_frontend:
        src_dist = os.path.join(frontend_dir, "dist")
        if os.path.isdir(src_dist) and os.listdir(src_dist):
            shutil.rmtree(web_dist, ignore_errors=True)
            shutil.copytree(src_dist, web_dist)
            log("  Using existing frontend/dist (skipped pnpm build)", "green")
        elif os.path.isdir(web_dist) and os.listdir(web_dist):
            log("  Using existing backend/web/dist (skipped pnpm build)", "green")
        else:
            return False, "--skip-frontend 但未找到前端产物（frontend/dist 与 backend/web/dist 均为空或不存在）"
    else:
        pnpm_bin = shutil.which("pnpm")
        if not pnpm_bin:
            return False, "未找到 pnpm（trpanel 前端需 pnpm 11+；也可用 --skip-frontend 复用已有产物）"
        env = dict(os.environ)
        env.setdefault("CI", "true")
        log("  Installing frontend deps (pnpm install --frozen-lockfile)...", "gray")
        proc = _run_cmd([pnpm_bin, "install", "--frozen-lockfile"], cwd=frontend_dir, env=env)
        if proc.returncode != 0:
            log("  --frozen-lockfile 失败，回退 pnpm install...", "gray")
            proc = _run_cmd([pnpm_bin, "install"], cwd=frontend_dir, env=env)
            if proc.returncode != 0:
                return False, "pnpm install 失败: " + _tail(proc)
        log("  Building frontend (pnpm build)...", "gray")
        proc = _run_cmd([pnpm_bin, "build"], cwd=frontend_dir, env=env)
        if proc.returncode != 0:
            return False, "pnpm build 失败: " + _tail(proc)
        src_dist = os.path.join(frontend_dir, "dist")
        if not (os.path.isdir(src_dist) and os.listdir(src_dist)):
            return False, f"前端构建未产出产物: {src_dist}"
        shutil.rmtree(web_dist, ignore_errors=True)
        shutil.copytree(src_dist, web_dist)
        log("  Frontend built into backend/web/dist", "green")

    # ---- 后端（Go 交叉编译，静态链接）----
    go_bin = shutil.which("go")
    if not go_bin:
        return False, "未找到 go 工具链"
    env = dict(os.environ)
    env["GOOS"] = "linux"
    env["GOARCH"] = arch
    env["CGO_ENABLED"] = "0"
    log(f"  Cross-compiling trpanel (linux/{arch})...", "gray")
    proc = _run_cmd(
        [go_bin, "build", "-trimpath", "-ldflags", "-s -w", "-o", out_path, "./cmd/server"],
        cwd=backend_dir, env=env,
    )
    if not os.path.exists(out_path) or os.path.getsize(out_path) == 0:
        return False, "Go 编译失败: " + _tail(proc)
    return True, ""


def main():
    parser = argparse.ArgumentParser(description="Transmission for fnOS 统一打包脚本")
    parser.add_argument("--app-version", "-v", default="", help="应用版本号（默认读 manifest，覆盖输出文件名）")
    parser.add_argument("--transmission-version", "-t", default="", help="指定 transmission-daemon 版本")
    parser.add_argument("--arch", "-a", default="arm64", choices=["arm64", "amd64"], help="目标架构")
    parser.add_argument("--trpanel-src", default="", help="从本地 trpanel 源码目录构建 WebUI（需 Go + pnpm 11+），优先级高于 --webui-binary 与 release 下载")
    parser.add_argument("--skip-frontend", action="store_true", help="配合 --trpanel-src：跳过前端 pnpm 构建，复用已有 frontend/dist 或 backend/web/dist")
    parser.add_argument("--webui-binary", default="", help="直接使用指定路径的 linux trpanel 二进制，跳过 trpanel 下载")
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
    # 清空旧 app 目录，避免切换 ui/web -> ui 后残留旧 ui/web 子目录
    shutil.rmtree(os.path.join(BUILD_DIR, "app"), ignore_errors=True)
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

    # [5/6] WebUI（trpanel 单二进制，Go+React 内嵌前端，从 sushazhi/trpanel 最新 release 下载）
    log("[5/6] Preparing WebUI (trpanel)...", "yellow")
    manager_target = os.path.join(BUILD_DIR, "app", "bin", "trpanel")
    os.makedirs(os.path.dirname(manager_target), exist_ok=True)

    if args.trpanel_src:
        # 从本地源码构建（Go 交叉编译 + 可选 pnpm 前端构建）
        ok, err = build_trpanel_from_src(args.trpanel_src, arch, manager_target, args.skip_frontend)
        if not ok:
            log(f"  ERROR: 从本地源码构建 trpanel 失败: {err}", "red")
            sys.exit(1)
        log(f"  Built trpanel from source: {args.trpanel_src}", "green")
    elif args.webui_binary:
        # 直接使用预编译二进制
        if not os.path.isfile(args.webui_binary) or os.path.getsize(args.webui_binary) == 0:
            log(f"  ERROR: 指定二进制不存在或为空: {args.webui_binary}", "red")
            sys.exit(1)
        shutil.copy2(args.webui_binary, manager_target)
        log(f"  Using provided binary: {args.webui_binary}", "green")
    else:
        # 从 trpanel 最新 release 下载对应架构二进制，解压出的 trpanel 直接以原名落入 app/bin/
        ok, err = download_trpanel(arch, manager_target)
        if not ok:
            log(f"  ERROR: 获取 trpanel 失败: {err}", "red")
            sys.exit(1)
    if os.name != "nt":
        os.chmod(manager_target, 0o755)

    # 复制附加 UI 文件（桌面图标与 config）
    ui_target = os.path.join(BUILD_DIR, "app", "ui")
    for sub in ["config", "images"]:
        p = os.path.join(PROJECT_DIR, "app", "ui", sub)
        if os.path.exists(p):
            copy_tree(p, os.path.join(ui_target, sub))
    log("  WebUI ready", "green")

    # [6/6] 构建 fpk
    log("[6/6] Building package...", "yellow")
    fnpack_url = get_fnpack_url()
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
