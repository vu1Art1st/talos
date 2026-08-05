FROM python:3.12-slim

# 使用国内 PyPI 镜像源加速依赖下载，避免官方源在构建时下载缓慢。
# 可在构建时通过 --build-arg PIP_INDEX_URL=xxx 覆盖；常用镜像：
#   清华大学  https://pypi.tuna.tsinghua.edu.cn/simple
#   阿里云    https://mirrors.aliyun.com/pypi/simple
#   中科大    https://pypi.mirrors.ustc.edu.cn/simple
ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
RUN printf '[global]\nindex-url = %s\n' "${PIP_INDEX_URL}" > /etc/pip.conf

# LibreOffice：仅当 ENABLE_LIBREOFFICE=1 时安装（报告目录域自动更新）。
# 使用 Debian 的 -nogui 最小包（无图形界面 / 无 Java 集成），配合中文字体与
# 等宽替代字体，2 核 2G 服务器可按需冷启动、用后即退，不常驻内存。
ARG ENABLE_LIBREOFFICE=0
RUN if [ "${ENABLE_LIBREOFFICE}" = "1" ]; then \
        apt-get update && apt-get install -y --no-install-recommends \
            libreoffice-writer-nogui \
            fonts-noto-cjk \
            fonts-liberation \
        && rm -rf /var/lib/apt/lists/*; \
    fi

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 以非 root 用户运行，降低容器逃逸风险；预建 storage 目录并归属该用户，
# 命名卷挂载到 /app/storage 时会继承此目录的属主，保证可写。
RUN useradd --create-home --uid 10001 app \
    && mkdir -p /app/storage \
    && chown -R app:app /app
USER app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
