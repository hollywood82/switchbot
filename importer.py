import csv
import shutil
import time, sqlite3
from datetime import datetime
from config import INPUT_DIR, DONE_DIR, ERROR_DIR
from database import get_connection, get_or_create_sensor, update_schema_dynamic, clean_column_name
from logger import log  # riusa l'unica istanza già creata in logger.py (no doppio setup_logger())

def parse_date(date_str):
    """Converte '01/06/2026 00:00' o formati simili in ISO standard."""
    for fmt in ('%d/%m/%Y %H:%M:%S', '%d/%m/%Y %H:%M', '%Y-%m-%d %H:%M:%S'):
        try:
            return datetime.strptime(date_str.strip(), fmt).strftime('%Y-%m-%d %H:%M:%S')
        except ValueError:
            continue
    raise ValueError(f"Formato data non supportato: {date_str}")

def clean_value(val):
    """Trasforma i decimali europei con la virgola (es. 25,6) in float validi (25.6).
    Se il valore non è numerico, lo segnala e lo scarta (None) invece di inserirlo
    come stringa in una colonna REAL."""
    if val is None or val.strip() == '':
        return None
    try:
        return float(val.strip().replace(',', '.'))
    except ValueError:
        log.warning(f"⚠️ Valore non numerico '{val}' scartato (atteso numero in colonna REAL).")
        return None

def safe_move(src_path, dest_dir):
    """Sposta il file in modo sicuro gestendo i blocchi di Windows/OneDrive con tentativi multipli."""
    dest_path = dest_dir / src_path.name
    if dest_path.exists():
        try:
            dest_path.unlink()
        except Exception:
            pass

    for i in range(5):
        try:
            shutil.move(str(src_path), str(dest_path))
            return
        except PermissionError:
            time.sleep(0.5)

    shutil.copy(str(src_path), str(dest_path))
    try:
        src_path.unlink()
    except Exception:
        log.warning(f"⚠️ File copiato in {dest_dir.name} ma impossibile rimuovere l'originale (bloccato da OneDrive/Sistema).")

def process_files():
    stats = {
        "csv_letti": 0, "sensori_trovati": 0, "sensori_nuovi": 0,
        "record_inseriti": 0, "duplicati": 0, "errori": 0
    }

    csv_files = list(INPUT_DIR.glob("*.csv"))
    if not csv_files:
        log.info("ℹ️ Nessun file CSV trovato nella cartella 'input'.")
        return stats

    conn = get_connection()

    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM sensori")
        initial_sensors = cursor.fetchone()[0]

        for file_path in csv_files:
            log.info(f"\n📂 Analisi file: {file_path.name}")
            stats["csv_letti"] += 1

            sensor_name = file_path.stem.replace("_data", "").strip()
            sensor_id = get_or_create_sensor(conn, sensor_name)

            dialect = csv.excel
            with open(file_path, 'r', encoding='utf-8') as f:
                sample = f.read(2048)
                if not sample:
                    log.error(f"❌ File vuoto: {file_path.name}")
                    safe_move(file_path, ERROR_DIR)
                    stats["errori"] += 1
                    continue
                try:
                    dialect = csv.Sniffer().sniff(sample, delimiters=[',', ';', '\t'])
                except csv.Error:
                    pass

            with open(file_path, 'r', encoding='utf-8') as f:
                reader = csv.reader(f, dialect)
                try:
                    raw_headers = next(reader)
                except StopIteration:
                    log.error(f"❌ File senza intestazione: {file_path.name}")
                    safe_move(file_path, ERROR_DIR)
                    stats["errori"] += 1
                    continue

                if 'Date' not in raw_headers:
                    log.error(f"❌ Colonna 'Date' assente nel file {file_path.name}")
                    safe_move(file_path, ERROR_DIR)
                    stats["errori"] += 1
                    continue

                try:
                    update_schema_dynamic(conn, raw_headers)
                except ValueError as e:
                    # collisione tra nomi colonna dopo la pulizia: file scartato, non corrotto
                    log.error(f"❌ Schema non valido in {file_path.name}: {e}")
                    safe_move(file_path, ERROR_DIR)
                    stats["errori"] += 1
                    continue

                cleaned_headers = [clean_column_name(h) for h in raw_headers]
                date_index = raw_headers.index('Date')  # calcolato una sola volta per file

                fields = ['sensor_id', 'date'] + [h for h in cleaned_headers if h != 'Date']
                placeholders = ', '.join(['?'] * len(fields))
                query = f"INSERT INTO misure ({', '.join(fields)}) VALUES ({placeholders})"

                file_inserted = 0
                file_duplicates = 0
                file_righe_scartate = 0
                n_cols = len(raw_headers)

                try:
                    for row in reader:
                        if not row:
                            continue

                        # Riga più corta/lunga delle intestazioni: la segnaliamo e scartiamo
                        # invece di mappare i valori in modo silenzioso e sbagliato
                        if len(row) != n_cols:
                            file_righe_scartate += 1
                            continue

                        row_dict = dict(zip(cleaned_headers, row))

                        try:
                            iso_date = parse_date(row[date_index])
                        except (ValueError, IndexError):
                            file_righe_scartate += 1
                            continue

                        record = [sensor_id, iso_date]
                        for h in cleaned_headers:
                            if h != 'Date':
                                record.append(clean_value(row_dict.get(h)))

                        try:
                            cursor.execute(query, record)
                            file_inserted += 1
                        except sqlite3.IntegrityError:
                            file_duplicates += 1

                    conn.commit()
                    msg = f"✔️ {file_inserted} Nuovi record | ⏳ {file_duplicates} Righe già esistenti (saltate)"
                    if file_righe_scartate:
                        msg += f" | 🚫 {file_righe_scartate} Righe malformate scartate"
                    log.info(msg)

                    stats["record_inseriti"] += file_inserted
                    stats["duplicati"] += file_duplicates

                    safe_move(file_path, DONE_DIR)

                except Exception as e:
                    conn.rollback()
                    log.error(f"❌ Errore durante l'inserimento dati: {e}", exc_info=True)
                    safe_move(file_path, ERROR_DIR)
                    stats["errori"] += 1

        cursor.execute("SELECT COUNT(*) FROM sensori")
        total_sensors = cursor.fetchone()[0]
        stats["sensori_trovati"] = total_sensors
        stats["sensori_nuovi"] = total_sensors - initial_sensors

    finally:
        conn.close()

    return stats
