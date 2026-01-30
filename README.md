# Transmission for fnOS 🚀

🌐 **语言/Language**
- [简体中文](README.md) | [English](README_EN.md)

[![Transmission Version](https://img.shields.io/badge/Transmission-4.1.0-blue?style=flat-square)](https://github.com/transmission/transmission/releases)
[![WebUI Version](https://img.shields.io/badge/WebUI-0.0.8-green?style=flat-square)](https://github.com/jianxcao/transmission-web/releases)
[![Platform](https://img.shields.io/badge/Platform-fnOS-green?style=flat-square)](https://www.fnnas.com/)
[![License](https://img.shields.io/badge/License-GPL--2.0-blue?style=flat-square)](https://www.gnu.org/licenses/gpl-2.0.html)

> 📌 **注意**：本应用目前仅支持**ARM64架构**

---

## ✨ 特色功能

- 🎯 **轻量级** - 资源占用低，运行高效
- 📡 **完整协议** - 支持磁力链接、种子文件、DHT/PEX/LSD
- ⚡ **速度控制** - 灵活的速度限制和队列管理
- 🌐 **WebUI** - 内置Web界面，随时随地管理
- 💾 **数据持久化** - 配置和下载数据保存在独立存储空间
- 🔄 **平滑升级** - 升级时自动备份和恢复数据

---

## 📦 安装说明

### 手动安装

1. 打开 **应用中心**
2. 点击左下角 **手动安装**
3. 选择安装包

---

## 💻 系统要求

| 项目 | 默认值 |
|------|--------|
| 访问地址 | `http://<NAS_IP>:9090/transmission/` |
| 服务端口 | 9090 |
| 架构 | ARM64 (aarch64) |

### 存储权限

- **读取/写入**：`transmission` 共享存储

---

## 📁 项目结构

```
fnos-transmission/
├── app/                    # fnOS应用资源
│   ├── bin/                # 构建产生的可执行文件
│   │   ├── transmission-daemon  # Transmission守护进程
│   │   ├── transmission-cli     # 命令行工具（可选）
│   │   └── transmission-remote  # 远程控制工具（可选）
│   ├── lib/                # 构建产生的库文件
│   │   └── libminiupnpc.so.*    # UPnP功能库文件
│   └── ui/                  # WebUI资源
│       ├── config          # 桌面应用配置
│       ├── images/         # 应用图标
│       │   ├── icon_64.png # 64x64图标
│       │   └── icon_256.png # 256x256图标
│       ├── index.html      # WebUI主页面
│       ├── css/            # WebUI样式文件
│       └── js/             # WebUI脚本文件
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
| [Transmission](https://github.com/transmission/transmission) | 4.1.0 | BitTorrent 客户端核心 | [GPL-2.0](https://www.gnu.org/licenses/gpl-2.0.html) |
| [transmission-web](https://github.com/jianxcao/transmission-web) | 0.0.8 | WebUI 界面 | [MIT](https://opensource.org/licenses/MIT) |

---

## 🤝 支持与反馈

- [报告问题](https://github.com/sushazhi/fnos-transmission/issues) - GitHub Issues
- [飞牛论坛](https://club.fnnas.com/) - 社区讨论
- [fnOS 文档](https://docs.fnnas.com/) - 官方文档

---

## 📝 更新日志

### v4.1.0
- ✨ 升级至 Transmission 4.1.0
- 🌐 默认启用 WebUI 现代界面
- 🔧 优化安装和升级流程

---

感谢 [Transmission](https://github.com/transmission/transmission) 和 [transmission-web](https://github.com/jianxcao/transmission-web) 开源项目的支持。
