#!/bin/bash

# 获取当前脚本所在目录
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

# 设置多个可能的库路径，包括当前目录的lib_compat
export LD_LIBRARY_PATH="$SCRIPT_DIR/lib:$SCRIPT_DIR/lib_compat:/app/lib:/app/lib_compat:/usr/lib64:/lib64:$LD_LIBRARY_PATH"

# 刷新库缓存
ldconfig 2>/dev/null || true

# 确定可执行文件路径
if [ -f "$SCRIPT_DIR/wxapi_linux_v1_0_5" ]; then
    WXAPI_PATH="$SCRIPT_DIR/wxapi_linux_v1_0_5"
    WORK_DIR="$SCRIPT_DIR"
elif [ -f "/app/wxapi_linux_v1_0_5" ]; then
    WXAPI_PATH="/app/wxapi_linux_v1_0_5"
    WORK_DIR="/app"
else
    echo "Error: wxapi_linux_v1_0_5 not found!"
    exit 1
fi

echo "Using wxapi path: $WXAPI_PATH"
echo "Working directory: $WORK_DIR"

# 检查库文件
echo "Checking library dependencies..."
ldd "$WXAPI_PATH"

# 检查关键库是否可用
echo "Checking critical libraries..."
if [ -f "$SCRIPT_DIR/lib_compat/libstdc++.so.6" ]; then
    echo "Found compatible libstdc++ in $SCRIPT_DIR/lib_compat"
    export LD_LIBRARY_PATH="$SCRIPT_DIR/lib_compat:$LD_LIBRARY_PATH"
elif [ -f "/app/lib_compat/libstdc++.so.6" ]; then
    echo "Found compatible libstdc++ in /app/lib_compat"
    export LD_LIBRARY_PATH="/app/lib_compat:$LD_LIBRARY_PATH"
fi

echo "Current LD_LIBRARY_PATH: $LD_LIBRARY_PATH"

# 启动应用
echo "Starting application..."
cd "$WORK_DIR"
exec "$WXAPI_PATH" 