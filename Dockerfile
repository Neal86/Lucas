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
    && node --check src/gpt_windows_connector/browser_bridge_extension/background.js \
    && node --check src/gpt_windows_connector/browser_bridge_extension/content.js \
    && pytest -q tests/test_dashboard_js_syntax.py tests/test_dashboard_routes.py tests/test_dashboard_script_boundaries.py tests/test_operation_accounting.py tests/test_security_approval_details.py tests/test_web_landing_brand_contract.py tests/test_deployment_healthcheck.py tests/test_ixbrowser_bridge.py tests/test_browser_handoff.py tests/test_browser_background_contract.py tests/test_browser_profile_registry.py tests/test_browser_bridge_extension.py tests/test_browser_router.py
RUN touch /quality-ok

FROM python:3.12-slim
COPY --from=quality /quality-ok /tmp/quality-ok
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

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
