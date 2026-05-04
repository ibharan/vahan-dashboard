# setup_task_scheduler.ps1
# Registers a Windows Task Scheduler job to run the VAHAN pipeline daily at 8 AM IST (2:30 AM UTC)
# Run as Administrator: Right-click PowerShell → "Run as Administrator", then execute this script.

$PythonPath = (Get-Command python).Source
$ScriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
$ScriptPath = Join-Path $ScriptDir "scheduler.py"
$LogPath    = Join-Path $ScriptDir "logs\task_scheduler.log"

$Action = New-ScheduledTaskAction `
    -Execute $PythonPath `
    -Argument "`"$ScriptPath`" --now >> `"$LogPath`" 2>&1" `
    -WorkingDirectory $ScriptDir

# 8:00 AM IST = 2:30 AM UTC
$Trigger = New-ScheduledTaskTrigger -Daily -At "02:30AM"

$Settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
    -RestartCount 2 `
    -RestartInterval (New-TimeSpan -Minutes 10) `
    -StartWhenAvailable

Register-ScheduledTask `
    -TaskName "VAHAN_2Wheeler_Daily_Scrape" `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Description "Daily VAHAN 2-wheeler scrape for Amazon Automotive GL dashboard" `
    -RunLevel Highest `
    -Force

Write-Host "Task registered: VAHAN_2Wheeler_Daily_Scrape" -ForegroundColor Green
Write-Host "Runs daily at 2:30 AM UTC (8:00 AM IST)" -ForegroundColor Cyan
Write-Host "To run immediately: schtasks /run /tn VAHAN_2Wheeler_Daily_Scrape"
