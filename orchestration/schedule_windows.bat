@echo off
REM ============================================================
REM AtmoSync – Windows Task Scheduler Setup
REM ============================================================
REM Run this batch file as Administrator to register a Windows
REM Task Scheduler job that runs the AtmoSync pipeline every
REM 5 minutes automatically.
REM
REM Usage: Right-click > Run as Administrator
REM ============================================================

SET PYTHON=C:\Python314\python.exe
SET SCRIPT=C:\Users\HP\Documents\GitHub\Atomsync\orchestration\pipeline_runner.py
SET TASK_NAME=AtmoSync_Pipeline

echo Creating Windows Task Scheduler job: %TASK_NAME%

schtasks /create ^
  /tn "%TASK_NAME%" ^
  /tr "\"%PYTHON%\" \"%SCRIPT%\" --once" ^
  /sc minute ^
  /mo 5 ^
  /ru SYSTEM ^
  /f

IF %ERRORLEVEL% EQU 0 (
    echo.
    echo SUCCESS: Task "%TASK_NAME%" created.
    echo The pipeline will run every 5 minutes automatically.
    echo.
    echo To view:   schtasks /query /tn "%TASK_NAME%"
    echo To delete: schtasks /delete /tn "%TASK_NAME%" /f
    echo To run now: schtasks /run /tn "%TASK_NAME%"
) ELSE (
    echo.
    echo ERROR: Failed to create task. Try running as Administrator.
)

pause
