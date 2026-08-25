param(
    [Parameter(Position = 0)]
    [ValidateSet("deploy", "deploy-restart", "restart", "status", "logs", "help")]
    [string]$Action = "help",

    [Parameter(Position = 1, ValueFromRemainingArguments = $true)]
    [string[]]$Message
)

$ErrorActionPreference = "Stop"
$ProjectDirectory = $PSScriptRoot
$Server = "sorrowingbot@192.225.219.189"
$ServerBotDirectory = "/home/sorrowingbot/Bot"
$Service = "sorrowingbot"
$HostingKey = Join-Path $env:USERPROFILE ".ssh\id_ed25519_bot_hosting"
$DeployKey = "/home/sorrowingbot/.ssh/github_sorrowing_bot"
$SshArguments = @(
    "-o", "IdentitiesOnly=yes",
    "-i", $HostingKey
)

function Show-Usage {
    Write-Host ""
    Write-Host "Sorrowing bot commands:"
    Write-Host '  .\bot deploy "message"          Push and pull code; reload an existing cog yourself.'
    Write-Host '  .\bot deploy-restart "message"  Push, pull, install dependencies, and restart.'
    Write-Host '  .\bot restart                  Restart the hosted bot.'
    Write-Host '  .\bot status                   Show whether the hosted bot is running.'
    Write-Host '  .\bot logs                     Show the latest hosted bot logs.'
    Write-Host ""
}

function Assert-LastCommand([string]$Description) {
    if ($LASTEXITCODE -ne 0) {
        throw "$Description failed with exit code $LASTEXITCODE."
    }
}

function Invoke-Server([string]$Command, [switch]$Interactive) {
    $arguments = @($SshArguments)
    if ($Interactive) {
        $arguments += "-t"
    }
    $arguments += @($Server, $Command)
    & ssh @arguments
    Assert-LastCommand "Server command"
}

function Publish-Code {
    $commitMessage = ($Message -join " ").Trim()
    if (-not $commitMessage) {
        throw 'Add a short update message, for example: .\bot deploy "Improve moderation"'
    }

    Set-Location $ProjectDirectory
    & git add -A
    Assert-LastCommand "Staging changes"

    & git diff --cached --quiet
    if ($LASTEXITCODE -eq 0) {
        Write-Host "No local changes to commit. Checking the server for updates..."
    }
    elseif ($LASTEXITCODE -eq 1) {
        & git commit -m $commitMessage
        Assert-LastCommand "Creating commit"
        & git push
        Assert-LastCommand "Pushing to GitHub"
    }
    else {
        Assert-LastCommand "Checking staged changes"
    }

    $pull = "cd $ServerBotDirectory && GIT_SSH_COMMAND='ssh -o IdentitiesOnly=yes -i $DeployKey' git pull --ff-only"
    Invoke-Server $pull
}

switch ($Action) {
    "deploy" {
        Publish-Code
        Write-Host "Code deployed. You can now reload the changed existing cog in Discord."
    }
    "deploy-restart" {
        Publish-Code
        $command = "cd $ServerBotDirectory && .venv/bin/python -m pip install -r requirements.txt && sudo systemctl restart $Service && sudo systemctl status $Service --no-pager"
        Invoke-Server $command -Interactive
    }
    "restart" {
        Invoke-Server "sudo systemctl restart $Service && sudo systemctl status $Service --no-pager" -Interactive
    }
    "status" {
        Invoke-Server "sudo systemctl status $Service --no-pager" -Interactive
    }
    "logs" {
        Invoke-Server "sudo journalctl -u $Service -n 50 --no-pager" -Interactive
    }
    default {
        Show-Usage
    }
}
