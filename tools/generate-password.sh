#!/bin/bash
# tools/generate-password.sh - Transmission密码生成工具
# 生成符合Transmission格式的加密密码

set -e

# 默认密码
PASSWORD="${1:-password}"

# 生成7字符随机salt
generate_salt() {
    head -c 7 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 7
}

# 生成加密密码
generate_encrypted_password() {
    local plain_password="$1"
    local salt=$(generate_salt)
    local hash=$(echo -n "${plain_password}${salt}" | sha1sum | cut -d' ' -f1)
    echo "{${hash}${salt}}"
}

echo "=== Transmission密码生成工具 ==="
echo ""
echo "原始密码: ${PASSWORD}"
echo "加密密码: $(generate_encrypted_password "$PASSWORD")"
echo ""
echo "加密格式: {SHA1(密码 + Salt)Salt}"
echo "Salt长度: 7字符"
echo "Hash算法: SHA-1"
echo ""

# 验证密码（可选）
if [ -n "$2" ]; then
    echo "验证密码..."
    ENCRYPTED="$2"
    EXPECTED=$(generate_encrypted_password "$PASSWORD")
    if [ "$ENCRYPTED" = "$EXPECTED" ]; then
        echo "✅ 密码验证成功"
    else
        echo "❌ 密码验证失败"
        echo "期望: $EXPECTED"
        echo "实际: $ENCRYPTED"
    fi
fi
