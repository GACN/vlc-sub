#!/bin/bash
set -e

# 1. 进入项目目录
TARGET_DIR="/home/kali/文档/vlc-sub"
if [ -d "$TARGET_DIR" ]; then
    cd "$TARGET_DIR"
else
    echo "错误：找不到目录 $TARGET_DIR"
    read -p "按回车退出..."
    exit 1
fi

echo "当前目录: $(pwd)"

# 2. 智能查找并激活虚拟环境 (自动判断路径)
if [ -f "bin/activate" ]; then
    echo "发现环境在当前目录，正在激活..."
    source bin/activate
elif [ -f "vlc-sub/bin/activate" ]; then
    echo "发现环境在子目录，正在激活..."
    source vlc-sub/bin/activate
else
    echo "❌ 严重错误：找不到 bin/activate 启动文件！"
    echo "请检查你的虚拟环境安装位置。"
    echo "当前目录下的文件有："
    ls -F
    read -p "按回车退出..."
    exit 1
fi

# 3. 设置环境变量
export LD_LIBRARY_PATH=`python3 -c 'import os; import nvidia.cublas.lib; import nvidia.cudnn.lib; print(os.path.dirname(nvidia.cublas.lib.__file__) + ":" + os.path.dirname(nvidia.cudnn.lib.__file__))'`:$LD_LIBRARY_PATH
export GTK_THEME=Adwaita
export HF_ENDPOINT=https://hf-mirror.com

# 4. 启动程序
echo "正在启动 AI 字幕 (v2)..."
python live_sub_v2.py

# 5. 退出保护
echo "程序已结束。"
read -p "按回车键关闭窗口..."
