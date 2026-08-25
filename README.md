# Transmission for fnOS 🚀

🌐 **语言/Language**
- [简体中文](README.md) | [English](README_EN.md)

[![Transmission Version](https://img.shields.io/badge/Transmission-4.1.3-blue?style=flat-square)](https://github.com/transmission/transmission/releases)
[![WebUI Version](https://img.shields.io/badge/WebUI-0.1.0-green?style=flat-square)](https://github.com/jianxcao/transmission-web/releases)
[![Platform](https://img.shields.io/badge/Platform-fnOS-green?style=flat-square)](https://www.fnnas.com/)
[![License](https://img.shields.io/badge/License-GPL--2.0-blue?style=flat-square)](https://www.gnu.org/licenses/gpl-2.0.html)

> 📌 **注意**：本应用支持 **ARM64 (aarch64)** 和 **amd64 (x86_64)** 架构，系统要求 **fnOS v1.1.19 及以上**。

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
| transmission-daemon | 构建时自动从 [GitHub Releases](https://github.com/sushazhi/fnos-transmission/releases) 获取对应架构的编译产物 |

### 一键构建

```bash
# 进入项目目录
cd fnos-transmission

# 运行构建（默认版本，默认架构 arm64）
python build.py

# 指定应用版本
python build.py --app-version 4.1.3.2.8

# 指定架构构建（amd64）
python build.py --arch amd64

# 指定 transmission-daemon 版本
python build.py --transmission-version 4.1.3

# 列出可用的 transmission 版本
python build.py --list-versions
```

**参数说明**：

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--app-version, -v` | 应用版本号（覆盖 manifest） | 读取 manifest |
| `--transmission-version, -t` | 指定 transmission-daemon 版本 | 应用版本前 3 段 |
| `--arch, -a` | 目标架构 `arm64` / `amd64` | `arm64` |
| `--list-versions` | 列出可用的 transmission 版本 | — |

**构建特性**：
- **跨平台**：一份脚本在 Windows / Linux / macOS 通用，自动检测平台并选择对应的官方 `fnpack` 构建工具
- **零外部依赖**：下载用内置 `urllib`，解压用内置 `zipfile` / `tarfile`，无需安装 `curl` / `unzip` / `tar`
- 自动从 GitHub Releases 获取 `transmission-daemon` 与 `libminiupnpc.so.17`（含架构后缀 / 版本后缀 / 裸文件名多级回退）
- 自动获取最新 `transmission-web` WebUI 并注入更新检测脚本
- 构建产物输出到项目根目录：`transmission-<版本>-<架构>.fpk`

### CI 构建

GitHub Actions 会自动为 **arm64** 和 **amd64** 两种架构构建，产物发布在：
- [Releases](https://github.com/sushazhi/fnos-transmission/releases)
- CI 运行页面下载 artifacts

---

### 构建产物

| 文件 | 说明 |
|------|------|
| `transmission-4.1.3.2.8-arm64.fpk` | fnOS 安装包（ARM64） |
| `transmission-4.1.3.2.8-amd64.fpk` | fnOS 安装包（amd64） |
| `.local-build/` | 构建缓存目录（可删除） |

---

## 💻 系统要求

| 项目 | 默认值 |
|------|--------|
| 访问地址 | `http://<NAS_IP>:9090/transmission/` |
| 默认端口 | 9090 (可在应用设置中修改) |
| 架构 | ARM64 (aarch64) / amd64 (x86_64) |

> 📌 **端口修改**：安装或应用设置中可自定义端口

### 存储权限

- **读取/写入**：`transmission` 共享存储

---

## 🔧 端口配置

本应用采用 fnOS **统一网关**访问（桌面图标或固定网关地址），默认情况下无需修改端口。如需要，可在**应用设置**中修改 WebUI/RPC 端口：

| 方式 | 说明 |
|------|------|
| **应用设置** | 在"应用设置"中修改 WebUI/RPC 端口，保存后自动重启应用 |

> 📌 **说明**：通过统一网关访问仍使用固定地址，此端口为本机内部 RPC 服务及直连访问使用。

---

## 📁 项目结构

```
fnos-transmission/
├── app/                    # fnOS应用资源
│   ├── bin/                # 构建产生的可执行文件
│   │   └── transmission-daemon  # Transmission守护进程
│   ├── lib/                # 构建产生的库文件
│   │   └── libminiupnpc.so.*    # UPnP功能库文件
│   └── ui/                  # WebUI资源（平铺于 ui/ 根，无额外 web 子目录，避免 fnOS 生成多余软链接）
│       ├── config          # 桌面应用配置
│       ├── images/         # 应用图标
│       │   ├── icon_64.png # 64x64图标
│       │   └── icon_256.png # 256x256图标
│       ├── index.html      # WebUI主页面
│       ├── assets/         # WebUI 静态资源
│       ├── css/            # WebUI样式文件
│       ├── js/             # WebUI脚本文件
│       └── update-check.js # 应用更新检测脚本
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
├── build.py                # 跨平台构建脚本（Windows/Linux/macOS）
├── LICENSE                 # 项目许可证
└── manifest                # 应用元数据
```

---

## 🔄 升级数据保护

升级时会自动备份和恢复数据到 `shares` 目录，确保配置和下载任务不丢失。

---

## 📚 开源项目

| 项目 | 版本 | 用途 | 许可证 |
|------|------|------|--------|
| [Transmission](https://github.com/transmission/transmission) | 4.1.3 | BitTorrent 客户端核心 | [GPL-2.0](https://www.gnu.org/licenses/gpl-2.0.html) |
| [transmission-web](https://github.com/jianxcao/transmission-web) | 0.1.0 | WebUI 界面 | [MIT](https://opensource.org/licenses/MIT) |

---

## 🤝 支持与反馈

- [报告问题](https://github.com/sushazhi/fnos-transmission/issues) - GitHub Issues
- [飞牛论坛](https://club.fnnas.com/) - 社区讨论
- [fnOS 文档](https://docs.fnnas.com/) - 官方文档

---

## 🧭 改进与规划建议

- [改进建议清单](docs/IMPROVEMENT_SUGGESTIONS.md) - 包含基础与进阶的稳定性、安全性、体验与工程化改进路线

---

## 📝 更新日志

### v4.1.3.2.8
- 🛠️ 修复升级时种子数据（torrents）丢失：备份路径多候选解析、恢复完整性校验、备份保留策略
- 🔧 升级不再重置用户 RPC 绑定/认证设置
- 🔐 RPC 认证开启后，通过 fnOS 统一网关访问仍免密（代理自动注入凭证）

### v4.1.3.2.1
- ✨ 新增打开/选择下载目录（fnOS文件选择器）

### v4.1.1
- ✨ 升级至 Transmission 4.1.1

---

感谢 [Transmission](https://github.com/transmission/transmission) 和 [transmission-web](https://github.com/jianxcao/transmission-web) 开源项目的支持。
