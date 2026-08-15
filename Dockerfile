FROM python:3.12-slim-bookworm

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

RUN apt-get update && apt-get install -y \
    pkg-config \
    default-libmysqlclient-dev \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt /app/
# Ensure all backend requirements are resolved
RUN python -m pip install --no-cache-dir --upgrade pip setuptools wheel \
    && python -m pip install --no-cache-dir -r requirements.txt \
    && python -m pip install --no-cache-dir "gunicorn>=22,<24"

COPY backend/ /app/
COPY docker/entrypoint.sh /usr/local/bin/nuboxed-entrypoint
RUN chmod +x /usr/local/bin/nuboxed-entrypoint

EXPOSE 8000

ENTRYPOINT ["/usr/local/bin/nuboxed-entrypoint"]
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "3", "config.wsgi:application"]
