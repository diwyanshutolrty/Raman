@echo off
echo Starting AI Assistant Backend...
start /b python app.py
echo Waiting for server to initialize...
timeout /t 3 /nobreak > nul
echo Opening AI Assistant in browser...
start http://127.0.0.1:5005
echo Assistant is now running!
echo Keep this window open while using the assistant.
pause
