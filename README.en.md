# Transmission for fnOS 🚀

[![Transmission Version](https://img.shields.io/badge/Transmission-4.1.0-blue?style=flat-square)](https://github.com/transmission/transmission/releases)
[![WebUI Version](https://img.shields.io/badge/WebUI-0.0.8-green?style=flat-square)](https://github.com/jianxcao/transmission-web/releases)
[![Platform](https://img.shields.io/badge/Platform-fnOS-green?style=flat-square)](https://www.fnnas.com/)
[![License](https://img.shields.io/badge/License-GPL--2.0-blue?style=flat-square)](https://www.gnu.org/licenses/gpl-2.0.html)

> 📌 **Note**: This application currently only supports **ARM64 architecture**

---

## ✨ Features

- 🎯 **Lightweight** - Low resource usage, efficient operation
- 📡 **Full Protocol** - Support for magnet links, torrent files, DHT/PEX/LSD
- ⚡ **Speed Control** - Flexible speed limits and queue management
- 🌐 **WebUI** - Built-in web interface for remote management
- 💾 **Data Persistence** - Configuration and downloads stored in dedicated storage
- 🔄 **Smooth Upgrades** - Automatic backup and restore during upgrades

---

## 📦 Installation

### Manual Installation

1. Open **App Center**
2. Click **Manual Install** at bottom left
3. Select the installation package

---

## 💻 System Requirements

| Item | Default |
|------|---------|
| Access URL | `http://<NAS_IP>:9090/transmission/` |
| Service Port | 9090 |
| Architecture | ARM64 (aarch64) |

### Storage Permissions

- **Read/Write**: `transmission` shared storage

---

## 📁 Project Structure

```
transmission-fnos/
├── cmd/                    # fnOS lifecycle scripts
│   ├── main               # Main service control script
│   ├── install_init       # Pre-install initialization
│   ├── install_callback   # Post-install callback
│   ├── upgrade_init       # Pre-upgrade backup
│   ├── upgrade_callback   # Post-upgrade restore
│   ├── uninstall_init     # Pre-uninstall cleanup
│   └── uninstall_callback # Post-uninstall cleanup
├── config/                # Configuration files
│   ├── privilege          # Permission config (ports, mounts)
│   └── resource           # Resource mapping config
├── wizard/                # Wizard UI definitions
│   ├── install            # Installation wizard
│   ├── upgrade            # Upgrade wizard
│   └── uninstall          # Uninstall wizard
├── ui/                    # Desktop icon resources
├── manifest               # Application metadata
└── package.json           # Build scripts
```

---

## 🔄 Upgrade Data Protection

Data is automatically backed up and restored during upgrades to the shares directory, ensuring configuration and download tasks are preserved.

---

## 📚 Open Source Projects

| Project | Version | Purpose | License |
|---------|---------|---------|---------|
| [Transmission](https://github.com/transmission/transmission) | 4.1.0 | BitTorrent client core | [GPL-2.0](https://www.gnu.org/licenses/gpl-2.0.html) |
| [transmission-web](https://github.com/jianxcao/transmission-web) | 0.0.8 | WebUI interface | [MIT](https://opensource.org/licenses/MIT) |

---

## 🤝 Support & Feedback

- [Report Issues](https://github.com/sushazhi/fnos-transmission/issues) - GitHub Issues
- [Feiniu Forum](https://club.fnnas.com/) - Community discussion
- [fnOS Documentation](https://docs.fnnas.com/) - Official documentation

---

## 📝 Changelog

### v4.1.0
- ✨ Upgrade to Transmission 4.1.0
- 🌐 Enable modern WebUI by default
- 🔧 Optimize installation and upgrade process

---

Thanks to [Transmission](https://github.com/transmission/transmission) and [transmission-web](https://github.com/jianxcao/transmission-web) open source projects for their support.
