@echo off
setlocal EnableExtensions EnableDelayedExpansion

rem ============================================================
rem  TESTE DE VELOCIDADE NO TELEGRAM (4 JEITOS DE ENVIAR E BAIXAR)
rem  Gera: logs\resultado-teste-velocidade-telegram.log
rem  Precisa de telegram_velocidade.py, telegram_login.py,
rem  arquivos_grandes.py e acessivel.py na mesma pasta.
rem  O tamanho do arquivo fica em configuracao-arquivos-grandes.txt
rem  (padrao 20 MB; o minimo usado aqui e 11 MB).
rem ============================================================

set "BASE=%~dp0"
set "VENV=%BASE%venv-velocidade-telegram"
set "LOGDIR=%BASE%logs"
set "LOG=%LOGDIR%\resultado-teste-velocidade-telegram.log"
set "PYCMD="

if not exist "%LOGDIR%" mkdir "%LOGDIR%"
if exist "%LOG%" del "%LOG%"

call :log ==== TESTE DE VELOCIDADE NO TELEGRAM ====
call :log Inicio: %DATE% %TIME%

for %%A in (telegram_velocidade.py telegram_login.py arquivos_grandes.py acessivel.py) do (
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

call :log ---------------- ETAPA 2: pip install telethon cryptg ----------------
call :now T1
>>"%LOG%" 2>&1 "%VPY%" -m pip install --disable-pip-version-check telethon cryptg
set "RC=!ERRORLEVEL!"
call :now T2
call :elapsed !T1! !T2! "pip install telethon cryptg"
call :log Codigo de saida do pip: !RC!
if not "!RC!"=="0" goto :fim

call :log ---------------- ETAPA 3: as 4 variantes ----------------
call :log Cada variante envia e baixa o arquivo. Dois bipes marcam o fim de cada uma.
call :now T1
"%VPY%" "%BASE%telegram_velocidade.py" "%LOG%"
set "RC=!ERRORLEVEL!"
call :now T2
call :elapsed !T1! !T2! "teste de velocidade"
call :log Codigo de saida do teste: !RC!

:fim
call :log Fim: %DATE% %TIME%
start "" explorer /select,"%LOG%"
if defined PYCMD (
  if exist "%BASE%acessivel.py" %PYCMD% "%BASE%acessivel.py" fim velocidade-telegram
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
