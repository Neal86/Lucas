FROM python:3.12-slim AS quality

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY . /app
RUN apt-get update \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir -e ".[dev]"
RUN python -m compileall -q src \
    && pytest -q tests/test_dashboard_js_syntax.py tests/test_dashboard_routes.py tests/test_operation_accounting.py
RUN touch /quality-ok

FROM python:3.12-slim
COPY --from=quality /quality-ok /tmp/quality-ok

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
