$ExtensionRoot = Resolve-Path "$PSScriptRoot/../.."
& uv run --script "$ExtensionRoot/scripts/python/delivery.py" @args
exit $LASTEXITCODE
