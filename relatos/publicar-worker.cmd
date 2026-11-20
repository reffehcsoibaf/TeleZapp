@echo off
rem Publica o Worker do TeleZapp (relatos e informacoes de uso) na Cloudflare.
rem Grava tudo em C:\logs\publicar-worker.txt. Rode com um duplo clique.
rem (Sem blocos com parenteses: o PATH do Windows tem "(x86)" e quebraria.)
setlocal
if not exist C:\logs mkdir C:\logs
set "LOG=C:\logs\publicar-worker.txt"
cd /d "%~dp0"
echo === %date% %time% === > "%LOG%"
where npx >nul 2>&1
if not errorlevel 1 goto temnode
if exist "C:\github\WinZapp_Python\client\node\npx.cmd" set "PATH=C:\github\WinZapp_Python\client\node;%PATH%"
:temnode
where npx >> "%LOG%" 2>&1
if errorlevel 1 goto semnode
echo. >> "%LOG%"
echo --- quem esta logado na Cloudflare --- >> "%LOG%"
call npx --yes wrangler whoami >> "%LOG%" 2>&1
echo. >> "%LOG%"
echo --- publicando; se der erro de sintaxe, o Worker antigo continua no ar --- >> "%LOG%"
call npx --yes wrangler deploy >> "%LOG%" 2>&1
set "RESULTADO=%errorlevel%"
echo. >> "%LOG%"
echo --- segredos configurados, so os nomes; precisam existir ADMIN_TOKEN e SAL --- >> "%LOG%"
call npx --yes wrangler secret list >> "%LOG%" 2>&1
echo. >> "%LOG%"
echo Codigo de saida da publicacao: %RESULTADO% >> "%LOG%"
type "%LOG%"
echo.
echo Resultado gravado em %LOG%
pause
exit /b %RESULTADO%
:semnode
echo ERRO: o Node.js nao foi encontrado neste computador. >> "%LOG%"
type "%LOG%"
pause
exit /b 1
