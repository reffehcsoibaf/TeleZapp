@echo off
setlocal EnableExtensions EnableDelayedExpansion

rem ============================================================
rem  INICIAR O TELEZAPP
rem  Na primeira vez (ou quando os componentes mudarem) cria o
rem  ambiente na pasta venv e instala o necessario. Depois abre o
rem  TeleZapp sem janela de terminal.
rem  Log: %APPDATA%\TeleZapp\logs\iniciar.log
rem ============================================================

set "BASE=%~dp0"
set "RAIZ=%BASE:~0,-1%"
set "VENV=%BASE%venv"
set "LOGDIR=%APPDATA%\TeleZapp\logs"
set "LOG=%LOGDIR%\iniciar.log"
set "PYCMD="

if not exist "%LOGDIR%" mkdir "%LOGDIR%"
>"%LOG%" echo ==== iniciar-telezapp %DATE% %TIME% ====
cd /d "%RAIZ%"

py -3.13 --version >nul 2>&1
if not errorlevel 1 set "PYCMD=py -3.13"
if not defined PYCMD (
  python --version >nul 2>&1
  if not errorlevel 1 set "PYCMD=python"
)
if not defined PYCMD (
  >>"%LOG%" echo ERRO: Python nao encontrado. Instale o Python 3.13.
  start "" notepad "%LOG%"
  goto :fim
)
>>"%LOG%" echo Python: %PYCMD%
>>"%LOG%" 2>&1 %PYCMD% --version

if not exist "%VENV%\Scripts\python.exe" (
  >>"%LOG%" echo Criando o ambiente em venv...
  >>"%LOG%" 2>&1 %PYCMD% -m venv "%VENV%"
  if not exist "%VENV%\Scripts\python.exe" (
    >>"%LOG%" echo ERRO: o ambiente nao foi criado.
    %PYCMD% "%BASE%ferramentas\aviso.py" erro-ambiente
    start "" explorer "%LOGDIR%"
    goto :fim
  )
)

set "VPY=%VENV%\Scripts\python.exe"
fc /b "%BASE%requirements.txt" "%VENV%\requirements-instalado.txt" >nul 2>&1
if errorlevel 1 (
  >>"%LOG%" echo Instalando componentes...
  "%VPY%" "%BASE%ferramentas\aviso.py" instalando
  >>"%LOG%" 2>&1 "%VPY%" -m pip install --disable-pip-version-check -r "%BASE%requirements.txt"
  if errorlevel 1 (
    >>"%LOG%" echo ERRO: a instalacao falhou.
    "%VPY%" "%BASE%ferramentas\aviso.py" erro-instalacao
    start "" explorer "%LOGDIR%"
    goto :fim
  )
  >>"%LOG%" 2>&1 "%VPY%" -m pip install --disable-pip-version-check --no-deps accessible-output2
  copy /y "%BASE%requirements.txt" "%VENV%\requirements-instalado.txt" >nul
  >>"%LOG%" echo Componentes instalados.
)

>>"%LOG%" 2>&1 "%VPY%" -m pip list --disable-pip-version-check
>>"%LOG%" echo Abrindo o TeleZapp: %DATE% %TIME%
start "" "%VENV%\Scripts\pythonw.exe" -m telezapp

:fim
endlocal
exit /b
