<#
.SYNOPSIS
  Installs the Claude Code mods in this folder on Windows and registers them in your
  user settings.json. Safe to run more than once.

.DESCRIPTION
  1. Copies each mod folder that sits next to this script into %USERPROFILE%\.claude\mods\
  2. Backs up %USERPROFILE%\.claude\settings.json (settings.json.bak-<date>)
  3. Adds the mod folders to "env" -> "CLAUDE_CODE_PLUGIN_DIRS", keeping everything else
     in the file (and any other plugin folders already listed) unchanged

  Run from a PowerShell window in the unzipped claude-mods folder:
    powershell -ExecutionPolicy Bypass -File .\install-windows.ps1
  Preview without changing anything:
    powershell -ExecutionPolicy Bypass -File .\install-windows.ps1 -DryRun

.PARAMETER Mods
  Which mods to install. Defaults to all of them. If a status-band folder is next to this
  script or already in the mods folder, it is loaded in place of usage-meter and turn-timer
  (it combines both), and those two are taken out of settings.json.

.PARAMETER DryRun
  Show what would change without copying files or writing settings.json.
#>
param(
  [string[]]$Mods = @('usage-meter', 'activity-pane', 'turn-timer', 'task-board', 'agents-panel'),
  [switch]$DryRun
)

$ErrorActionPreference = 'Stop'

# Windows PowerShell 5.1 (the one built into Windows 10) otherwise writes arrays as {"value": [...], "Count": n}.
if ($PSVersionTable.PSVersion.Major -lt 6) { Remove-TypeData System.Array -ErrorAction SilentlyContinue }

$claudeDir = if ($env:CLAUDE_CONFIG_DIR) { $env:CLAUDE_CONFIG_DIR } else { Join-Path $env:USERPROFILE '.claude' }
$modsDir = Join-Path $claudeDir 'mods'
$settingsPath = Join-Path $claudeDir 'settings.json'
$sourceDir = $PSScriptRoot

function Test-ModFolder([string]$path) {
  Test-Path (Join-Path (Join-Path $path '.claude-plugin') 'plugin.json')
}

# status-band combines usage-meter and turn-timer: when it is available, load it instead of those two.
$Combined = @('usage-meter', 'turn-timer')
$hasStatusBand = (Test-ModFolder (Join-Path $sourceDir 'status-band')) -or (Test-ModFolder (Join-Path $modsDir 'status-band'))
if ($hasStatusBand -and -not $PSBoundParameters.ContainsKey('Mods')) {
  $Mods = @('status-band') + @($Mods | Where-Object { $Combined -notcontains $_ })
}
$Retired = if ($Mods -contains 'status-band') { $Combined } else { @() }

Write-Host "Claude config folder: $claudeDir"
Write-Host "Mods folder:          $modsDir"
Write-Host ''

# 1. Copy mods and work out the folder each one loads from.
$modPaths = @()
foreach ($mod in $Mods) {
  $source = Join-Path $sourceDir $mod
  $target = Join-Path $modsDir $mod

  if (Test-ModFolder $source) {
    if ($DryRun) {
      Write-Host "[dry run] would copy $mod -> $target"
    } else {
      New-Item -ItemType Directory -Force -Path $modsDir | Out-Null
      Copy-Item -Recurse -Force -Path $source -Destination $modsDir
      Write-Host "Copied   $mod -> $target"
    }
  }

  # An unzip tool sometimes adds an extra level (mods\usage-meter\usage-meter\...).
  $nested = Join-Path $target $mod
  if ((Test-ModFolder $target) -or ($DryRun -and (Test-ModFolder $source))) {
    $modPaths += $target
  } elseif (Test-ModFolder $nested) {
    Write-Host "Note     $mod is one folder too deep; using $nested" -ForegroundColor Yellow
    $modPaths += $nested
  } else {
    Write-Host "Skipped  $mod (not found next to this script or in $modsDir)" -ForegroundColor Yellow
  }
}

if ($modPaths.Count -eq 0) {
  Write-Host ''
  Write-Host 'No mods found, settings.json left unchanged.' -ForegroundColor Red
  exit 1
}

# 2. Read settings.json (or start a new one).
$settings = New-Object PSObject
if (Test-Path $settingsPath) {
  $raw = [IO.File]::ReadAllText($settingsPath).TrimStart([char]0xFEFF)
  if ($raw.Trim()) {
    try {
      $settings = $raw | ConvertFrom-Json
    } catch {
      Write-Host ''
      Write-Host "settings.json is not valid JSON, so it was left unchanged:" -ForegroundColor Red
      Write-Host "  $settingsPath"
      Write-Host "  $($_.Exception.Message)"
      Write-Host 'Fix the file (or paste it to Claude to fix), then run this script again.'
      exit 1
    }
  }
}

if (-not $settings.PSObject.Properties['env']) {
  $settings | Add-Member -NotePropertyName env -NotePropertyValue (New-Object PSObject)
}

# 3. Merge with any plugin folders already listed, dropping duplicates and stale entries for these mods.
$existing = @()
if ($settings.env.PSObject.Properties['CLAUDE_CODE_PLUGIN_DIRS']) {
  $existing = @("$($settings.env.CLAUDE_CODE_PLUGIN_DIRS)" -split ';' | ForEach-Object { $_.Trim() } | Where-Object { $_ })
}
$ours = $modPaths | ForEach-Object { $_.TrimEnd('\', '/') }
# Also drops mods that status-band replaces, so they are not loaded twice.
$names = @($Mods) + @($Retired) | ForEach-Object { $_.ToLower() }
$kept = @($existing | Where-Object {
  $leaf = (Split-Path $_.TrimEnd('\', '/') -Leaf).ToLower()
  -not ($names -contains $leaf)
})
$all = @()
foreach ($dir in ($kept + $ours)) {
  if (-not ($all | Where-Object { $_ -ieq $dir })) { $all += $dir }
}
$newValue = $all -join ';'
$oldValue = if ($existing.Count) { $existing -join ';' } else { '(not set)' }

if ($settings.env.PSObject.Properties['CLAUDE_CODE_PLUGIN_DIRS']) {
  $settings.env.CLAUDE_CODE_PLUGIN_DIRS = $newValue
} else {
  $settings.env | Add-Member -NotePropertyName CLAUDE_CODE_PLUGIN_DIRS -NotePropertyValue $newValue
}

$json = $settings | ConvertTo-Json -Depth 100

Write-Host ''
Write-Host 'CLAUDE_CODE_PLUGIN_DIRS'
Write-Host "  before: $oldValue"
Write-Host "  after:  $newValue"

if ($DryRun) {
  Write-Host ''
  Write-Host '[dry run] settings.json would become:'
  Write-Host $json
  exit 0
}

# 4. Back up, then write without a byte-order mark (Claude Code reads plain UTF-8).
New-Item -ItemType Directory -Force -Path $claudeDir | Out-Null
if (Test-Path $settingsPath) {
  $backup = "$settingsPath.bak-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
  Copy-Item $settingsPath $backup
  Write-Host ''
  Write-Host "Backup:  $backup"
}
[IO.File]::WriteAllText($settingsPath, $json, (New-Object Text.UTF8Encoding($false)))
Write-Host "Updated: $settingsPath"
Write-Host ''
Write-Host 'Done. Close VS Code completely and reopen it (or restart claude) to load the mods.' -ForegroundColor Green
