from pathlib import Path

host = '127.0.0.1'
user = 'postgres'
password = '1234'
db_name = 'UP_dataBase'

DB_URL = "postgresql+psycopg2://postgres:1234@localhost:5432/UP_dataBase"
BASE_DIR = Path(__file__).parent
LOGS_DIR = BASE_DIR / "logs"
REPORTS_DIR = BASE_DIR / "reports"
LOGS_DIR.mkdir(exist_ok=True)
REPORTS_DIR.mkdir(exist_ok=True)