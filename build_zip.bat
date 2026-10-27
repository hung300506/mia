@echo off
echo ==============================================
echo   DONG GOI CAP NHAT CHO DISCLOUD
echo ==============================================
python -c "import zipfile, os; files = ['bot.py', 'requirements.txt', 'discloud.config', '.env']; z = zipfile.ZipFile('mimi-bot.zip', 'w', zipfile.ZIP_DEFLATED); [z.write(f, f) for f in files if os.path.exists(f)]; z.close(); print('Done! Da cap nhat xong file mimi-bot.zip.')"
echo.
echo Ban co the tai file mimi-bot.zip len Discloud.
pause
