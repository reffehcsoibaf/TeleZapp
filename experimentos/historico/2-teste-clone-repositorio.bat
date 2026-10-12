@echo off
setlocal EnableExtensions EnableDelayedExpansion

rem ============================================================
rem  TESTE OPCIONAL: INSTALAR A PARTIR DO REPOSITORIO CLONADO
rem  Mede o clone e o npm install (que inclui a compilacao do
rem  projeto), sem baixar o Chromium, para isolar esse custo.
rem  Gera o arquivo: logs\resultado-teste-clone.log
rem ============================================================

set "BASE=%~dp0"
set "REPO=%BASE%repo-wppconnect"
set "NPMCACHE=%BASE%cache-npm-teste-clone"
set "PPTRCACHE=%BASE%cache-puppeteer-teste-clone"
set "LOGDIR=%BASE%logs"
set "LOG=%LOGDIR%\resultado-teste-clone.log"

if not exist "%LOGDIR%" mkdir "%LOGDIR%"
if exist "%LOG%" del "%LOG%"

call :log ==== TESTE DE INSTALACAO PELO REPOSITORIO CLONADO ====
call :log Inicio: %DATE% %TIME%

where node >nul 2>&1
if errorlevel 1 goto :semfer
where npm >nul 2>&1
if errorlevel 1 goto :semfer
where git >nul 2>&1
if errorlevel 1 goto :semgit

>>"%LOG%" echo Versao do Node:
>>"%LOG%" 2>&1 call node -v
>>"%LOG%" echo Versao do npm:
>>"%LOG%" 2>&1 call npm -v
>>"%LOG%" echo Versao do git:
>>"%LOG%" 2>&1 git --version

if exist "%REPO%" rmdir /s /q "%REPO%"
if exist "%NPMCACHE%" rmdir /s /q "%NPMCACHE%"
if exist "%PPTRCACHE%" rmdir /s /q "%PPTRCACHE%"

call :log ---------------- ETAPA 1: git clone ----------------
call :now T1
>>"%LOG%" 2>&1 git clone --depth 1 https://github.com/wppconnect-team/wppconnect.git "%REPO%"
set "RC=!ERRORLEVEL!"
call :now T2
call :elapsed !T1! !T2! CLONE
if not "!RC!"=="0" (
  call :log ERRO no clone. Veja a saida acima no log.
  goto :fim
)

call :log ---------------- ETAPA 2: npm install no repositorio ----------------
set "PUPPETEER_CACHE_DIR=%PPTRCACHE%"
set "PUPPETEER_SKIP_DOWNLOAD=true"
set "PUPPETEER_SKIP_CHROMIUM_DOWNLOAD=true"
pushd "%REPO%"
>>"%LOG%" echo Saida do npm install a seguir:
call :now T1
>>"%LOG%" 2>&1 call npm install --cache "%NPMCACHE%" --foreground-scripts
set "RC=!ERRORLEVEL!"
call :now T2
popd
call :elapsed !T1! !T2! INSTALL

if exist "%REPO%\dist" (call :log Pasta dist existe: a compilacao foi feita) else (call :log Pasta dist NAO existe: a compilacao nao foi feita ou falhou)

call :log ==================== RESUMO ====================
call :log Clone: !SUM_CLONE!
call :log npm install no repositorio, sem Chromium: !SUM_INSTALL!
goto :fim

:semfer
call :log ERRO: node ou npm nao encontrado. Instale o Node.js e rode de novo.
goto :fim

:semgit
call :log ERRO: git nao encontrado. Instale o Git ou pule este teste.
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
set "MSG=!SEG!,!CS! segundos no total, cerca de !MIN! min !SS! s. Codigo de saida: !RC!"
call :log RESULTADO: !MSG!
set "SUM_%~3=!MSG!"
exit /b
