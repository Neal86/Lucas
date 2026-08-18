FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    GWC_HOST=0.0.0.0 \
    GWC_PORT=8787 \
    GWC_DATA_DIR=/data

WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir .

VOLUME ["/data"]
EXPOSE 8787
CMD ["gwc-gateway"]
