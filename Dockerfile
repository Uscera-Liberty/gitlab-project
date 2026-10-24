# syntax=docker/dockerfile:1

# ---------- Stage 1: builder — ставим зависимости в изолированный venv ----------
FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /src
# Сначала только requirements — этот слой берётся из кэша, пока зависимости не менялись
COPY requirements.txt .
RUN pip install -r requirements.txt

# ---------- Stage 2: test — линтер и тесты внутри сборки ----------
FROM builder AS test

COPY requirements-dev.txt .
RUN pip install -r requirements-dev.txt

COPY pyproject.toml .
COPY app ./app
COPY tests ./tests
RUN ruff check . && ruff format --check . && pytest -q -p no:cacheprovider

# ---------- Stage 3: runtime — финальный минимальный образ ----------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    DB_PATH=/data/users.db

# Непривилегированный пользователь — контейнер не работает от root
RUN groupadd --system app && useradd --system --gid app --no-create-home app \
    && mkdir /data && chown app:app /data

WORKDIR /app
# Из builder забираем только готовый venv, из контекста — только код приложения
COPY --from=builder /opt/venv /opt/venv
COPY app ./app

USER app
VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
