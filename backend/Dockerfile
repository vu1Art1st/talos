FROM python:3.12-slim

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
