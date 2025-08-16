@echo off
echo Starting Guard Management System...
echo.

echo Activating virtual environment...
call myenv\Scripts\activate

echo.
echo Installing/updating dependencies...
pip install -r requirements.txt

echo.
echo Starting the application...
python main.py

pause
