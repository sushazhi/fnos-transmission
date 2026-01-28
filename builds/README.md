# Transmission ARM64 二进制文件

此目录存放构建生成的ARM64二进制文件，可直接使用无需重复编译。

## 📦 文件说明

| 文件 | 说明 | 必需 |
|------|------|------|
| `transmission-daemon` | 主守护进程 | ✅ 是 |
| `transmission-cli` | 命令行工具 | ❌ 可选 |
| `transmission-remote` | 远程管理工具 | ❌ 可选 |
| `VERSION` | 版本信息文件 | ✅ 是 |

## 📋 VERSION 文件内容

```
TRANSMISSION_VERSION=4.1.0    # Transmission版本
WEBUI_VERSION=0.0.7           # WebUI版本
APP_VERSION=4.1.0             # 应用版本
ARCH=arm64                    # 架构
BUILT_AT=2026-01-28-19:30:00  # 构建时间
COMMIT=abc123...              # Git提交ID
```

## 🚀 使用方法

### 方法1：直接从builds目录使用

```bash
# 复制二进制到应用目录
cp builds/transmission-daemon app/bin/
cp builds/transmission-cli app/bin/      # 可选
cp builds/transmission-remote app/bin/   # 可选

# 设置可执行权限
chmod +x app/bin/transmission-*
```

### 方法2：GitHub Actions自动更新

每次main分支构建完成后，二进制文件会自动提交到此目录。

```bash
# 更新本地二进制
git pull origin main
```

## 🔨 重新构建

如果需要重新构建二进制：

```bash
# 确保在Linux ARM64环境或使用GitHub Actions
# 触发main分支构建
git push origin main
```

GitHub Actions将自动：
1. 交叉编译ARM64二进制
2. 集成transmission-web UI
3. 打包.fpk应用
4. **自动提交二进制到builds目录**

## ⚠️ 注意事项

- 二进制文件仅适用于ARM64架构
- 需要配合 `app/ui/transmission/` 中的WebUI文件使用
- 版本信息保存在 `VERSION` 文件中

## 📊 二进制信息

- **架构**: aarch64 (ARM64)
- **构建方式**: 交叉编译 (x86_64 → ARM64)
- **依赖库**: 静态链接或系统库
- **大小**: 约2-5MB