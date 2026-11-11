# Windows helper (no make needed):  .\scripts\tasks.ps1 dev | test | eval | doctor
param([Parameter(Mandatory = $true)][ValidateSet("install", "dev", "test", "eval", "doctor")][string]$Task)
$root = Split-Path $PSScriptRoot -Parent
switch ($Task) {
  "install" { Push-Location "$root\backend"; uv sync --extra ml --extra ocr; Pop-Location; Push-Location "$root\frontend"; npm install; Pop-Location }
  "dev" {
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root\backend'; uv run kavra serve"
    Push-Location "$root\frontend"; npm run dev; Pop-Location
  }
  "test" { Push-Location "$root\backend"; uv run pytest -q; Pop-Location; Push-Location "$root\frontend"; npm test; Pop-Location }
  "eval" { Push-Location "$root\backend"; uv run python ..\eval\run.py --update-readme; Pop-Location }
  "doctor" { Push-Location "$root\backend"; uv run kavra doctor; Pop-Location }
}
