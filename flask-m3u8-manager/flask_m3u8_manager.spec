# -*- mode: python ; coding: utf-8 -*-
import os
import sys
import subprocess

block_cipher = None

# 获取当前目录
current_dir = os.path.dirname(os.path.abspath(SPEC))

# 检查并解压 FFmpeg 文件（仅在打包时）
def ensure_ffmpeg_binaries():
    """确保 FFmpeg 二进制文件可用于打包"""
    bin_dir = os.path.join(current_dir, 'bin')
    bin_7z = os.path.join(current_dir, 'bin.7z')
    ffmpeg_exe = os.path.join(bin_dir, 'ffmpeg.exe')

    # 如果 bin 目录不存在或 ffmpeg.exe 不存在，则解压
    if not os.path.exists(ffmpeg_exe):
        if os.path.exists(bin_7z):
            print("正在为打包解压 FFmpeg 文件...")
            try:
                # 尝试使用 7z 命令解压
                result = subprocess.run(['7z', 'x', bin_7z, f'-o{bin_dir}'],
                                      capture_output=True, text=True)
                if result.returncode == 0:
                    print("FFmpeg 文件解压成功")
                else:
                    print(f"警告: 7z 解压失败: {result.stderr}")
                    print("请手动解压 bin.7z 到 bin/ 目录")
            except FileNotFoundError:
                print("警告: 未找到 7z 命令")
                print("请安装 p7zip 或手动解压 bin.7z 到 bin/ 目录")
        else:
            print("警告: bin.7z 文件不存在，FFmpeg 将不会被包含在打包中")
    else:
        print("FFmpeg 文件已准备就绪")

# 执行 FFmpeg 检查
ensure_ffmpeg_binaries()

# 动态构建 binaries 列表
def get_ffmpeg_binaries():
    """获取可用的 FFmpeg 二进制文件列表"""
    binaries = []
    ffmpeg_files = [
        'ffmpeg.exe', 'ffplay.exe', 'ffprobe.exe',
        'avcodec-62.dll', 'avdevice-62.dll', 'avfilter-11.dll',
        'avformat-62.dll', 'avutil-60.dll', 'swresample-6.dll', 'swscale-9.dll'
    ]

    for filename in ffmpeg_files:
        filepath = os.path.join(current_dir, 'bin', filename)
        if os.path.exists(filepath):
            binaries.append((filepath, 'bin'))
        else:
            print(f"警告: {filename} 不存在，将不会被包含在打包中")

    return binaries

a = Analysis(
    ['start.py'],
    pathex=[current_dir],
    binaries=get_ffmpeg_binaries(),
    datas=[
        ('templates', 'templates'),
        ('static', 'static'),
        ('config.py', '.'),
        ('models.py', '.'),
        ('m3u8_processor.py', '.'),
        ('app.py', '.'),
        ('llm_service.py', '.'),
    ],
    hiddenimports=[
        'flask',
        'flask.templating',
        'flask_cors',
        'flask_sqlalchemy',
        'requests',
        'm3u8',
        'pycryptodomex',
        'urllib3',
        'colorlog',
        'sqlite3',
        'threading',
        'uuid',
        'json',
        'datetime',
        'pathlib',
        'subprocess',
        'webbrowser',
        'werkzeug',
        'werkzeug.security',
        'jinja2',
        'markupsafe',
        'itsdangerous',
        'click',
        'blinker',
        'sqlalchemy',
        'sqlalchemy.dialects.sqlite',
        'sqlalchemy.pool',
        'email_validator',
        'wtforms',
        'platform',
        'time',
        'os',
        'sys',
        'urllib.parse',
        'concurrent.futures',
        'queue',
        'logging',
        'traceback',
        'functools',
        'collections',
        're',
        'base64',
        'hashlib',
        'hmac',
        'secrets',
        'tempfile',
        'shutil',
        'glob',
        'mimetypes',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'numpy',
        'pandas',
        'scipy',
        'PIL',
        'cv2',
        'torch',
        'tensorflow',
        'downloads.db',  # 排除本地数据库文件
        '*.db',          # 排除所有数据库文件
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='Flask-M3U8-Manager',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(current_dir, 'static', 'favicon.ico') if os.path.exists(os.path.join(current_dir, 'static', 'favicon.ico')) else None,
)
