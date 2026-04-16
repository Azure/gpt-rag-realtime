# Stage 1: Serve the built app with a static file server
FROM python:3.12-slim AS production-stage

COPY . .

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN python -m pip install -r requirements.txt

RUN python -m pip install gunicorn

CMD ["python3", "-m", "gunicorn", "app:create_app", "-b", "0.0.0.0:8080", "--worker-class", "aiohttp.GunicornWebWorker"]