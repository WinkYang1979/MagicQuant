@echo off
title MagicQuant Migration
echo.
echo  Migrating from C:\quant to C:\MagicQuant...
echo.

:: Copy existing data files if they exist
if exist C:\quant\signals_latest.json (
    copy C:\quant\signals_latest.json C:\MagicQuant\data\signals_latest.json
    echo  Copied signals_latest.json
)
if exist C:\quant\account_data.json (
    copy C:\quant\account_data.json C:\MagicQuant\data\account_data.json
    echo  Copied account_data.json
)
if exist C:\quant\watchlist.json (
    copy C:\quant\watchlist.json C:\MagicQuant\config\watchlist.json
    echo  Copied watchlist.json
)

echo.
echo  Migration complete!
echo  You can now use MagicQuant.bat to start all services.
echo.
pause
