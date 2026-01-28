# Transmission密码加密说明

## 加密方式

Transmission使用 **SHA-1(password + salt)** 格式存储密码。

## 加密格式

```
{40位SHA-1哈希 + 7位Salt}
```

**示例**: {0b68e34b1c16c7a00f955accef73db738ab311f00SFLPoE7}

## 组成部分

| 部分 | 长度 | 说明 |
|------|------|------|
| { | 1 | 开始符号 |
| SHA-1哈希 | 40 | SHA-1(密码 + Salt)的十六进制结果 |
| Salt | 7 | 随机字母数字字符串 |
| } | 1 | 结束符号 |

## 默认凭据

| 项目 | 默认值 |
|------|--------|
| 用户名 | admin |
| 密码 | password |
| 端口 | 9090 |

## 相关文件

- cmd/install_callback - 安装时生成加密密码
- cmd/config_callback - 配置回调，支持更新密码
- tools/generate-password.sh - 密码生成工具
