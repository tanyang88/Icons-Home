# Icons Home - 上传服务镜像
# 纯 Python 标准库，零第三方依赖

FROM python:3.12-slim

WORKDIR /app

# 复制项目文件（.dockerignore 已排除运行时数据 data/ 等）
COPY . .

EXPOSE 8000

# 容器内固定监听 0.0.0.0:8000，对外端口由 docker-compose / nginx 决定
CMD ["python", "upload_server.py", "--host", "0.0.0.0", "--port", "8000"]
