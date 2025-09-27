# Flask M3U8 下载管理器

一个功能强大的M3U8视频下载管理平台，与cat-catch浏览器扩展完美集成。

## 🌟 主要功能

### 📥 下载管理
- **添加下载任务**: 支持M3U8链接的批量下载管理
- **任务控制**: 暂停、恢复、删除下载任务
- **进度监控**: 实时显示下载进度和状态
- **断点续传**: 支持下载中断后继续下载

### 🎬 视频处理
- **切片保存**: 自动下载并保存M3U8视频切片到本地
- **MP4转换**: 将下载完成的切片转换为MP4格式
- **在线播放**: 支持直接播放M3U8和转换后的MP4文件

### 🔗 扩展集成
- **一键后台下载**: 在cat-catch扩展的m3u8下载页面添加"后台下载"按钮
- **无缝衔接**: 直接从浏览器扩展发送下载任务到Flask后台

## 🚀 快速开始

### 1. 安装依赖

```bash
cd flask-m3u8-manager
pip install -r requirements.txt
```

### 2. 启动服务

```bash
python start.py
```

或者直接运行：

```bash
python app.py
```

### 3. 访问界面

服务启动后会自动打开浏览器访问：http://localhost:5001

## 📖 使用说明

### 在Flask管理界面中：

1. **添加任务**: 在"添加下载任务"区域输入M3U8链接
2. **管理任务**: 在任务列表中可以暂停、恢复、删除任务
3. **转换视频**: 下载完成后可以转换为MP4格式
4. **播放视频**: 点击播放按钮在线观看

### 在cat-catch扩展中：

1. 在m3u8下载页面解析M3U8链接
2. 点击"🚀 后台下载"按钮
3. 任务会自动添加到Flask后台管理系统
4. 可选择打开管理界面查看下载进度

## 📁 文件结构

```
flask-m3u8-manager/
├── app.py                 # Flask主应用
├── start.py              # 启动脚本
├── requirements.txt      # Python依赖
├── README.md            # 说明文档
├── templates/           # HTML模板
│   ├── index.html      # 主页模板
│   └── play.html       # 播放页面模板
├── static/             # 静态文件
│   ├── css/
│   │   └── style.css   # 样式文件
│   └── js/
│       └── main.js     # 前端脚本
└── downloads/          # 下载目录
    ├── segments/       # 切片文件
    └── converted/      # 转换后的MP4文件
```

## 🔧 配置说明

### 下载目录
- **切片存储**: `downloads/segments/任务名称/`
- **转换输出**: `downloads/converted/任务名称.mp4`

### 服务配置
- **端口**: 5001 (可在app.py中修改)
- **主机**: 0.0.0.0 (允许局域网访问)

## 📋 API接口

### 任务管理
- `GET /api/tasks` - 获取所有任务
- `POST /api/tasks` - 创建新任务
- `GET /api/tasks/{id}` - 获取单个任务
- `POST /api/tasks/{id}/pause` - 暂停任务
- `POST /api/tasks/{id}/resume` - 恢复任务
- `POST /api/tasks/{id}/update_url` - 更新任务URL
- `DELETE /api/tasks/{id}/delete` - 删除任务

### 视频处理
- `POST /api/tasks/{id}/convert` - 转换为MP4
- `GET /api/tasks/{id}/play` - 获取播放URL
- `GET /api/download/{id}` - 下载转换后的文件

## 🛠️ 技术栈

- **后端**: Flask + Python
- **前端**: HTML5 + CSS3 + JavaScript (jQuery)
- **视频处理**: FFmpeg
- **M3U8解析**: m3u8库
- **HTTP请求**: requests库

## ⚠️ 注意事项

1. **FFmpeg依赖**: MP4转换功能需要系统安装FFmpeg
2. **端口占用**: 确保5001端口未被占用
3. **网络访问**: 下载需要稳定的网络连接
4. **存储空间**: 确保有足够的磁盘空间存储视频文件

## 🔍 故障排除

### 常见问题

1. **启动失败**: 检查端口5001是否被占用
2. **下载失败**: 检查M3U8链接是否有效
3. **转换失败**: 确保系统已安装FFmpeg
4. **跨域问题**: Flask已配置CORS，如仍有问题请检查浏览器设置

### 日志查看

Flask应用会在控制台输出详细的运行日志，包括：
- 任务创建和状态变化
- 下载进度信息
- 错误信息和异常

## 📄 许可证

本项目基于现有的cat-catch项目，遵循相同的开源许可证。

## 🤝 贡献

欢迎提交Issue和Pull Request来改进这个项目！
