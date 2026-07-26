FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

RUN sed -i 's|deb.debian.org|mirrors.cloud.tencent.com|g; s|security.debian.org|mirrors.cloud.tencent.com|g' \
        /etc/apt/sources.list.d/debian.sources \
    && apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl libmagic1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -i https://mirrors.cloud.tencent.com/pypi/simple --upgrade pip \
    && pip install -i https://mirrors.cloud.tencent.com/pypi/simple \
        -r requirements.txt

COPY . .
EXPOSE 5000
CMD ["gunicorn", "--workers", "1", "--threads", "8", "--worker-class", "gthread", "--timeout", "900", "--bind", "127.0.0.1:5000", "app.http.app:app"]



