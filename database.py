import sqlite3
import re
from config import DB_PATH

def get_connection():
    return sqlite3.connect(DB_PATH)

def init_db():
    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sensori (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT UNIQUE NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS misure (
                sensor_id INTEGER,
                date TEXT,
                FOREIGN KEY(sensor_id) REFERENCES sensori(id),
                UNIQUE(sensor_id, date)
            )
        """)

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_misure_date ON misure(date)")
        conn.commit()

def get_or_create_sensor(conn, sensor_name):
    """Verifica se il sensore esiste già. Se non esiste, lo crea assegnando un ID consecutivo."""
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO sensori (nome) VALUES (?)", (sensor_name,))
    cursor.execute("SELECT id FROM sensori WHERE nome = ?", (sensor_name,))
    return cursor.fetchone()[0]

def update_schema_dynamic(conn, headers):
    """Pulisce i nomi delle colonne e aggiorna dinamicamente la tabella se servono nuove colonne.
    Gestisce anche collisioni tra header diversi che si riducono allo stesso nome pulito."""
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(misure)")
    existing_cols = {row[1].lower() for row in cursor.fetchall()}

    seen_in_this_file = set()

    for h in headers:
        col_clean = clean_column_name(h)

        if not col_clean or col_clean.lower() in ['sensor_id', 'date', 'id']:
            continue

        if col_clean.lower() in seen_in_this_file:
            # Collisione tra due header diversi che producono lo stesso nome colonna:
            # meglio fermarsi con un errore chiaro che corrompere i dati silenziosamente.
            raise ValueError(
                f"Collisione di nomi colonna: l'header '{h}' produce '{col_clean}', "
                f"già usato da un'altra colonna in questo file."
            )
        seen_in_this_file.add(col_clean.lower())

        if col_clean.lower() not in existing_cols:
            cursor.execute(f'ALTER TABLE misure ADD COLUMN "{col_clean}" REAL')
            conn.commit()
            existing_cols.add(col_clean.lower())

def clean_column_name(header):
    """Normalizza i nomi delle colonne rimuovendo caratteri non standard,
    garantendo un identificatore SQL valido."""
    replacements = {
        " ": "_", "(": "_", ")": "", "℃": "C", "°": "", "%": "pct", "³": "3", "/": "_", "-": "_"
    }
    cleaned = header.strip()
    for k, v in replacements.items():
        cleaned = cleaned.replace(k, v)

    # Rimuove qualunque carattere non alfanumerico/underscore rimasto
    cleaned = re.sub(r'[^0-9a-zA-Z_]', '', cleaned)

    # Un identificatore SQL non può iniziare con una cifra
    if cleaned and cleaned[0].isdigit():
        cleaned = f"col_{cleaned}"

    # Collassa underscore multipli e quelli ai bordi
    cleaned = re.sub(r'_+', '_', cleaned).strip('_')

    return cleaned
