#!/bin/bash

# 设置颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "========================================"
echo -e "${BLUE}🎬 Flask M3U8 下载管理器${NC}"
echo "========================================"
echo

# 检查Python是否安装
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ 错误: 未找到Python3，请先安装Python 3.7+${NC}"
    echo "Ubuntu/Debian: sudo apt install python3 python3-pip python3-venv"
    echo "CentOS/RHEL: sudo yum install python3 python3-pip"
    echo "macOS: brew install python3"
    exit 1
fi

# 检查pip是否可用
if ! command -v pip3 &> /dev/null; then
    echo -e "${RED}❌ 错误: pip3不可用，请检查Python安装${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Python环境检查通过${NC}"
echo

# 检查是否存在虚拟环境
if [ ! -d "venv" ]; then
    echo -e "${YELLOW}📦 创建虚拟环境...${NC}"
    python3 -m venv venv
    if [ $? -ne 0 ]; then
        echo -e "${RED}❌ 创建虚拟环境失败${NC}"
        exit 1
    fi
    echo -e "${GREEN}✅ 虚拟环境创建成功${NC}"
fi

# 激活虚拟环境
echo -e "${YELLOW}🔄 激活虚拟环境...${NC}"
source venv/bin/activate

# 安装依赖
echo -e "${YELLOW}📥 安装依赖包...${NC}"
pip install -r requirements.txt
if [ $? -ne 0 ]; then
    echo -e "${RED}❌ 依赖安装失败，请检查网络连接${NC}"
    exit 1
fi

echo -e "${GREEN}✅ 依赖安装完成${NC}"
echo

# 检查FFmpeg
if ! command -v ffmpeg &> /dev/null; then
    echo -e "${YELLOW}⚠️  警告: 未找到FFmpeg，MP4转换功能将不可用${NC}"
    echo "Ubuntu/Debian: sudo apt install ffmpeg"
    echo "CentOS/RHEL: sudo yum install ffmpeg"
    echo "macOS: brew install ffmpeg"
    echo
fi

# 启动Flask应用
echo -e "${BLUE}🚀 启动Flask M3U8 下载管理器...${NC}"
echo
python start.py
