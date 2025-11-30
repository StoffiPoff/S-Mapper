# PS1 helper to start the S-Mapper app from a developer environment
# Usage: ./scripts/run_app.ps1
# Prefer the virtualenv interpreter when present; PowerShell 5.1 doesn't
# support the C-style ternary operator, so use a regular if/else branch.
if ($env:VIRTUAL_ENV -and $env:VIRTUAL_ENV.Trim() -ne '') {
	$python = "$env:VIRTUAL_ENV\Scripts\python.exe"
} else {
	$python = "python"
}

& $python -m s_mapper.app
