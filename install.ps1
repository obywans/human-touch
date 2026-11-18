# HumanTouch installer for Windows (PowerShell 5.1 or 7). Installs the skill so its command is /human.
#   powershell -ExecutionPolicy Bypass -File install.ps1 [-Claude] [-Agents] [-GeminiCommand]
# One clone lives in %USERPROFILE%\.human-touch; each host gets a directory junction (no admin needed).
# Nothing existing is overwritten. Default: -Claude -Agents.
param([switch]$Claude, [switch]$Agents, [switch]$GeminiCommand)
$ErrorActionPreference = 'Stop'
$h = if ($env:USERPROFILE) { $env:USERPROFILE } else { $HOME }
$clone = if ($env:HUMAN_TOUCH_HOME) { $env:HUMAN_TOUCH_HOME } else { Join-Path $h '.human-touch' }
$repo  = if ($env:HUMAN_TOUCH_REPO) { $env:HUMAN_TOUCH_REPO } else { 'https://github.com/obywans/human-touch' }
if (-not ($Claude -or $Agents -or $GeminiCommand)) { $Claude = $true; $Agents = $true }
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw 'git is required' }
if (Test-Path (Join-Path $clone '.git')) { git -C $clone pull --ff-only -q; if ($LASTEXITCODE) { throw "could not update $clone" } }
elseif (Test-Path $clone) { throw "$clone exists and is not a HumanTouch clone; set HUMAN_TOUCH_HOME" }
else { git clone -q $repo $clone; if ($LASTEXITCODE) { throw 'git clone failed' } }
$skill = Join-Path $clone 'skills\human'
function Link($target) {
  New-Item -ItemType Directory -Force -Path (Split-Path $target) | Out-Null
  if (Test-Path $target) { Write-Warning "SKIPPED: $target already exists (not touched). Move it away and run again."; return }
  New-Item -ItemType Junction -Path $target -Target $skill | Out-Null
  Write-Host "installed: $target -> $skill"
}
if ($Claude) { Link (Join-Path $h '.claude\skills\human') }
if ($Agents) { Link (Join-Path $h '.agents\skills\human') }
if ($GeminiCommand) {
  $f = Join-Path $h '.gemini\commands\human.toml'
  New-Item -ItemType Directory -Force -Path (Split-Path $f) | Out-Null
  if (Test-Path $f) { Write-Warning "SKIPPED: $f already exists (not touched)." }
  else {
    $toml = 'description = "HumanTouch: improve prose, clean invisible Unicode, inspect metadata, audit watermarks"' + "`n" + 'prompt = """Use the human skill (HumanTouch) on this request: {{args}}"""' + "`n"
    [IO.File]::WriteAllText($f, $toml, (New-Object Text.UTF8Encoding($false)))
    Write-Host "installed: $f"
  }
}
Write-Host ("HumanTouch " + (Get-Content (Join-Path $skill 'VERSION') -Raw).Trim() + ". Update later with: git -C `"$clone`" pull")
