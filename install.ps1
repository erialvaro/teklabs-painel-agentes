# Instalador do Painel de Agentes · TekLabs Digital (Windows)
# Criado por Erick Álvaro da Silva · TekLabs Digital
# Uso: powershell -ExecutionPolicy Bypass -File .\install.ps1 [opções do instalar.py]
$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent $MyInvocation.MyCommand.Path

function Testar-Python($cmd, $extra) {
    # Devolve o caminho do executável se for Python 3.9+; o atalho da Microsoft Store não conta.
    try {
        $saida = & $cmd @extra --version 2>$null
        if ($LASTEXITCODE -ne 0 -or -not ($saida -match 'Python (\d+)\.(\d+)')) { return $null }
        if ([int]$Matches[1] -lt 3 -or ([int]$Matches[1] -eq 3 -and [int]$Matches[2] -lt 9)) { return $null }
        $caminho = & $cmd @extra -c "import sys; print(sys.executable)" 2>$null
        if ($LASTEXITCODE -eq 0 -and $caminho) { return $caminho.Trim() }
    } catch { }
    return $null
}

$python = $null
foreach ($c in @(@('py', @('-3')), @('python3', @()), @('python', @()))) {
    if (Get-Command $c[0] -ErrorAction SilentlyContinue) {
        $python = Testar-Python $c[0] $c[1]
        if ($python) { break }
    }
}
if (-not $python -and (Get-Command uv -ErrorAction SilentlyContinue)) {
    try { $p = (& uv python find 2>$null); if ($p) { $python = Testar-Python $p.Trim() @() } } catch { }
}
if (-not $python) {
    Write-Host "Python 3.9 ou mais novo não foi encontrado."
    Write-Host "Instale com:  winget install Python.Python.3.12   e rode este instalador de novo."
    exit 1
}
Write-Host "Usando Python: $python"
& $python (Join-Path $raiz "instalar.py") @args
exit $LASTEXITCODE
