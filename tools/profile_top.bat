@echo off
cd /d "%~dp0.."
echo Live profiling. Press Ctrl+C to stop.
py-spy top --subprocesses -- python main.py
pause
