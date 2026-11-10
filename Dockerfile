FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

RUN useradd --create-home --uid 1000 aqua && mkdir -p /app/data/raw && chown -R aqua /app
USER aqua

EXPOSE 8000
CMD ["uvicorn", "aqua_foresight.api.main:app_factory", "--factory", "--host", "0.0.0.0", "--port", "8000"]
