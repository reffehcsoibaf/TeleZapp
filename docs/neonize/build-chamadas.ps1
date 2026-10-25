<#
  Recompila a DLL do neonize OFFLINE.  Uso:  .\build.ps1 -Variante teste|chamadas
  Saida: saida\<variante>\ (DLL + 7 arquivos .py + SHA256SUMS.txt). Veja LEIAME.md.
#>
param([Parameter(Mandatory)][ValidateSet('teste','chamadas')][string]$Variante)
$ErrorActionPreference = 'Stop'
$raiz = $PSScriptRoot
$env:PATH = "$raiz\toolchain\go\bin;C:\msys64\ucrt64\bin;$env:PATH"
$env:GOPATH = "$raiz\gopath"
$env:GOCACHE = "$raiz\gocache"
$env:GOTOOLCHAIN = 'local'
$env:GOFLAGS = '-mod=mod'
$env:GOPROXY = 'off'
$env:GOSUMDB = 'off'
$env:CGO_ENABLED = '1'

$repo = "$raiz\neonize"
$trab = "$raiz\work\$Variante"
$ramaBase = 'feat/group-request-participants'

# worktree de trabalho limpo na ponta da branch (a raiz de work\ e recriada pelo git)
if (-not (Test-Path $trab)) { git -C $repo worktree add --detach $trab $ramaBase | Out-Null }
git -C $trab -c core.autocrlf=false checkout -q -f --detach $ramaBase
git -C $trab -c core.autocrlf=false checkout-index -a -f
git -C $trab clean -q -fdx

# go.mod/go.sum fixos da variante (replace do whatsmeow local e, nas chamadas, do meowcaller)
Copy-Item "$raiz\fontes\$Variante\go.mod","$raiz\fontes\$Variante\go.sum" "$trab\goneonize\" -Force

if ($Variante -eq 'chamadas') {
    Copy-Item "$raiz\fontes\chamadas\calls.go" "$trab\goneonize\calls.go" -Force
    $p = "$trab\goneonize\main.go"
    $s = [IO.File]::ReadAllText($p)
    $s = [regex]::Replace($s, '(\t\tdelete\(clients, C\.GoString\(id\)\)\r?\n)', '$1' + "`t`tremoverChamadas(C.GoString(id))`n", 1)
    $s = [regex]::Replace($s, '(\tclients\[uuid\] = client\r?\n)', '$1' + "`tinstalarChamadas(uuid)`n", 1)
    if (($s -split 'removerChamadas').Count -ne 2 -or ($s -split 'instalarChamadas').Count -ne 2) { throw 'ganchos de chamadas nao aplicados' }
    # banco de sessao: espera ate 30 s por trava e usa WAL (sem isso, com muita escrita ao
    # mesmo tempo, o whatsmeow falha com "database is locked": ligacoes e mensagens perdidas)
    $dsn = 'file:%s?_foreign_keys=on'
    $dsnNovo = 'file:%s?_foreign_keys=on&_journal_mode=WAL&_busy_timeout=30000&_synchronous=NORMAL&_txlock=immediate'
    if (-not $s.Contains($dsn)) { throw 'DSN do sqlite nao encontrado' }
    $s = $s.Replace($dsn, $dsnNovo)
    [IO.File]::WriteAllText($p, $s)
}

$saida = "$raiz\saida\$Variante"
New-Item -ItemType Directory -Force "$saida\aioze","$saida\proto" | Out-Null
Push-Location "$trab\goneonize"
try {
    go build -buildmode=c-shared -ldflags=-s -o "$saida\neonize-windows-amd64.dll" .
    if ($LASTEXITCODE) { throw "go build falhou ($LASTEXITCODE)" }
} finally { Pop-Location }
Remove-Item "$saida\neonize-windows-amd64.h" -ErrorAction SilentlyContinue

$py = "$trab\neonize"
foreach ($f in 'client.py','_binder.py','events.py','aioze\events.py','proto\Neonize_pb2.py','proto\Neonize_pb2.pyi') {
    Copy-Item "$py\$f" "$saida\$f" -Force
}
# protobufs gerados pelo protoc sao LF; o checkout no Windows os converte para CRLF
foreach ($f in 'proto\Neonize_pb2.py','proto\Neonize_pb2.pyi') {
    $t = [IO.File]::ReadAllText("$saida\$f").Replace("`r`n","`n")
    [IO.File]::WriteAllText("$saida\$f", $t, (New-Object Text.UTF8Encoding($false)))
}
$linhas = foreach ($f in 'neonize-windows-amd64.dll','client.py','_binder.py','events.py','aioze\events.py','proto\Neonize_pb2.py','proto\Neonize_pb2.pyi') {
    $h = (Get-FileHash "$saida\$f" -Algorithm SHA256).Hash.ToLower()
    "$h *$($f.Replace([string][char]92,'/'))"
}
[IO.File]::WriteAllLines("$saida\SHA256SUMS.txt", $linhas)
Get-Content "$saida\SHA256SUMS.txt"
