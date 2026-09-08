# The envless API.
#
#   docker build -t envless-api ./backend
#   docker run --rm -p 8000:8000 \
#     -e DATABASE_URL=postgresql+psycopg://postgres:kali@host.docker.internal:5432/envless \
#     -e ENVLESS_MASTER_KEY=... envless-api
#
# Tables are created on startup, so a fresh database needs no extra step.

FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dependencies are their own layer, so editing the source does not reinstall
# them. psycopg ships binary wheels, so no compiler is needed here.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY seed.py smoke_test.py guard_test.py rotation_demo.py ./

# Nothing here needs root. /pigeon is created here on purpose: a named volume
# mounted there takes its ownership from the image, so seed.py can write the
# token it issues without this container needing to be root.
RUN useradd --create-home --uid 10001 envless \
    && mkdir -p /pigeon \
    && chown -R envless:envless /app /pigeon
USER envless

EXPOSE 8000

# /health reports whether Postgres is reachable, which is what "ready" means
# for this service - the API is useless without it.
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
    CMD python -c "import urllib.request,sys,json; \
d=json.load(urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)); \
sys.exit(0 if d.get('database') == 'connected' else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
