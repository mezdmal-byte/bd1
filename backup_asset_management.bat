@echo off
REM Создание резервной копии проекта asset_management

REM Путь к скрипту бэкапа
set SCRIPT_DIR=%~dp0
set BACKUP_PS=%SCRIPT_DIR%backup_asset_management.ps1

echo Запуск резервного копирования через PowerShell...

powershell -ExecutionPolicy Bypass -File "%BACKUP_PS%"

echo.
echo Резервное копирование завершено. Нажмите любую клавишу для выхода.
pause >nul



