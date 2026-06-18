@echo off
set "OUTFILE=profile_flamegraph_%DATE:~-4,4%%DATE:~-7,2%%DATE:~-10,2%_%TIME:~0,2%%TIME:~3,2%%TIME:~6,2%.svg"
set "OUTFILE=%OUTFILE: =0%"
echo Recording to %OUTFILE% ...
echo Close the Zarin Engine window when done.
py-spy record -o "%OUTFILE%" --subprocesses --duration 30 -- python main.py
echo.
echo Saved: %OUTFILE%
pause
