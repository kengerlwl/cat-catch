# 域名配置功能使用说明

## 功能概述

域名配置功能允许您为不同的域名设置专用的 HTTP Headers 和 Cookies。这些配置将在访问 M3U8 文件和下载视频切片时自动应用，帮助您绕过某些网站的访问限制。

## 主要特性

- ✅ **内存存储**：配置存储在内存中，重启应用后需要重新配置
- ✅ **自动应用**：在解析 M3U8、下载切片、获取解密密钥时自动应用对应域名的配置
- ✅ **智能合并**：域名配置会与默认 headers 智能合并，不会覆盖必要的默认设置
- ✅ **Cookie 处理**：自动将 Cookie 对象转换为标准的 Cookie 请求头格式

## 使用方法

### 1. 访问配置页面

在 M3U8 下载管理器主页面，点击 **🌐 域名配置** 按钮，或直接访问：
```
http://localhost:5001/domain-config
```

### 2. 添加域名配置

1. 在 **域名** 字段输入目标域名（不包含协议），例如：`example.com`
2. 在 **Headers** 字段输入 JSON 格式的自定义请求头
3. 在 **Cookies** 字段输入 JSON 格式的 Cookie 数据
4. 点击 **💾 保存配置**

### 3. 配置示例

#### Headers 配置示例
```json
{
  "Authorization": "Bearer your-access-token",
  "X-Requested-With": "XMLHttpRequest",
  "X-Custom-Header": "custom-value"
}
```

#### Cookies 配置示例
```json
{
  "session_id": "abc123def456",
  "user_token": "xyz789",
  "preferences": "theme=dark&lang=zh"
}
```

## 工作原理

### 1. 域名匹配
系统会从 URL 中提取域名部分，并查找对应的配置：
- `https://example.com/video.m3u8` → 匹配域名 `example.com`
- `http://sub.example.com/playlist.m3u8` → 匹配域名 `sub.example.com`

### 2. 配置应用时机
域名配置会在以下场景自动应用：
- **M3U8 解析**：访问 M3U8 播放列表文件时
- **切片下载**：下载每个视频切片时
- **密钥获取**：下载加密视频的解密密钥时

### 3. Headers 合并规则
- 域名配置的 headers 会与默认 headers 合并
- 如果存在同名 header，域名配置优先级更高
- Cookie 会自动合并到 `Cookie` 请求头中

## 实际应用场景

### 场景 1：需要身份验证的网站
某些网站需要登录后才能访问视频资源：
```json
// Headers 配置
{
  "Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "X-User-ID": "12345"
}

// Cookies 配置
{
  "session": "s%3Aj6DOTvIo7-Zlxh7hJGd4Ur6bCNnfBP1q",
  "auth_token": "abc123def456ghi789"
}
```

### 场景 2：防盗链保护
某些网站检查 Referer 和 Origin：
```json
// Headers 配置
{
  "Referer": "https://example.com/",
  "Origin": "https://example.com"
}
```

### 场景 3：API 访问控制
需要特定 API 密钥的网站：
```json
// Headers 配置
{
  "X-API-Key": "your-api-key-here",
  "X-Client-Version": "1.0.0"
}
```

## 注意事项

1. **内存存储**：配置只存储在内存中，应用重启后会丢失
2. **域名精确匹配**：子域名需要单独配置（`www.example.com` 和 `example.com` 是不同的域名）
3. **JSON 格式**：Headers 和 Cookies 必须是有效的 JSON 格式
4. **安全性**：请不要在配置中包含敏感信息，因为配置会在日志中显示

## API 接口

如果需要通过程序化方式管理域名配置，可以使用以下 API：

### 获取所有配置
```http
GET /api/domain-configs
```

### 保存配置
```http
POST /api/domain-configs
Content-Type: application/json

{
  "domain": "example.com",
  "headers": {"Authorization": "Bearer token"},
  "cookies": {"session": "abc123"}
}
```

### 删除配置
```http
DELETE /api/domain-configs/example.com
```

## 故障排除

### 配置不生效
1. 检查域名是否正确（不包含协议，使用小写）
2. 确认 JSON 格式是否正确
3. 查看应用日志中的域名配置应用信息

### JSON 格式错误
确保 Headers 和 Cookies 使用正确的 JSON 格式：
```json
// 正确 ✅
{
  "key": "value",
  "another": "data"
}

// 错误 ❌
{
  key: "value",        // 缺少引号
  "another": 'data'    // 使用单引号
}
```

## 更新日志

- **v1.0.0**：初始版本，支持基本的域名配置功能
- 支持 Headers 和 Cookies 配置
- 自动应用到 M3U8 解析和切片下载
- 提供 Web 管理界面和 API 接口
