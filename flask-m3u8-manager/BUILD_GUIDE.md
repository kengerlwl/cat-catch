# Flask M3U8 Manager - 构建指南

本文档介绍如何将Flask M3U8 Manager打包为可执行文件（EXE）。

## 🚀 自动构建（推荐）

### GitHub Actions 自动构建

项目已配置GitHub Actions，会在以下情况自动构建Windows EXE文件：

1. **推送到主分支时**：当代码推送到 `main` 或 `master` 分支时
2. **Pull Request时**：当创建针对主分支的PR时
3. **手动触发**：在GitHub仓库的Actions页面手动运行

#### 构建产物获取方式：

1. **Artifacts下载**：
   - 进入GitHub仓库的Actions页面
   - 选择最新的构建任务
   - 下载 `Flask-M3U8-Manager-Windows-EXE` 文件

2. **Release下载**（仅主分支）：
   - 进入GitHub仓库的Releases页面
   - 下载最新版本的 `Flask-M3U8-Manager.exe`

## 🔧 本地构建

### Windows 本地构建

#### 前置要求：
- Python 3.8+ 已安装
- pip 包管理器可用
- **FFmpeg 支持**：确保 `bin.7z` 文件存在于项目根目录

#### 构建步骤：
```bash
# 1. 进入Flask应用目录
cd flask-m3u8-manager

# 2. 运行构建脚本
build_exe.bat
```

构建脚本会自动：
- 安装所需依赖
- 使用PyInstaller打包应用
- **打包时自动解压 bin.7z 中的 FFmpeg 文件**
- 生成独立的EXE文件（包含FFmpeg）

#### FFmpeg 集成特性：
- **智能打包**：只在打包时解压 FFmpeg，开发时保持仓库轻量
- **自动包含**：FFmpeg 可执行文件和依赖库会自动打包到 EXE 中
- **无需安装**：打包后的 EXE 文件无需系统安装 FFmpeg
- **开发友好**：开发时使用系统 FFmpeg，无需解压 bin.7z

### Linux/macOS 本地构建

#### 前置要求：
- Python 3.8+ 已安装
- pip 包管理器可用
- **FFmpeg 支持**：确保 `bin.7z` 文件存在于项目根目录
- **p7zip 工具**：用于解压 7z 文件（`brew install p7zip` 或 `sudo apt install p7zip-full`）

#### 构建步骤：
```bash
# 1. 进入Flask应用目录
cd flask-m3u8-manager

# 2. 运行构建脚本
./build_exe.sh
```

构建过程与 Windows 类似，会在打包时自动处理 FFmpeg 集成。

#### 构建步骤：
```bash
# 1. 进入Flask应用目录
cd flask-m3u8-manager

# 2. 运行构建脚本
./build_exe.sh
```

## 📁 构建产物

构建完成后，可执行文件位于：
- Windows: `dist/Flask-M3U8-Manager.exe`
- Linux/macOS: `dist/Flask-M3U8-Manager`

## 🎯 使用方法

1. **运行可执行文件**：
   - Windows: 双击 `Flask-M3U8-Manager.exe`
   - Linux/macOS: 在终端运行 `./Flask-M3U8-Manager`

2. **访问管理界面**：
   - 程序启动后会自动打开浏览器
   - 手动访问：http://localhost:5001

3. **开始使用**：
   - 添加M3U8下载任务
   - 管理下载队列
   - 转换视频格式

## ⚙️ 高级配置

### 自定义PyInstaller配置

如需修改打包配置，编辑 `flask_m3u8_manager.spec` 文件：

```python
# 添加额外的数据文件
datas=[
    ('templates', 'templates'),
    ('static', 'static'),
    ('your_file.txt', '.'),  # 添加自定义文件
],

# 添加隐藏导入
hiddenimports=[
    'flask',
    'your_module',  # 添加自定义模块
],
```

### GitHub Actions 自定义

修改 `.github/workflows/build-flask-exe.yml` 来自定义构建流程：

- 更改Python版本
- 添加额外的构建步骤
- 修改发布配置

## 🐛 故障排除

### 常见问题

1. **构建失败 - 缺少依赖**：
   ```bash
   pip install -r requirements.txt
   pip install pyinstaller
   ```

2. **运行时错误 - 模块未找到**：
   - 检查 `flask_m3u8_manager.spec` 中的 `hiddenimports`
   - 添加缺失的模块到隐藏导入列表

3. **文件路径错误**：
   - 确保所有资源文件都在 `datas` 列表中
   - 检查相对路径是否正确

4. **EXE文件过大**：
   - 在spec文件中添加 `excludes` 排除不需要的模块
   - 使用 `upx=True` 启用压缩

5. **FFmpeg 相关问题**：
   - **bin.7z 不存在**：确保 `bin.7z` 文件在项目根目录
   - **解压失败**：手动解压 `bin.7z` 到 `bin/` 目录
   - **转换失败**：检查打包后的 EXE 是否包含 `bin/ffmpeg.exe`

### 调试模式

如需调试构建过程，可以：

1. **启用详细输出**：
   ```bash
   pyinstaller flask_m3u8_manager.spec --clean --noconfirm --log-level DEBUG
   ```

2. **生成目录模式**（而非单文件）：
   ```python
   # 在spec文件中修改
   exe = EXE(
       # ... 其他参数 ...
       onefile=False,  # 改为False
   )
   ```

## 📝 注意事项

1. **杀毒软件**：某些杀毒软件可能误报PyInstaller生成的EXE文件
2. **文件大小**：打包后的文件较大（通常50-100MB），这是正常现象
3. **启动时间**：首次启动可能需要几秒钟来解压和初始化
4. **数据库**：SQLite数据库文件会在EXE同目录下创建
5. **下载目录**：默认下载目录为EXE同目录下的 `downloads` 文件夹

## 🔗 相关链接

- [PyInstaller 官方文档](https://pyinstaller.readthedocs.io/)
- [GitHub Actions 文档](https://docs.github.com/en/actions)
- [Flask 部署指南](https://flask.palletsprojects.com/en/2.3.x/deploying/)
