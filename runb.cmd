
@echo off
setlocal
rem ---------------------------------------------------------------------------
rem  runb.cmd
rem  Primero build.cmd; si termina sin errores, ejecuta run.cmd.
rem  Si el build falla NO se ejecuta la aplicacion.
rem  Los argumentos se pasan a run.cmd, p. ej.:  runb.cmd --debug
rem ---------------------------------------------------------------------------

cd /d "%~dp0"

rem Evita que build.cmd / run.cmd pausen por su cuenta: la pausa la hace este.
set "NOPAUSE=1"

call "%~dp0build.cmd"
if errorlevel 1 (
    echo.
    echo [runb] El build fallo: no se ejecuta la aplicacion.
    goto :fail
)

call "%~dp0run.cmd" %*
if errorlevel 1 goto :fail
exit /b 0

:fail
echo.
rem Si se abrio con doble clic, se pausa para poder leer el error.
echo %cmdcmdline% | find /i "/c" >nul && pause
exit /b 1
