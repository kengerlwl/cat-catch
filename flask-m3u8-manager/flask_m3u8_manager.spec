# -*- mode: python ; coding: utf-8 -*-
import os
import sys
import subprocess

block_cipher = None

# Get current directory
current_dir = os.path.dirname(os.path.abspath(SPEC))

# Check and extract FFmpeg files (only during packaging)
def ensure_ffmpeg_binaries():
    """Ensure FFmpeg binaries are available for packaging"""
    bin_dir = os.path.join(current_dir, 'bin')
    bin_7z = os.path.join(current_dir, 'bin.7z')
    ffmpeg_exe = os.path.join(bin_dir, 'ffmpeg.exe')

    # If bin directory or ffmpeg.exe doesn't exist, extract from bin.7z
    if not os.path.exists(ffmpeg_exe):
        if os.path.exists(bin_7z):
            print("Extracting FFmpeg files for packaging...")
            try:
                # Try to use 7z command to extract
                result = subprocess.run(['7z', 'x', bin_7z, f'-o{bin_dir}'],
                                      capture_output=True, text=True)
                if result.returncode == 0:
                    print("FFmpeg files extracted successfully")
                else:
                    print(f"Warning: 7z extraction failed: {result.stderr}")
                    print("Please manually extract bin.7z to bin/ directory")
            except FileNotFoundError:
                print("Warning: 7z command not found")
                print("Please install p7zip or manually extract bin.7z to bin/ directory")
        else:
            print("Warning: bin.7z file not found, FFmpeg will not be included in the build")
    else:
        print("FFmpeg files are ready")

# Execute FFmpeg check
ensure_ffmpeg_binaries()

# Dynamically build binaries list
def get_ffmpeg_binaries():
    """Get available FFmpeg binary files list"""
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
            print(f"Warning: {filename} not found, will not be included in the build")

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
        'downloads.db',  # Exclude local database files
        '*.db',          # Exclude all database files
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
