# Pigeon - the app that runs on whatever envless hands it.
#
# It carries no configuration of its own beyond where envless is and the token
# proving which environment it may read, so both arrive as environment
# variables rather than being baked in.

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py config_client.py integration_test.py ./
COPY templates ./templates

RUN useradd --create-home --uid 10001 pigeon \
    && chown -R pigeon:pigeon /app
USER pigeon

EXPOSE 8100

# Healthy means it reached envless and has a configuration to run on. Without
# one it is up but has nothing to do.
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
    CMD python -c "import urllib.request,sys,json; \
d=json.load(urllib.request.urlopen('http://127.0.0.1:8100/health', timeout=4)); \
sys.exit(0 if d.get('configured') else 1)"

CMD ["python", "app.py"]
