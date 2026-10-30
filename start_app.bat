@echo off
rem Startet die Gelaendeschnitte-App. Optional: Projektdatei (.gsproj) als Argument.
rem Python von python.org verwenden (dort sind PySide6, pyvista, ezdxf installiert), nicht die Store-Version.
cd /d "%~dp0"
set "PY=%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
if not exist "%PY%" set "PY=python"
"%PY%" main.py %*
if errorlevel 1 pause
