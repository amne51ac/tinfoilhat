@echo off
REM Setup script for the Tinfoil Hat Competition application (Windows)

REM Check Python version
python --version | findstr "Python 3.13" >nul
if errorlevel 1 (
    echo Error: Python 3.13 is required.
    echo Please install Python 3.13 and try again.
    pause
    exit /b 1
)

REM Create a virtual environment
echo Creating virtual environment...
python -m venv venv

REM Activate virtual environment
echo Activating virtual environment...
call venv\Scripts\activate.bat

REM Install dependencies
echo Installing dependencies...
pip install -e .

REM Initialize the database
echo Initializing database...
python init_db.py

echo Setup complete! You can now run the application with 'python run.py'
pause 