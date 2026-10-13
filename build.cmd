
@echo off
setlocal
rem ---------------------------------------------------------------------------
rem  build.cmd
rem  Compila el frontend (Svelte + Vite + Tailwind) hacia dist_ui\ para que
rem  pywebview lo cargue. Termina con errorlevel 0 si todo salio bien y con 1
rem  si algo fallo (asi runb.cmd sabe si puede continuar).
rem ---------------------------------------------------------------------------

where npm >nul 2>&1
if errorlevel 1 (
    echo [build] ERROR: npm no esta en el PATH. Instala Node.js ^(https://nodejs.org^).
    goto :fail
)

pushd "%~dp0frontend" 2>nul
if errorlevel 1 (
    echo [build] ERROR: no existe la carpeta "%~dp0frontend".
    goto :fail
)

if not exist "node_modules" (
    echo [build] Primera vez: instalando dependencias con npm install...
    call npm install --ignore-scripts --no-audit --no-fund
    if errorlevel 1 (
        echo [build] ERROR: npm install fallo.
        popd
        goto :fail
    )
)

echo [build] Compilando el frontend con vite...
call npm run build
if errorlevel 1 (
    echo [build] ERROR: npm run build fallo.
    popd
    goto :fail
)
popd

echo [build] OK - frontend compilado en "%~dp0dist_ui"
exit /b 0

:fail
echo.
rem Si se abrio con doble clic, se pausa para poder leer el error.
rem (runb.cmd define NOPAUSE y es quien se encarga de la pausa)
if defined NOPAUSE exit /b 1
echo %cmdcmdline% | find /i "/c" >nul && pause
exit /b 1
