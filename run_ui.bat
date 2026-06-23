@echo off
cd /d "D:\Projects-D\s2connects AI Voice bot\scaiva\ui"
set BACKEND_URL=http://localhost:8000
set NEXT_PUBLIC_API_URL=http://localhost:8000
"C:\Program Files\Volta\pnpm.exe" run dev
pause
