@echo off
setlocal EnableExtensions EnableDelayedExpansion

rem ============================================================
rem  TESTE DE EMPACOTAMENTO (PYINSTALLER)
rem  Gera: logs\resultado-teste-empacotamento.log
rem  Cria um executavel com wxPython, neonize, Telethon, hachoir e a
rem  fala do NVDA, mede tamanho e tempo de partida e roda um autoteste.
rem  Precisa de app_empacotamento.py, medir_pasta.py, fala.py,
rem  amostras.py e acessivel.py na mesma pasta. Nao usa contas nem
rem  internet alem do pip. Demora alguns minutos.
rem ============================================================

set "BASE=%~dp0"
set "VENV=%BASE%venv-empacotamento"
set "SAIDA=%BASE%empacotado"
set "TRABALHO=%BASE%build-pyinstaller"
set "EXE=%SAIDA%\TeleZappTeste\TeleZappTeste.exe"
set "LOGDIR=%BASE%logs"
set "LOG=%LOGDIR%\resultado-teste-empacotamento.log"
set "PYILOG=%LOGDIR%\pyinstaller-saida.log"
set "PYCMD="

if not exist "%LOGDIR%" mkdir "%LOGDIR%"
if exist "%LOG%" del "%LOG%"

call :log ==== TESTE DE EMPACOTAMENTO ====
call :log Inicio: %DATE% %TIME%

for %%A in (app_empacotamento.py medir_pasta.py fala.py amostras.py acessivel.py) do (
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

call :log ---------------- ETAPA 2: instalar pacotes ----------------
call :now T1
>>"%LOG%" 2>&1 "%VPY%" -m pip install --disable-pip-version-check wxPython neonize telethon hachoir pyinstaller
set "RC=!ERRORLEVEL!"
call :now T2
call :elapsed !T1! !T2! "pip install dos pacotes"
call :log Codigo de saida do pip: !RC!
if not "!RC!"=="0" goto :fim
>>"%LOG%" 2>&1 "%VPY%" -m pip install --disable-pip-version-check --no-deps accessible-output2
>>"%LOG%" 2>&1 "%VPY%" -m pip list --disable-pip-version-check

call :log ---------------- ETAPA 3: autoteste como script, sem empacotar ----------------
call :now T1
"%VPY%" "%BASE%app_empacotamento.py" --autoteste "%LOG%"
set "RC=!ERRORLEVEL!"
call :now T2
call :elapsed !T1! !T2! "autoteste como script"
call :log Falhas no autoteste como script: !RC!

call :log ---------------- ETAPA 4: PyInstaller ----------------
call :log A saida completa fica em logs\pyinstaller-saida.log. Pode demorar.
if exist "%SAIDA%" rmdir /s /q "%SAIDA%"
if exist "%TRABALHO%" rmdir /s /q "%TRABALHO%"
call :now T1
>"%PYILOG%" 2>&1 "%VPY%" -m PyInstaller --noconfirm --clean --onedir --console --name TeleZappTeste --distpath "%SAIDA%" --workpath "%TRABALHO%" --specpath "%TRABALHO%" --collect-all neonize --collect-all magic --collect-all accessible_output2 --collect-submodules telethon --collect-submodules hachoir "%BASE%app_empacotamento.py"
set "RC=!ERRORLEVEL!"
call :now T2
call :elapsed !T1! !T2! "PyInstaller"
call :log Codigo de saida do PyInstaller: !RC!
>>"%LOG%" echo Linhas importantes da saida do PyInstaller:
>>"%LOG%" findstr /c:"ERROR" /c:"completed successfully" /c:"PyInstaller:" "%PYILOG%"
for /f %%n in ('findstr /c:"WARNING" "%PYILOG%" ^| find /c /v ""') do call :log Avisos do PyInstaller: %%n

if not exist "%EXE%" (
  call :log ERRO: o executavel nao foi gerado. Se o PyInstaller terminou sem erro, o antivirus pode ter bloqueado ou apagado o arquivo.
  goto :fim
)
call :log Executavel gerado.
"%VPY%" "%BASE%medir_pasta.py" "%SAIDA%\TeleZappTeste" "%LOG%"

call :log ---------------- ETAPA 5: executavel empacotado, 1a execucao ----------------
call :now T1
"%EXE%" --autoteste "%LOG%"
set "RC=!ERRORLEVEL!"
call :now T2
call :elapsed !T1! !T2! "1a execucao do executavel"
call :log Falhas no autoteste do executavel: !RC!
if not exist "%EXE%" call :log AVISO: o executavel sumiu depois de rodar. Possivel quarentena do antivirus.

call :log ---------------- ETAPA 6: executavel empacotado, 2a execucao ----------------
call :now T1
"%EXE%" --autoteste "%LOG%"
set "RC=!ERRORLEVEL!"
call :now T2
call :elapsed !T1! !T2! "2a execucao do executavel"
call :log Falhas no autoteste do executavel: !RC!

:fim
call :log Fim: %DATE% %TIME%
start "" explorer /select,"%LOG%"
if defined PYCMD (
  if exist "%BASE%acessivel.py" %PYCMD% "%BASE%acessivel.py" fim empacotamento
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
