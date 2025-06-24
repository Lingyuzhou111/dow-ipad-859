FROM ubuntu:24.04

# 避免交互式提示
ENV DEBIAN_FRONTEND=noninteractive

# 安装基本工具和时区
RUN apt-get update && apt-get install -y \
    ca-certificates \
    tzdata \
    libc6 \
    zlib1g \
    && rm -rf /var/lib/apt/lists/*

# 设置时区为中国时区
ENV TZ=Asia/Shanghai

# 创建应用目录
WORKDIR /app

# 创建lib目录并设置环境变量
RUN mkdir -p /app/lib
ENV LD_LIBRARY_PATH=/app/lib:$LD_LIBRARY_PATH

# 复制库文件并设置权限
COPY lib/ /app/lib/
RUN chmod 755 /app/lib/*.so* && \
    cd /app/lib && \
    ln -sf libv08.so libv08.so.1 && \
    ldconfig /app/lib

# 复制其他文件
COPY wxapi_linux_v1_0_5 /app/
COPY 08sae.dat /app/
COPY rqtx.dat /app/
COPY conf/ /app/conf/
COPY swagger/ /app/swagger/
COPY start.sh /app/

# 设置可执行权限
RUN chmod +x /app/wxapi_linux_v1_0_5 && \
    chmod +x /app/start.sh

# 暴露端口
EXPOSE 8059

# 运行应用
CMD ["/app/start.sh"] 