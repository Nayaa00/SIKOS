FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY requirements.lock ./
RUN pip install --no-cache-dir --timeout 120 -r requirements.lock && useradd --create-home sikos
COPY --chown=sikos:sikos app ./app
USER sikos
EXPOSE 8000
CMD ["sh", "-c", "python -m app.cli init-db && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-proxy-headers"]
