@echo off
chcp 65001 >nul
title Система учета ОС — Запуск

echo.
echo ==================================================
echo      СИСТЕМА УЧЕТА ОСНОВНЫХ СРЕДСТВ
echo ==================================================
echo.

:: Проверка Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ОШИБКА] Python не найден! Установите Python 3.8+ с https://python.org
    pause
    exit /b 1
)

:: Проверка Flask
python -c "import flask" >nul 2>&1
if %errorlevel% neq 0 (
    echo [УСТАНОВКА] Flask не найден. Устанавливаю...
    pip install flask pandas openpyxl werkzeug --quiet
    if %errorlevel% neq 0 (
        echo [ОШИБКА] Не удалось установить зависимости. Проверьте интернет.
        pause
        exit /b 1
    )
    echo [ГОТОВО] Flask и зависимости установлены.
) else (
    echo [OK] Flask уже установлен.
)

:: Проверка базы
if not exist "assets.db" (
    echo [ИНФО] База assets.db не найдена — будет создана при первом запуске.
)

:: Проверка schema.sql
if not exist "schema.sql" (
    echo [ОШИБКА] Файл schema.sql не найден! Положите его в эту папку.
    pause
    exit /b 1
)

:: Проверка app.py
if not exist "app.py" (
    echo [ОШИБКА] Файл app.py не найден!
    pause
    exit /b 1
)

echo.
echo [ЗАПУСК] Сервер стартует...
echo          Откроется в браузере: http://127.0.0.1:5000
echo          Для остановки: Ctrl+C
echo.

:: Запуск
start "" http://127.0.0.1:5000
python app.py

echo.
echo [СТОП] Сервер остановлен.
pause