@echo off
setlocal
set "PYTHONPATH=D:\ExplainLab\backend;%PYTHONPATH%"
if "%EXPLAINLAB_API_URL%"=="" set "EXPLAINLAB_API_URL=http://127.0.0.1:8000"
"D:\ExplainLab\.venv\Scripts\python.exe" -m app.mcp_server
