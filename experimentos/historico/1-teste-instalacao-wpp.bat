@echo off
setlocal EnableExtensions EnableDelayedExpansion

rem ============================================================
rem  TESTE DE TEMPO DE INSTALACAO DO WPPCONNECT
rem  Gera o arquivo: logs\resultado-teste-instalacao.log
rem  Rode com duplo clique e espere aparecer a mensagem final.
rem ============================================================

set "BASE=%~dp0"
set "WORK=%BASE%teste-wpp"
set "NPMCACHE=%BASE%cache-npm-teste"
set "PPTRCACHE=%BASE%cache-puppeteer-teste"
set "LOGDIR=%BASE%logs"
set "LOG=%LOGDIR%\resultado-teste-instalacao.log"

if not exist "%LOGDIR%" mkdir "%LOGDIR%"
if exist "%LOG%" del "%LOG%"

call :log ==== TESTE DE INSTALACAO DO WPPCONNECT ====
call :log Inicio: %DATE% %TIME%
call :log Pasta do teste: %BASE%

where node >nul 2>&1
if errorlevel 1 goto :semnode
where npm >nul 2>&1
if errorlevel 1 goto :semnode

call :log ---------------- AMBIENTE ----------------
>>"%LOG%" ver
>>"%LOG%" echo Versao do Node:
>>"%LOG%" 2>&1 call node -v
>>"%LOG%" echo Versao do npm:
>>"%LOG%" 2>&1 call npm -v
>>"%LOG%" echo Registro do npm:
>>"%LOG%" 2>&1 call npm config get registry
>>"%LOG%" echo Cache global do npm:
>>"%LOG%" 2>&1 call npm config get cache
>>"%LOG%" echo Caminho do node:
>>"%LOG%" 2>&1 where node

set "EDGE1=%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"
set "EDGE2=%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"
set "EDGEOK=nao"
if exist "%EDGE1%" set "EDGEOK=sim, em Program Files x86"
if exist "%EDGE2%" set "EDGEOK=sim, em Program Files"
call :log Microsoft Edge encontrado: %EDGEOK%

rem Comeca do zero: apaga caches usados somente por este teste
if exist "%NPMCACHE%" rmdir /s /q "%NPMCACHE%"
if exist "%PPTRCACHE%" rmdir /s /q "%PPTRCACHE%"

call :rodar "TESTE A - sem baixar Chromium, cache do npm vazio" 1 A
call :rodar "TESTE B - COM download do Chromium, cache do npm ja preenchido" 0 B
call :rodar "TESTE C - sem baixar Chromium, cache do npm ja preenchido" 1 C

call :log ==================== RESUMO ====================
call :log A, sem Chromium e cache vazio: !SUM_A!
call :log B, com Chromium e cache cheio: !SUM_B!
call :log C, sem Chromium e cache cheio: !SUM_C!
call :log Comparacao justa do Chromium: B contra C.
goto :fim

:semnode
call :log ERRO: node ou npm nao encontrado. Instale o Node.js e rode de novo.
goto :fim

:fim
call :log Fim: %DATE% %TIME%
echo(
echo Pronto. Envie este arquivo de log:
echo %LOG%
echo(
pause
endlocal
exit /b

rem ------------------------------------------------------------
rem  Sub-rotinas
rem ------------------------------------------------------------

:log
echo(%*
>>"%LOG%" echo(%*
exit /b

:now
set "TT=%TIME: =0%"
set /a "%~1=(1!TT:~0,2!-100)*360000+(1!TT:~3,2!-100)*6000+(1!TT:~6,2!-100)*100+(1!TT:~9,2!-100)"
exit /b

:elapsed
set /a "D=%~2-%~1"
if !D! lss 0 set /a "D+=8640000"
set /a "SEG=D/100, CS=D%%100"
set "CS=0!CS!"
set "CS=!CS:~-2!"
set /a "MIN=SEG/60, SS=SEG%%60"
set "MSG=!SEG!,!CS! segundos no total, cerca de !MIN! min !SS! s. Codigo de saida do npm: !RC!"
call :log RESULTADO: !MSG!
set "SUM_%~3=!MSG!"
exit /b

:rodar
set "TITULO=%~1"
set "SKIP=%~2"
set "ID=%~3"
call :log ------------------------------------------------
call :log %TITULO%
call :log ------------------------------------------------
if exist "%WORK%" rmdir /s /q "%WORK%"
mkdir "%WORK%"
if exist "%PPTRCACHE%" rmdir /s /q "%PPTRCACHE%"
set "PUPPETEER_CACHE_DIR=%PPTRCACHE%"
if "%SKIP%"=="1" (
  set "PUPPETEER_SKIP_DOWNLOAD=true"
  set "PUPPETEER_SKIP_CHROMIUM_DOWNLOAD=true"
) else (
  set "PUPPETEER_SKIP_DOWNLOAD="
  set "PUPPETEER_SKIP_CHROMIUM_DOWNLOAD="
)
pushd "%WORK%"
call npm init -y >nul 2>&1
>>"%LOG%" echo Saida do npm install a seguir:
call :now T1
>>"%LOG%" 2>&1 call npm install @wppconnect-team/wppconnect --cache "%NPMCACHE%" --foreground-scripts
set "RC=!ERRORLEVEL!"
call :now T2
popd
call :elapsed !T1! !T2! %ID%
if exist "%PPTRCACHE%\chrome" (call :log Chromium foi baixado nesta rodada: SIM) else (call :log Chromium foi baixado nesta rodada: NAO)
set "NPASTAS=0"
if exist "%WORK%\node_modules" for /f %%n in ('dir /ad /b "%WORK%\node_modules" ^| find /c /v ""') do set "NPASTAS=%%n"
call :log Pastas de primeiro nivel em node_modules: !NPASTAS!
exit /b
