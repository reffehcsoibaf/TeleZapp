@echo off
setlocal EnableExtensions EnableDelayedExpansion

rem ============================================================
rem  TESTE DE CHAMADA DE VOZ DO WHATSAPP (meowcaller sobre o hypermeow)
rem  Gera: logs\resultado-teste-chamada-whatsapp.log
rem  Precisa de chamada_whatsapp.py, fala.py, acessivel.py e do
rem  programa em Go: 10-chamada-whatsapp-meowcaller\chamadas-teste.exe
rem  Usa uma CONTA DE TESTE, pareada como aparelho conectado (codigo
rem  de telefone). Liga para alguem ou espera uma chamada por 45
rem  segundos e mede se a voz passa nos dois sentidos. Use fones de
rem  ouvido e avise a outra pessoa. Nao usa o terminal: siga as
rem  caixas de mensagem e os bipes.
rem ============================================================

set "BASE=%~dp0"
set "VENV=%BASE%venv-chamada-whatsapp"
set "LOGDIR=%BASE%logs"
set "LOG=%LOGDIR%\resultado-teste-chamada-whatsapp.log"
set "PYCMD="
set "RC=1"

if not exist "%LOGDIR%" mkdir "%LOGDIR%"
if exist "%LOG%" del "%LOG%"

call :log ==== TESTE DE CHAMADA DE VOZ DO WHATSAPP ====
call :log Inicio: %DATE% %TIME%

for %%A in (chamada_whatsapp.py fala.py acessivel.py) do (
  if not exist "%BASE%%%A" (
    call :log ERRO: %%A nao foi encontrado nesta pasta.
    goto :fim
  )
)
if not exist "%BASE%10-chamada-whatsapp-meowcaller\chamadas-teste.exe" (
  call :log ERRO: falta 10-chamada-whatsapp-meowcaller\chamadas-teste.exe
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

call :log ---------------- ETAPA 2: instalar sounddevice e numpy ----------------
call :now T1
>>"%LOG%" 2>&1 "%VPY%" -m pip install --disable-pip-version-check sounddevice numpy
set "RC=!ERRORLEVEL!"
call :now T2
call :elapsed !T1! !T2! "pip install sounddevice numpy"
call :log Codigo de saida do pip: !RC!
if not "!RC!"=="0" goto :fim
>>"%LOG%" 2>&1 "%VPY%" -m pip install --disable-pip-version-check --no-deps accessible-output2
>>"%LOG%" 2>&1 "%VPY%" -m pip list --disable-pip-version-check

call :log ---------------- ETAPA 3: chamada de voz ----------------
call :log Use fones de ouvido. Siga as caixas de mensagem.
"%VPY%" "%BASE%chamada_whatsapp.py" "%LOG%"
set "RC=!ERRORLEVEL!"
call :log Codigo de saida do teste: !RC!

:fim
call :log Fim: %DATE% %TIME%
start "" explorer /select,"%LOG%"
if defined PYCMD (
  if exist "%BASE%acessivel.py" %PYCMD% "%BASE%acessivel.py" fim chamada-whatsapp !RC!
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
