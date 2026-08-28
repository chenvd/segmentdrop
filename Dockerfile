FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && addgroup --system segmentdrop \
    && adduser --system --ingroup segmentdrop segmentdrop \
    && mkdir -p /app/data \
    && chown segmentdrop:segmentdrop /app/data

COPY --chown=segmentdrop:segmentdrop app ./app
COPY --chown=segmentdrop:segmentdrop static ./static
COPY --chown=segmentdrop:segmentdrop templates ./templates

USER segmentdrop
EXPOSE 8000
VOLUME ["/app/data"]
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-access-log"]
