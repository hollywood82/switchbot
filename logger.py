import logging
import sys
from datetime import datetime
from config import LOGS_DIR

_logger_instance = None  # cache per evitare doppia inizializzazione

def setup_logger():
    """Crea (o riusa) il logger 'ImportSensori'.
    Idempotente: se viene chiamato più volte (es. da più moduli),
    non aggiunge handler duplicati e non duplica le righe di log."""
    global _logger_instance
    if _logger_instance is not None:
        return _logger_instance

    logger = logging.getLogger("ImportSensori")
    logger.setLevel(logging.INFO)
    logger.propagate = False  # evita doppio output se il root logger ha handler

    # Se per qualche motivo ha già handler (es. reload moduli), li puliamo prima
    if logger.handlers:
        logger.handlers.clear()

    log_filename = LOGS_DIR / f"import_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

    # Formato per il file
    file_formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    file_handler = logging.FileHandler(log_filename, encoding='utf-8')
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    # Formato per la console
    console_formatter = logging.Formatter('%(message)s')
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    _logger_instance = logger
    return logger

# Variabile importata dagli altri moduli: ora sicura anche se setup_logger()
# viene richiamato altrove (importer.py compreso)
log = setup_logger()
