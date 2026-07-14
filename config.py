from pathlib import Path

# Definisce la cartella principale dove si trova questo file config.py
BASE_DIR = Path(__file__).resolve().parent

# Directory di progetto collegate
INPUT_DIR = BASE_DIR / "input"
DONE_DIR = BASE_DIR / "done"
ERROR_DIR = BASE_DIR / "error"
LOGS_DIR = BASE_DIR / "logs"

# Il percorso assoluto del database SQLite (Quello che mancava!)
DB_PATH = BASE_DIR / "sensori.db"

# Creazione automatica delle cartelle se non esistono
for folder in [INPUT_DIR, DONE_DIR, ERROR_DIR, LOGS_DIR]:
    folder.mkdir(parents=True, exist_ok=True)
