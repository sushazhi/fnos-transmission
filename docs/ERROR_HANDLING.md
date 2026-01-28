# 应用错误异常展示处理

## 概述

fnOS应用中心支持在脚本执行出错时，将错误信息以Dialog对话框形式展示给用户。

## TRIM_TEMP_LOGFILE 支持范围

**✅ 支持的脚本**（错误会展示给用户）：
- `cmd/main` - 主生命周期管理脚本
- `cmd/install_init` - 安装初始化脚本
- `cmd/install_callback` - 安装后置脚本
- `cmd/upgrade_init` - 升级初始化脚本
- `cmd/upgrade_callback` - 升级回调脚本

**❌ 不支持的脚本**（错误不会展示给用户）：
- `cmd/config_init` - 配置初始化脚本
- `cmd/config_callback` - 配置回调脚本
- `cmd/uninstall_init` - 卸载初始化脚本
- `cmd/uninstall_callback` - 卸载回调脚本

## 使用方式

### 标准错误处理模式

```bash
#!/bin/bash

# 错误日志文件路径
ERROR_LOG="${TRIM_TEMP_LOGFILE:-/tmp/transmission_error.log}"

# 写入错误日志并退出（会展示给用户）
error_exit() {
    local message="$1"
    local exit_code="${2:-1}"
    echo "$message" > "$ERROR_LOG"
    exit $exit_code
}

# 使用示例
case "$1" in
    start)
        # 检查环境变量
        if [ -z "$TRIM_APPDEST" ]; then
            error_exit "错误：TRIM_APPDEST 环境变量未设置，应用无法启动"
        fi
        
        # 检查文件存在
        if [ ! -f "/path/to/binary" ]; then
            error_exit "错误：可执行文件不存在，启动失败" 1
        fi
        
        # 启动应用
        ./myapp
        ;;
esac
```

### 错误码说明

| 错误码 | 说明 |
|--------|------|
| `exit 0` | 成功，无错误 |
| `exit 1` | 通用错误，会展示ERROR_LOG内容 |
| 其他 | 不建议使用 |

### 不写入TRIM_TEMP_LOGFILE的情况

直接 `exit 1` 不写入日志时，系统会显示：
```
执行XX脚本出错且原因未知
```

## 示例代码

### cmd/main 错误处理

```bash
#!/bin/bash

ERROR_LOG="${TRIM_TEMP_LOGFILE:-/tmp/transmission-daemon_error.log}"

error_exit() {
    echo "$1" > "$ERROR_LOG"
    exit 1
}

start() {
    # 检查必要文件
    if [ ! -f "$BIN_DIR/transmission-daemon" ]; then
        error_exit "错误：transmission-daemon 未找到或不可执行，请检查安装"
    fi
    
    # 启动服务
    "$BIN_DIR/transmission-daemon" --config-dir "$DATA_DIR" &
    
    # 验证启动
    sleep 2
    if ! ps -p $! > /dev/null; then
        error_exit "错误：transmission-daemon 启动失败，请检查日志"
    fi
    
    echo "启动成功"
}
```

### cmd/install_init 错误处理

```bash
#!/bin/bash

ERROR_LOG="${TRIM_TEMP_LOGFILE:-/tmp/transmission_error.log}"

error_exit() {
    echo "$1" > "$ERROR_LOG"
    exit 1
}

echo "正在安装..."

# 检查环境变量
if [ -z "$TRIM_PKGVAR" ]; then
    error_exit "错误：TRIM_PKGVAR 环境变量未设置，安装失败"
fi

# 创建目录
if ! mkdir -p "${TRIM_PKGVAR}/data" 2>/dev/null; then
    error_exit "错误：无法创建数据目录，安装失败"
fi

echo "安装成功"
exit 0
```

## 注意事项

1. **只对支持的脚本生效** - config和uninstall脚本不支持错误展示
2. **使用 `exit 1`** - 返回错误码1才会触发错误展示
3. **写入完整错误信息** - 包括错误原因和可能的解决方案
4. **不要使用 `set -e`** - 配合错误处理时需谨慎
5. **错误信息要友好** - 避免显示技术细节，用用户能理解的语言

## 错误信息最佳实践

| 不好 ❌ | 好 ✅ |
|---------|------|
| "File not found" | "配置文件不存在，请重新安装应用" |
| "Segmentation fault" | "应用发生错误，请检查系统资源是否充足" |
| "Null pointer exception" | "发生未知错误，请联系技术支持" |

## 相关文件

- `lib/errlib.sh` - 错误处理工具库（可选使用）
- `cmd/main` - 主脚本（支持错误展示）
- `cmd/install_*` - 安装脚本（支持错误展示）
- `cmd/upgrade_*` - 升级脚本（支持错误展示）
