FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    PYTHONUTF8=1

WORKDIR /app
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# 程式與 data.db 都不放進映像檔：docker-compose 把這個資料夾掛載到 /app，
# 改了程式只要重新啟動容器就會生效，不用重建
EXPOSE 8003
CMD ["python", "watch_and_serve.py"]
