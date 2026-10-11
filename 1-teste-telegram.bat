@echo off
setlocal EnableExtensions EnableDelayedExpansion

rem ============================================================
rem  TESTE DO TELEGRAM COM TELETHON
rem  Gera o arquivo: logs\resultado-teste-telegram.log
rem  Precisa de telegram_teste.py, acessivel.py e amostras.py na mesma pasta.
rem  Nao exige ler nem digitar no terminal: avisos saem em caixas de mensagem
rem ============================================================

set "BASE=%~dp0"
set "VENV=%BASE%venv-telegram"
set "LOGDIR=%BASE%logs"
set "LOG=%LOGDIR%\resultado-teste-telegram.log"
set "PYCMD="

if not exist "%LOGDIR%" mkdir "%LOGDIR%"
if exist "%LOG%" del "%LOG%"

call :log ==== TESTE DO TELEGRAM COM TELETHON ====
call :log Inicio: %DATE% %TIME%

if not exist "%BASE%telegram_teste.py" (
  call :log ERRO: telegram_teste.py nao foi encontrado nesta pasta.
  goto :fim
)
if not exist "%BASE%acessivel.py" (
  call :log ERRO: acessivel.py nao foi encontrado nesta pasta.
  goto :fim
)
if not exist "%BASE%amostras.py" (
  call :log ERRO: amostras.py nao foi encontrado nesta pasta.
  goto :fim
)

rem Escolhe o Python
py -3.13 --version >nul 2>&1
if not errorlevel 1 set "PYCMD=py -3.13"
if not defined PYCMD (
  python --version >nul 2>&1
  if not errorlevel 1 set "PYCMD=python"
)
if not defined PYCMD (
  call :log ERRO: Python nao encontrado. Instale o Python e rode de novo.
  goto :fim
)

call :log Comando Python usado: %PYCMD%
>>"%LOG%" 2>&1 %PYCMD% --version

call :log ---------------- ETAPA 1: ambiente virtual ----------------
if exist "%VENV%" rmdir /s /q "%VENV%"
call :now T1
>>"%LOG%" 2>&1 %PYCMD% -m venv "%VENV%"
call :now T2
call :elapsed !T1! !T2! "criar ambiente virtual"

set "VPY=%VENV%\Scripts\python.exe"
if not exist "%VPY%" (
  call :log ERRO: o ambiente virtual nao foi criado.
  goto :fim
)

call :log ---------------- ETAPA 2: pip install telethon hachoir ----------------
>>"%LOG%" echo Saida do pip a seguir:
call :now T1
>>"%LOG%" 2>&1 "%VPY%" -m pip install --disable-pip-version-check telethon hachoir
set "RC=!ERRORLEVEL!"
call :now T2
call :elapsed !T1! !T2! "pip install telethon hachoir"
call :log Codigo de saida do pip: !RC!
if not "!RC!"=="0" goto :fim
>>"%LOG%" 2>&1 "%VPY%" -m pip list --disable-pip-version-check

call :log ---------------- ETAPA 3: teste com avisos e Bloco de Notas ----------------
call :log Siga as caixas de mensagem. O leitor de tela le cada uma.
"%VPY%" "%BASE%telegram_teste.py" "%LOG%"
set "RC=!ERRORLEVEL!"
call :log Codigo de saida do teste: !RC!

:fim
call :log Fim: %DATE% %TIME%
start "" explorer /select,"%LOG%"
if defined PYCMD (
  if exist "%BASE%acessivel.py" %PYCMD% "%BASE%acessivel.py" fim telegram
)
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
call :log TEMPO %~3: !SEG!,!CS! segundos
exit /b
