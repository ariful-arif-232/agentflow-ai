# AgentFlow AI — API container (FastAPI + ML engine).
# Data generation + training run at build time so the container starts in seconds.
FROM python:3.11-slim@sha256:bab1b7ef4b450c81002278d035eff85ebe394ae94df904f7a3ba14f7e16e487b

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /srv

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ml ./ml
COPY apps/api ./apps/api
RUN python ml/scripts/generate_data.py > /dev/null \
 && python ml/scripts/train.py \
 && rm -rf /root/.cache

RUN useradd --create-home --uid 10001 agentflow && chown -R agentflow /srv
USER agentflow

WORKDIR /srv/apps/api
ENV PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers 1"]
