@echo off
REM Starts Redis (Celery's broker + result backend) via Docker.
REM Requires Docker Desktop to be installed and running first.
docker compose up -d redis
docker compose ps
