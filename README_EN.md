# Transmission for fnOS 🚀

🌐 **语言/Language**
- [简体中文](README.md) | [English](README_EN.md)

[![Transmission Version](https://img.shields.io/badge/Transmission-4.1.0-blue?style=flat-square)](https://github.com/transmission/transmission/releases)
[![WebUI Version](https://img.shields.io/badge/WebUI-0.0.8-green?style=flat-square)](https://github.com/jianxcao/transmission-web/releases)
[![Platform](https://img.shields.io/badge/Platform-fnOS-green?style=flat-square)](https://www.fnnas.com/)
[![License](https://img.shields.io/badge/License-GPL--2.0-blue?style=flat-square)](https://www.gnu.org/licenses/gpl-2.0.html)

> 📌 **Note**: This app currently only supports **ARM64 architecture**

---

## ✨ Featured Functions

- 🎯 **Lightweight** - Low resource usage, efficient operation
- 📡 **Complete Protocol** - Support for magnet links, torrent files, DHT/PEX/LSD
- ⚡ **Speed Control** - Flexible speed limits and queue management
- 🌐 **WebUI** - Built-in web interface for management anywhere
- 💾 **Data Persistence** - Configuration and download data stored in independent storage
- 🔄 **Smooth Upgrade** - Automatic backup and recovery during upgrades

---

## 📦 Installation Instructions

### Manual Installation

1. Open **App Center**
2. Click **Manual Installation** at the bottom left
3. Select the installation package

---

## 💻 System Requirements

| Item | Default Value |
|------|--------------|
| Access Address | `http://<NAS_IP>:9090/transmission/` |
| Service Port | 9090 |
| Architecture | ARM64 (aarch64) |

### Storage Permissions

- **Read/Write**: `transmission` shared storage

---

## 📁 Project Structure

```
fnos-transmission/
├── app/                    # fnOS app resources
│   ├── bin/                # Build-generated executables
│   │   ├── transmission-daemon  # Transmission daemon
│   │   ├── transmission-cli     # Command-line tool (optional)
│   │   └── transmission-remote  # Remote control tool (optional)
│   ├── lib/                # Build-generated library files
│   │   └── libminiupnpc.so.*    # UPnP library files
│   └── ui/                  # WebUI resources
│       ├── config          # Desktop app configuration
│       ├── images/         # App icons
│       │   ├── icon_64.png # 64x64 icon
│       │   └── icon_256.png # 256x256 icon
│       ├── index.html      # WebUI main page
│       ├── css/            # WebUI styles
│       └── js/             # WebUI scripts
├── cmd/                    # fnOS lifecycle scripts
│   ├── config_callback     # Post-configuration callback
│   ├── config_init         # Configuration initialization
│   ├── install_init        # Pre-installation initialization
│   ├── install_callback    # Post-installation callback
│   ├── main               # Main service control script
│   ├── uninstall_init      # Pre-uninstallation cleanup
│   ├── uninstall_callback  # Post-uninstallation cleanup
│   ├── upgrade_init        # Pre-upgrade backup
│   └── upgrade_callback    # Post-upgrade recovery
├── config/                 # Configuration files
│   ├── privilege           # Permission configuration (ports, mount points)
│   └── resource            # Resource mapping configuration
├── wizard/                 # Wizard UI definitions
│   ├── config              # Configuration wizard
│   ├── install             # Installation wizard
│   ├── upgrade             # Upgrade wizard
│   └── uninstall           # Uninstallation wizard
├── LICENSE                 # Project license
└── manifest                # App metadata
```

---

## 🔄 Upgrade Data Protection

During upgrades, data is automatically backed up and restored to the `shares` directory, ensuring configurations and download tasks are not lost.

---

## 📚 Open Source Projects

| Project | Version | Purpose | License |
|---------|---------|---------|---------|
| [Transmission](https://github.com/transmission/transmission) | 4.1.0 | BitTorrent client core | [GPL-2.0](https://www.gnu.org/licenses/gpl-2.0.html) |
| [transmission-web](https://github.com/jianxcao/transmission-web) | 0.0.8 | WebUI interface | [MIT](https://opensource.org/licenses/MIT) |

---

## 🤝 Support and Feedback

- [Report Issues](https://github.com/sushazhi/fnos-transmission/issues) - GitHub Issues
- [Feiniu Forum](https://club.fnnas.com/) - Community Discussion
- [fnOS Documentation](https://docs.fnnas.com/) - Official Documentation

---

## 📝 Changelog

### v4.1.0
- ✨ Upgraded to Transmission 4.1.0
- 🌐 Modern WebUI interface enabled by default
- 🔧 Optimized installation and upgrade processes

---

Thanks to the support of the [Transmission](https://github.com/transmission/transmission) and [transmission-web](https://github.com/jianxcao/transmission-web) open source projects.