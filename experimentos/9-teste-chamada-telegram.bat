@echo off
setlocal EnableExtensions EnableDelayedExpansion

rem ============================================================
rem  TESTE DE CHAMADA DE VOZ 1 A 1 NO TELEGRAM (py-tgcalls)
rem  Gera: logs\resultado-teste-chamada-telegram.log
rem  Precisa de chamada_telegram.py, fala.py, acessivel.py e
rem  telegram_login.py na mesma pasta. Liga para uma pessoa ou
rem  espera uma chamada, por 45 segundos, e mede se a voz passa e
rem  quanto custa. Use fones de ouvido e avise a outra pessoa.
rem  Nao usa o terminal: siga as caixas de mensagem e bipes.
rem ============================================================

set "BASE=%~dp0"
set "VENV=%BASE%venv-chamada-telegram"
set "LOGDIR=%BASE%logs"
set "LOG=%LOGDIR%\resultado-teste-chamada-telegram.log"
set "PYCMD="

if not exist "%LOGDIR%" mkdir "%LOGDIR%"
if exist "%LOG%" del "%LOG%"

call :log ==== TESTE DE CHAMADA DE VOZ NO TELEGRAM ====
call :log Inicio: %DATE% %TIME%

for %%A in (chamada_telegram.py fala.py acessivel.py telegram_login.py) do (
  if not exist "%BASE%%%A" (
    call :log ERRO: %%A nao foi encontrado nesta pasta.
    goto :fim
  )
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

call :log ---------------- ETAPA 2: instalar py-tgcalls ----------------
call :now T1
>>"%LOG%" 2>&1 "%VPY%" -m pip install --disable-pip-version-check py-tgcalls telethon cryptg
set "RC=!ERRORLEVEL!"
call :now T2
call :elapsed !T1! !T2! "pip install do py-tgcalls"
call :log Codigo de saida do pip: !RC!
if not "!RC!"=="0" goto :fim
>>"%LOG%" 2>&1 "%VPY%" -m pip install --disable-pip-version-check --no-deps accessible-output2
>>"%LOG%" 2>&1 "%VPY%" -m pip list --disable-pip-version-check
call :log Tamanho do ambiente virtual:
"%VPY%" "%BASE%medir_pasta.py" "%VENV%" "%LOG%"

call :log ---------------- ETAPA 3: chamada de voz ----------------
call :log Use fones de ouvido. Siga as caixas de mensagem.
"%VPY%" "%BASE%chamada_telegram.py" "%LOG%"
set "RC=!ERRORLEVEL!"
call :log Codigo de saida do teste: !RC!

:fim
call :log Fim: %DATE% %TIME%
start "" explorer /select,"%LOG%"
if defined PYCMD (
  if exist "%BASE%acessivel.py" %PYCMD% "%BASE%acessivel.py" fim chamada-telegram
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
set /a "MIN=SEG/60, SS=SEG%%60"
call :log TEMPO %~3: !SEG!,!CS! segundos, cerca de !MIN! min !SS! s
exit /b
