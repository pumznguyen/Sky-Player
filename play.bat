@echo off
where uv >nul 2>nul
if %ERRORLEVEL% equ 0 (
    uv run python src/main.py %*
) else (
    python src/main.py %*
)
