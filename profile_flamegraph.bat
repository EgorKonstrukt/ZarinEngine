@echo off
py-spy record -o profile_flamegraph.svg --subprocesses -- python main.py
echo.
echo Flamegraph saved to profile_flamegraph.svg
pause
