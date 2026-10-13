
@echo off
setlocal
rem ---------------------------------------------------------------------------
rem  run.cmd
rem  Ejecuta la aplicacion (pywebview). No compila nada: usa lo que haya en
rem  dist_ui\. Los argumentos se pasan a main.py, p. ej.:  run.cmd --debug
rem ---------------------------------------------------------------------------

cd /d "%~dp0"

if not exist "dist_ui\index.html" (
    echo [run] ERROR: no existe dist_ui\index.html. Ejecuta build.cmd primero ^(o usa runb.cmd^).
    goto :fail
)

rem Python: primero el .venv del proyecto, despues el launcher "py", despues "python"
set "PY="
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if not defined PY (
    where py >nul 2>&1
    if not errorlevel 1 set "PY=py"
)
if not defined PY (
    where python >nul 2>&1
    if not errorlevel 1 set "PY=python"
)
if not defined PY (
    echo [run] ERROR: no se encontro Python ^(.venv, py ni python^).
    goto :fail
)

"%PY%" main.py %*
if errorlevel 1 (
    echo.
    echo [run] La aplicacion termino con errores.
    goto :fail
)
exit /b 0

:fail
echo.
rem Si se abrio con doble clic, se pausa para poder leer el error.
rem (runb.cmd define NOPAUSE y es quien se encarga de la pausa)
if defined NOPAUSE exit /b 1
echo %cmdcmdline% | find /i "/c" >nul && pause
exit /b 1
