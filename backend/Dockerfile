FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY tests ./tests
COPY alembic.ini .
COPY alembic ./alembic
COPY docker-entrypoint.sh .

RUN chmod +x docker-entrypoint.sh

ENV PYTHONPATH=/app
EXPOSE 8000

ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
