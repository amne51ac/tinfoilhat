@echo off
REM Setup script for the Tinfoil Hat Competition application (Windows)

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