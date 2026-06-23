@echo off
cd /d "D:\Projects-D\s2connects AI Voice bot\scaiva"
set DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5433/postgres
set REDIS_URL=redis://:redissecret@localhost:6379
set ENVIRONMENT=local
set LOG_LEVEL=DEBUG
set BACKEND_API_ENDPOINT=http://localhost:8000
set UI_APP_URL=http://localhost:3010
set MINIO_ENDPOINT=localhost:9000
set MINIO_PUBLIC_ENDPOINT=http://localhost:9000
set MINIO_ACCESS_KEY=minioadmin
set MINIO_SECRET_KEY=minioadmin
set MINIO_BUCKET=voice-audio
set MINIO_SECURE=false
set TURN_HOST=localhost
set TURN_SECRET=dograh-turn-secret-change-in-production
".\venv\Scripts\python.exe" -m uvicorn api.app:app --host 0.0.0.0 --port 8000
pause
