# Transmission for fnOS 🚀

[![Transmission Version](https://img.shields.io/badge/Transmission-4.1.3-blue?style=flat-square)](https://github.com/transmission/transmission/releases)
[![WebUI](https://img.shields.io/badge/WebUI-Go%2BReact-green?style=flat-square)](https://github.com/sushazhi/SeedArk)
[![Platform](https://img.shields.io/badge/Platform-fnOS-green?style=flat-square)](https://www.fnnas.com/)
[![License](https://img.shields.io/badge/License-MIT-blue?style=flat-square)](LICENSE)

> 📌 **注意**：本应用支持 **ARM64 (aarch64)** 和 **amd64 (x86_64)** 架构，系统要求 **fnOS v1.2.0401 及以上**。

---

## ✨ 特色功能

- 🎯 **轻量级** - 资源占用低，运行高效
- 📡 **完整协议** - 支持磁力链接、种子文件、DHT/PEX/LSD
- ⚡ **速度控制** - 灵活的速度限制和队列管理
- 🌐 **WebUI** - 内置Web界面，随时随地管理
- 📁 **下载目录选择** - 应用页面内可直接选择/打开下载目录（fnOS 文件选择器）
- 🔐 **网关免密** - 接入 fnOS 统一网关，登录系统后即可直接打开，无需设置账号密码
- 🔒 **RPC 认证免密** - 即使开启 RPC 认证，经统一网关访问时由代理自动注入凭证，无需再次登录
- 💾 **数据持久化** - 配置和下载数据保存在独立存储空间
- 🔄 **平滑升级** - 升级时自动备份和恢复数据（含种子数据）

---

## 📦 安装与更新

### 手动安装/更新

1. 打开 **应用中心**
2. 点击左下角 **手动安装**
3. 选择安装包

---

## 🔨 本地构建

统一使用跨平台 Python 构建脚本 `build.py`，**在 Windows / Linux / macOS 上命令完全一致**，仅需安装 Python 3.8+（项目本身即依赖 Python，无额外负担）。

### 环境要求

| 组件 | 要求 |
|------|------|
| Python | 3.8+（Windows / Linux / macOS 通用） |
| transmission-daemon | musl 全静态编译产物（无需动态库），构建时自动从 [GitHub Releases](https://github.com/sushazhi/fnos-transmission/releases) 获取 `transmission-daemon-musl-<版本>-<架构>` |
| SeedArk | 默认从本地 `../SeedArk` 源码构建（需 Go + pnpm 11+）；源码不存在时回退为从 [SeedArk Releases](https://github.com/sushazhi/SeedArk/releases) 下载对应架构的 WebUI 管理面板（Go+React 单二进制，原名 trpanel） |

### 一键构建

```bash
# 进入项目目录
cd fnos-transmission

# 运行构建（默认版本，默认架构 arm64）
python build.py

# 指定应用版本
python build.py --app-version 4.1.3.2.32

# 指定架构构建（amd64）
python build.py --arch amd64

# 指定 transmission-daemon 版本
python build.py --transmission-version 4.1.3

# 默认从本地 ../SeedArk 源码构建 WebUI（检测到源码目录即生效，需 Go + pnpm 11+）
python build.py

# 指定其他 SeedArk 源码目录
python build.py --seedark-src ../SeedArk

# 本地源码构建，但跳过前端 pnpm 构建（复用 frontend/dist 已有产物）
python build.py --skip-frontend

# 强制从 SeedArk 最新 release 下载 WebUI（跳过本地源码）
python build.py --seedark-release

# 直接使用预编译的 seedark 二进制
python build.py --webui-binary ./seedark-linux-arm64

# 列出可用的 transmission 版本
python build.py --list-versions
```

**参数说明**：

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--app-version, -v` | 应用版本号（覆盖 manifest） | 读取 manifest |
| `--transmission-version, -t` | 指定 transmission-daemon 版本 | 应用版本前 3 段 |
| `--arch, -a` | 目标架构 `arm64` / `amd64` | `arm64` |
| `--seedark-src` | 指定本地 SeedArk 源码目录构建 WebUI（需 Go + pnpm 11+），优先级最高 | 自动检测 `../SeedArk` |
| `--skip-frontend` | 配合本地源码构建：跳过前端 pnpm 构建，复用已有 `frontend/dist` 或 `backend/web/dist` | — |
| `--webui-binary` | 直接使用指定路径的 linux `seedark` 二进制，跳过 SeedArk 下载 | — |
| `--seedark-release` | 强制从 SeedArk 最新 release 下载 WebUI，跳过本地源码检测 | — |
| `--list-versions` | 列出可用的 transmission 版本 | — |

**构建特性**：
- **跨平台**：一份脚本在 Windows / Linux / macOS 通用，自动检测平台并选择对应的官方 `fnpack` 构建工具
- **WebUI 内嵌**：多种来源，按优先级 `--seedark-src` > `--webui-binary` > 本地 `../SeedArk` 自动检测 > release 下载
  - **本地源码构建**（默认，检测到 `../SeedArk`）：在源码目录内执行 `pnpm install --frozen-lockfile` → `pnpm build` → 产物复制到 `backend/web/dist`，再 `CGO_ENABLED=0 GOOS=linux GOARCH=<arch> go build -trimpath ./cmd/server` 交叉编译，与 SeedArk 官方 Dockerfile 流程一致；需 Go 与 pnpm 11+
  - **release 下载**（无本地源码时回退，或 `--seedark-release` 强制）：从 [SeedArk](https://github.com/sushazhi/SeedArk) 最新 release 下载对应架构的 `seedark` 单二进制（Go + React 内嵌前端），以原名放入 `app/bin/`，无需本地 Go/Node 工具链
  - **预编译二进制**（`--webui-binary <file>`）：直接指定已编译好的 linux `seedark`
- **daemon 下载**：自动从 GitHub Releases 获取 musl 静态 `transmission-daemon`（候选资产 `transmission-daemon-musl-<版本>-<架构>` → `transmission-daemon-musl-<架构>` 多级回退），产物缓存在 `.local-build/` 供重复构建复用
- 构建产物输出到项目根目录：`transmission-<版本>-<架构>.fpk`

### CI 构建

GitHub Actions（`.github/workflows/build-and-release.yml`）自动为 **arm64** / **amd64** 双架构构建并发布：

- **musl 静态编译** transmission-daemon（Alpine 容器内全静态编译），产物上传至 `v<版本>` release；同名资产已存在时直接复用，手动触发时可勾选 `force_rebuild` 强制重编
- **fpk 打包**：下载 SeedArk 最新 release → 组装应用结构 → `fnpack` 打包 → 上传 artifacts；打 `v*` tag 时自动发布 release（含 fpk）
- 触发方式：推送 `v*` tag、手动触发（workflow_dispatch）
- 产物位置：[Releases](https://github.com/sushazhi/fnos-transmission/releases)、CI 运行页面 artifacts

### 月末自动跟进上游

`.github/workflows/check-upstream.yml` 每月**最后一天**（UTC 03:23 = 北京时间 11:23）检查
[transmission/transmission](https://github.com/transmission/transmission) 有没有新版本：

| 上游情况 | 动作 |
|----------|------|
| **有新版本** | 改 `manifest`（`version` = 上游版本 + 修订号 `0`，并追加 `changelog`）与 README 版本标注 → 提交 `main` → 打 tag `v<版本>` → 派发 `build-and-release.yml` 构建并发布 |
| **无新版本** | 不改任何文件、不提交、不打 tag、不构建，直接跳过 |

版本号规则：`上游版本.适配层修订号`。上游出 `4.1.4` 时自动变为 `4.1.4.0`；上游未变但要重打时（手动勾选 `force`）修订号 +1，如 `4.1.3.5`。

- **为什么「月末」用 `28-31` + 运行时判定**：GitHub Actions 的 cron 来自 POSIX cron 实现，`L`（月末）这类扩展没有被官方文档列为受支持字段，最坏情况是静默不触发。因此用确定受支持的 `28-31` 窗口，再在 job 里判一次「明天是不是 1 号」——等价于「今天是本月最后一天」，28/29/30/31 四种月份长度全覆盖。
- **为什么是独立 workflow**：GitHub 规定「用内置 `GITHUB_TOKEN` 推送 tag 不会触发其它 workflow」（防递归）。所以「定时检查 → push tag → 由 tag 触发构建」走不通，必须显式 `gh workflow run` 派发；只有 `workflow_dispatch` / `repository_dispatch` 被排除在该规则之外。
- **幂等/自愈**：提交后 manifest 版本已等于目标值，下次检查判定「无更新」直接跳过，不会重复发版。「无更新」分支不是简单退出，而是按 `manifest` 当前版本核对 tag 与 Release，缺什么补什么：①提交成功但 **tag 推送失败** → 下次补 tag；②「提交成功但派发失败」，或「Release 建了但 `.fpk` 上传失败」（`build-and-release.yml` 里上传失败不会让 job 变红）→ 下次核对 `v<版本>` 的 Release 是否**真的带齐 arm64/amd64 两个 `.fpk`**，缺则补一次派发。tag 推送与提交一样带 3 次重试。
- **人工指定版本会被校验**：`--apply --upstream-version 4.1.4` 会先确认该版本确实存在于上游 tag，不存在则直接报错——避免把一个**永远构建不出来**的版本号提交进 `main`（那会让构建拉源码 404，而 `main` 上的版本号不会再被自动纠正）。
- 行尾：`.gitattributes` 对 `manifest`、`README.md`、`cmd/*` 强制 LF。CI 用 `grep`/`cut` 直接解析 `manifest` 取版本号，CRLF 会让 `\r` 混进版本号与包名。
- 检查逻辑在 [`tools/check_upstream.py`](tools/check_upstream.py)，可本地复现：`python3 tools/check_upstream.py --detect`（只检查不改动）、`--apply`、`--apply --force`、`--apply --upstream-version 4.1.4`。
- **注意**：GitHub 会在仓库连续 60 天无提交后自动停用定时 workflow（并给仓库所有者发邮件）。本 workflow 有更新时会提交，所以只要上游还在发版就不会被停；若上游长期无新版而收到停用通知，到 Actions 页面点一次 **Enable workflow** 即可。定时任务只在默认分支上生效，改动需先合入 `main`。

---

### 构建产物

| 文件 | 说明 |
|------|------|
| `transmission-<版本>-<架构>.fpk` | fnOS 安装包（如 `transmission-4.1.3.2-arm64.fpk`） |
| `.local-build/` | 构建缓存目录（daemon / fnpack，可删除） |

---

## 💻 系统要求

| 项目 | 默认值 |
|------|--------|
| 访问地址 | fnOS 桌面图标（统一网关 `/app/transmission`） |
| WebUI 服务 | SeedArk 直连 fnOS 统一网关（`transmission.sock`） |
| RPC 端口 | 9090 (可在应用设置中修改) |
| 架构 | ARM64 (aarch64) / amd64 (x86_64) |

> 📌 **端口修改**：安装或应用设置中可自定义 RPC 端口

### 存储权限

- **读取/写入**：`transmission` 共享存储

---

## 🔧 端口配置

本应用采用 fnOS **统一网关**访问（桌面图标或固定网关地址 `/app/transmission`），默认情况下无需修改端口。Web 界面由 `seedark`（SeedArk 管理面板）提供（直接监听 fnOS 统一网关 Unix socket，不对外暴露 TCP 端口），界面通过 RPC 连接本机 `transmission-daemon`。

| 服务 | 地址 | 说明 |
|------|------|------|
| Web 界面 | `/app/transmission`（网关） | SeedArk（Go + React 单二进制，直连网关 socket） |
| Transmission RPC | 127.0.0.1:9090 | 可在**应用设置**中修改，管理界面自动跟随 |

> 📌 **说明**：通过统一网关访问始终使用固定地址；应用设置中的端口对应 Transmission RPC 服务端口。

---

## 📁 项目结构

```
fnos-transmission/
├── app/                    # fnOS应用资源
│   ├── bin/                # 构建产生的可执行文件
│   │   ├── transmission-daemon  # Transmission守护进程（musl 全静态编译，无动态库依赖）
│   │   └── seedark # WebUI 后端（SeedArk，原名 trpanel；Go+React 单二进制，内嵌前端，直连 fnOS 统一网关）
│   └── ui/                  # 桌面图标与应用入口配置（前端已内嵌于 seedark）
│       ├── config          # 桌面应用配置
│       └── images/         # 应用图标
│           ├── icon_64.png # 64x64图标
│           └── icon_256.png # 256x256图标
├── cmd/                    # fnOS 生命周期脚本
│   ├── config_callback     # 配置后置
│   ├── config_init         # 配置初始化
│   ├── install_init        # 安装前初始化
│   ├── install_callback    # 安装后回调
│   ├── main               # 主服务控制脚本
│   ├── uninstall_init      # 卸载前清理
│   ├── uninstall_callback  # 卸载后清理
│   ├── upgrade_init        # 升级前备份
│   └── upgrade_callback    # 升级后恢复
├── config/                 # 配置文件
│   ├── privilege           # 权限配置（端口、挂载点）
│   └── resource            # 资源映射配置
├── wizard/                 # 向导UI定义
│   ├── config              # 配置向导
│   ├── install             # 安装向导
│   ├── upgrade             # 升级向导
│   └── uninstall           # 卸载向导
├── tools/
│   └── check_upstream.py   # 月末检查上游版本并改写 manifest/README（供 CI 调用，可本地复现）
├── .github/workflows/
│   ├── build-and-release.yml  # 双架构构建 + 发布（tag / 手动触发）
│   └── check-upstream.yml     # 每月最后一天检查上游，有更新则改版本并派发构建
├── build.py                # 跨平台构建脚本（Windows/Linux/macOS）
├── LICENSE                 # 项目许可证
└── manifest                # 应用元数据
```

---

## 🔄 升级数据保护

升级时会自动备份和恢复数据到 `shares` 目录，确保配置和下载任务不丢失：

- **备份触发**：只要数据目录存在即备份（含空目录结构），备份前强制停止 daemon 确保 `torrents/resume` 完整落盘
- **单一备份**：备份目录固定为 `shares/.data_backup`，升级时仅保留最新一份（重建前清理旧备份），不按日期归档
- **恢复回退**：优先从备份信息文件定位备份目录；备份为空或缺失时不执行恢复，保留现有数据
- **失败容忍**：备份完整性校验失败时不终止升级（警告并保留备份），避免升级中断卡死

---

## 📚 开源项目

| 项目 | 版本 | 用途 | 许可证 |
|------|------|------|--------|
| [Transmission](https://github.com/transmission/transmission) | 4.1.3 | BitTorrent 客户端核心 | [GPL-2.0](https://www.gnu.org/licenses/gpl-2.0.html) |
| [SeedArk](https://github.com/sushazhi/SeedArk) | latest | WebUI 管理面板（Go + React 单二进制，内嵌前端，原名 trpanel） | MIT |

> 📌 **许可证说明**：本应用自身代码（生命周期脚本、构建工具、配置）以 [MIT](LICENSE) 许可证发布；包内聚合分发了 **Transmission（GPL-2.0）** 的 `transmission-daemon` 二进制与 **SeedArk（MIT，原名 trpanel）** 的 WebUI。Transmission 对应源代码与构建脚本的获取方式见 [LICENSE](LICENSE) 中的「Source code offer」。

---

## 🤝 支持与反馈

- [报告问题](https://github.com/sushazhi/fnos-transmission/issues) - GitHub Issues
- [飞牛论坛](https://club.fnnas.com/) - 社区讨论
- [fnOS 文档](https://docs.fnnas.com/) - 官方文档

---

## 🧭 开发者文档

- [应用错误异常展示处理](docs/ERROR_HANDLING.md) - fnOS 生命周期脚本的错误处理与日志约定

---

## 📝 更新日志

### v4.1.3.3
- ✨ 新增 MCP 独立直连端口（默认 9094），AI 客户端可绕过统一网关直连 `/mcp`
- 🔧 transmission-daemon 改为 Alpine musl 全静态编译（static-pie，无 glibc 等动态库依赖），CI 自动双架构编译并复用已发布产物
- ✨ 管理面板升级为 [SeedArk](https://github.com/sushazhi/SeedArk)（Go+React 单二进制，原名 trpanel），构建脚本改为从 SeedArk 最新 release 自动下载打包
- ✨ 新增打开/选择下载目录（fnOS文件选择器）

### v4.1.1
- ✨ 升级至 Transmission 4.1.1

---

感谢 [Transmission](https://github.com/transmission/transmission) 和 [SeedArk](https://github.com/sushazhi/SeedArk)（原名 trpanel）开源项目的支持。
