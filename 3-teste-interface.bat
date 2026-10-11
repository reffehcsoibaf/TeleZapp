@echo off
setlocal EnableExtensions EnableDelayedExpansion

rem ============================================================
rem  TESTE DA INTERFACE (PROTOTIPO COM DADOS DE EXEMPLO)
rem  Gera o arquivo: logs\resultado-teste-interface.log
rem  Precisa de prototipo_interface.py, modelo_conversas.py, fala.py
rem  e acessivel.py na mesma pasta. Nao usa contas nem envia nada.
rem ============================================================

set "BASE=%~dp0"
set "VENV=%BASE%venv-interface"
set "LOGDIR=%BASE%logs"
set "LOG=%LOGDIR%\resultado-teste-interface.log"
set "PYCMD="

if not exist "%LOGDIR%" mkdir "%LOGDIR%"
if exist "%LOG%" del "%LOG%"

call :log ==== TESTE DA INTERFACE ====
call :log Inicio: %DATE% %TIME%

for %%A in (prototipo_interface.py modelo_conversas.py fala.py acessivel.py) do (
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

call :log ---------------- ETAPA 2: pip install wxPython ----------------
>>"%LOG%" echo Saida do pip a seguir:
call :now T1
>>"%LOG%" 2>&1 "%VPY%" -m pip install --disable-pip-version-check wxPython
set "RC=!ERRORLEVEL!"
call :now T2
call :elapsed !T1! !T2! "pip install wxPython"
call :log Codigo de saida do pip: !RC!
if not "!RC!"=="0" goto :fim

call :log ---------------- ETAPA 3: pip install accessible-output2 ----------------
call :log So para obter a DLL de fala do NVDA, sem as dependencias do pacote.
call :now T1
>>"%LOG%" 2>&1 "%VPY%" -m pip install --disable-pip-version-check --no-deps accessible-output2
set "RC=!ERRORLEVEL!"
call :now T2
call :elapsed !T1! !T2! "pip install accessible-output2"
call :log Codigo de saida do pip: !RC!
>>"%LOG%" 2>&1 "%VPY%" -m pip list --disable-pip-version-check

call :log ---------------- ETAPA 4: prototipo da interface ----------------
call :log A janela do prototipo vai abrir. Use o NVDA normalmente. Feche com Control Q.
"%VPY%" "%BASE%prototipo_interface.py" "%LOG%"
set "RC=!ERRORLEVEL!"
call :log Codigo de saida do prototipo: !RC!

:fim
call :log Fim: %DATE% %TIME%
start "" explorer /select,"%LOG%"
if defined PYCMD (
  if exist "%BASE%acessivel.py" %PYCMD% "%BASE%acessivel.py" fim interface
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
