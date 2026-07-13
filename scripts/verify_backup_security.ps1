param(
    [Parameter(Mandatory = $true)]
    [string]$BackupDirectory
)

$ErrorActionPreference = 'Stop'
$repositoryRoot = (Get-Item -LiteralPath (Join-Path $PSScriptRoot '..')).FullName
$backupRoot = [IO.Path]::GetFullPath($BackupDirectory)
if ($backupRoot.StartsWith($repositoryRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw 'BackupDirectory must be outside the repository root.'
}
if (-not (Test-Path -LiteralPath $backupRoot -PathType Container)) {
    throw 'BackupDirectory must already exist.'
}

$broadPrincipals = @('Everyone', 'BUILTIN\Users', 'Authenticated Users', 'Users')
$unsafeRules = Get-Acl -LiteralPath $backupRoot |
    Select-Object -ExpandProperty Access |
    Where-Object {
        $_.AccessControlType -eq 'Allow' -and
        $broadPrincipals -contains $_.IdentityReference.Value
    }
if ($unsafeRules) {
    throw 'BackupDirectory grants a broad principal access; restrict the ACL before backup use.'
}

Write-Output 'backup_security_verified=true'
