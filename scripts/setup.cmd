@echo off
REM All the logic lives in setup.py - Python runs the same everywhere,
REM so it can be tested once and trusted on every machine.
python "%~dp0setup.py" %*
if errorlevel 1 pause
