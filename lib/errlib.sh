#!/bin/bash
# lib/errlib.sh - 错误处理工具库
# 提供标准化的错误处理函数

# 初始化错误日志路径
init_error_log() {
    ERROR_LOG="${TRIM_TEMP_LOGFILE:-/tmp/transmission_error.log}"
    export ERROR_LOG
}

# 写入错误日志并退出
# 用法: error_exit "错误信息" [退出码]
error_exit() {
    local message="$1"
    local exit_code="${2:-1}"
    
    # 确保ERROR_LOG已初始化
    if [ -z "$ERROR_LOG" ]; then
        init_error_log
    fi
    
    # 写入错误日志
    echo "$message" > "$ERROR_LOG"
    
    # 退出
    exit $exit_code
}

# 写入错误日志（不退出）
# 用法: log_error "错误信息"
log_error() {
    local message="$1"
    
    if [ -z "$ERROR_LOG" ]; then
        init_error_log
    fi
    
    echo "$message" >> "$ERROR_LOG"
}

# 检查命令执行结果
# 用法: check_result $? "成功消息" "失败消息"
check_result() {
    local result=$1
    local success_msg="$2"
    local error_msg="$3"
    
    if [ $result -eq 0 ]; then
        [ -n "$success_msg" ] && echo "$success_msg"
        return 0
    else
        [ -n "$error_msg" ] && log_error "$error_msg"
        return 1
    fi
}

# 检查文件或目录是否存在
# 用法: check_exists file|dir path "名称"
check_exists() {
    local type="$1"
    local path="$2"
    local name="$3"
    
    if [ "$type" = "file" ]; then
        if [ ! -f "$path" ]; then
            log_error "${name}不存在: ${path}"
            return 1
        fi
    elif [ "$type" = "dir" ]; then
        if [ ! -d "$path" ]; then
            log_error "${name}不存在: ${path}"
            return 1
        fi
    fi
    
    return 0
}

# 检查环境变量
# 用法: check_env VAR1 VAR2 ...
check_env() {
    local missing=false
    
    for var in "$@"; do
        if [ -z "${!var}" ]; then
            log_error "环境变量未设置: ${var}"
            missing=true
        fi
    done
    
    if [ "$missing" = true ]; then
        return 1
    fi
    
    return 0
}

# 创建错误处理配置
setup_error_handling() {
    # 初始化错误日志
    init_error_log
    
    # 确保错误日志文件存在且可写
    mkdir -p "$(dirname "$ERROR_LOG")" 2>/dev/null || true
}
