@echo off
cd /d c:\python_projects\self_study

REM 가상환경이 있으면 활성화
if exist venv\Scripts\activate.bat (
    call venv\Scripts\activate.bat
)

python app.py >> logs\app.log 2>&1
