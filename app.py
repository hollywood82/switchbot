# "postgresql://neondb_owner:npg_Ke0s4DdLlJUS@ep-rough-shape-zalohu9u.c-2.eu-west-2.aws.neon.tech/neondb?sslmode=require"

import streamlit as st
import os
import random
import string
import psycopg2  # Sostituito sqlite3 con psycopg2
import json

# IMPORTIAMO LA FUNZIONE DALL'ALTRO FILE SEPARATO
from viewer_wms import show_dashboard

# --- IMPOSTAZIONI DELLA PAGINA ---
st.set_page_config(page_title="CHE CALDO CHE FA", page_icon="🌐", layout="wide")

# --- CONNESSIONE A NEON POSTGRESQL ---
DB_URL = "postgresql://neondb_owner:npg_Ke0s4DdLlJUS@ep-rough-shape-zalohu9u.c-2.eu-west-2.aws.neon.tech/neondb?sslmode=require"

def get_db_connection():
    return psycopg2.connect(DB_URL)

# --- INIZIALIZZAZIONE DATABASE POSTGRESQL ---
def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    # Creiamo la tabella utenti usando la sintassi PostgreSQL
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS utenti (
            username TEXT PRIMARY KEY,
            email TEXT NOT NULL,
            password TEXT NOT NULL,
            ruolo TEXT NOT NULL,
            profilo_dati TEXT
        )
    """)
    
    # Inseriamo l'utente admin predefinito se la tabella è vuota
    cursor.execute("SELECT COUNT(*) FROM utenti WHERE username = 'admin'")
    if cursor.fetchone()[0] == 0:
        cursor.execute(
            "INSERT INTO utenti (username, email, password, ruolo, profilo_dati) VALUES (%s, %s, %s, %s, %s)",
            ("admin", "admin@comune.it", "admin123", "Admin", None)
        )
        # Aggiungiamo anche un utente standard di test
        cursor.execute(
            "INSERT INTO utenti (username, email, password, ruolo, profilo_dati) VALUES (%s, %s, %s, %s, %s)",
            ("utente", "utente@email.com", "password", "Utente standard", None)
        )
    conn.commit()
    cursor.close()
    conn.close()

# Eseguiamo l'inizializzazione del database all'avvio
try:
    init_db()
except Exception as e:
    st.error(f"Errore di connessione al database PostgreSQL: {e}")

# --- FUNZIONE PER LEGGERE IL FILE DI TESTO MANTENENDO GLI ACAPO ---
def carica_testo_da_file(nome_file="intro_test.txt"):
    if not nome_file.endswith(".txt"):
        nome_file += ".txt"
        
    if os.path.exists(nome_file):
        with open(nome_file, "r", encoding="utf-8") as f:
            testo_raw = f.read()
            return testo_raw.replace("\n", "<br>")
    else:
        return f"*(Crea un file '{nome_file}' nella stessa cartella per mostrare qui il tuo testo)*"

# --- INIZIALIZZAZIONE DELLO STATO DELLA SESSIONE ---
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "user_profile" not in st.session_state:
    st.session_state.user_profile = None

# --- FUNZIONI DI AUTENTICAZIONE SU POSTGRESQL ---
def login(username, password):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT username, email, password, ruolo FROM utenti WHERE username = %s", (username,))
        user = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if user and user[2] == password:
            st.session_state.logged_in = True
            st.session_state.user_profile = {
                "username": user[0],
                "email": user[1],
                "ruolo": user[3]
            }
            st.success("Accesso effettuato!")
            st.rerun()
        else:
            st.error("Username o password errati.")
    except Exception as e:
        st.error(f"Errore durante il login: {e}")

def registra_utente(username, email, password, profilo_dati):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Verifichiamo se lo username esiste già
        cursor.execute("SELECT username FROM utenti WHERE username = %s", (username,))
        if cursor.fetchone():
            st.error("Questo username esiste già!")
            cursor.close()
            conn.close()
            return
            
        # Salviamo i dettagli aggiuntivi del form convertendoli in formato stringa JSON
        profilo_json = json.dumps(profilo_dati, ensure_ascii=False)
        
        cursor.execute(
            "INSERT INTO utenti (username, email, password, ruolo, profilo_dati) VALUES (%s, %s, %s, %s, %s)",
            (username, email, password, "Utente standard", profilo_json)
        )
        conn.commit()
        st.success("Registrazione completata con successo! Ora puoi fare il login nel tab 'Accedi'.")
    except Exception as e:
        st.error(f"Errore durante il salvataggio dei dati: {e}")
    finally:
        cursor.close()
        conn.close()

def aggiorna_password_db(username, nuova_password):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE utenti SET password = %s WHERE username = %s", (nuova_password, username))
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        st.error(f"Errore durante l'aggiornamento della password: {e}")

def recupera_password_db(username):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT email FROM utenti WHERE username = %s", (username,))
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        return result[0] if result else None
    except Exception as e:
        st.error(f"Errore durante il recupero della password: {e}")
        return None

def oscura_email(email):
    try:
        nome, dominio = email.split("@")
        return f"{nome[0]}***@{dominio}"
    except:
        return email

# --- GESTIONE INTERFACCIA ---
if not st.session_state.logged_in:
    # --- SCHERMATA DI LOG-IN / REGISTRAZIONE / RECUPERO ---
    
    col_logo_1, col_logo_2, col_logo_3 = st.columns([2, 1, 2])
    with col_logo_2:
        image_path = "image_963340.jpg"
        if os.path.exists(image_path):
            st.image(image_path, use_container_width=True)
            
    st.markdown(
        """
        <div style="text-align: center;">
            <h1 style="margin-bottom: 5px; color: #1E3A8A; font-weight: bold;">CHE TEMPO CHE FA</h1>
            <p style="font-size: 1.25rem; color: #666; margin-top: 0;">DATI NOSTRI, SPAZI DI TUTTI.</p>
        </div>
        """, 
        unsafe_allow_html=True
    )
    
    testo_personalizzato = carica_testo_da_file("intro_test.txt")
    st.markdown(
        f"""
        <div style="text-align: center; max-width: 600px; margin: 15px auto; color: #444; font-size: 1rem; line-height: 1.5; font-style: italic;">
            {testo_personalizzato}
        </div>
        """, 
        unsafe_allow_html=True
    )
    
    st.markdown("---")
    
    col_box_1, col_box_2, col_box_3 = st.columns([1, 2, 1])
    
    with col_box_2:
        tab1, tab2, tab3 = st.tabs(["🔐 Accedi", "📝 Registrati", "🔑 Recupera Password"])
        
        # --- TAB 1: LOGIN ---
        with tab1:
            st.subheader("Login")
            login_user = st.text_input("Username", key="login_user")
            login_pass = st.text_input("Password", type="password", key="login_pass")
            if st.button("Accedi", type="primary", use_container_width=True):
                login(login_user, login_pass)
                
        # --- TAB 2: REGISTRAZIONE ---
        with tab2:
            st.subheader("Crea un nuovo account")
            
            reg_user = st.text_input("Scegli uno Username *", key="reg_user")
            reg_email = st.text_input("La tua Email *", key="reg_email")
            reg_pass = st.text_input("Scegli una Password *", type="password", key="reg_pass")
            
            st.markdown("---")
            st.markdown("### Informazioni sul Profilo")
            
            reg_eta = st.selectbox("Età *", options=["", "< 18", "18–25", "26–35", "36–50", "51–65", "65+"], index=0)
            
            reg_background = st.multiselect(
                "Background (Seleziona almeno una voce) *",
                options=["Student*/ricercator*", "Cittadin*", "Attivista", "Professionista", "Altro"]
            )
            
            reg_settore_professione = ""
            if "Professionista" in reg_background:
                reg_settore_professione = st.text_input("Specificare il settore professionale (facoltativo)")
                
            reg_altro_background = ""
            if "Altro" in reg_background:
                reg_altro_background = st.text_input("Specificare altro background (facoltativo)")

            reg_canale = st.selectbox(
                "Come hai saputo della community? *", 
                options=["", "Passaparola", "Social", "Evento pubblico", "Università", "Altro"],
                index=0
            )
            
            reg_motivazione = st.text_area(
                "Motivazione *", 
                placeholder="Racconta in breve cosa ti ha incuriosito o motivato..."
            )
            
            reg_partecipazione = st.multiselect(
                "Modalità di partecipazione (Seleziona almeno una voce) *",
                options=["Ospitare un sensore", "Partecipare a campagne di misura sul campo", "Solo seguire i risultati"]
            )

            reg_consenso_dati = st.checkbox(
                "Acconsento al trattamento dei dati raccolti in questo form per finalità di analisi del progetto, come da informativa privacy. *"
            )
            
            if st.button("Registrati", use_container_width=True, type="primary"):
                if not reg_user or not reg_email or not reg_pass:
                    st.error("Per favore, compila tutti i campi di accesso (Username, Email e Password).")
                elif reg_eta == "":
                    st.error("Il campo 'Età' è obbligatorio.")
                elif len(reg_background) == 0:
                    st.error("Seleziona almeno un'opzione nel campo 'Background'.")
                elif reg_canale == "":
                    st.error("Specifica come hai saputo della community.")
                elif not reg_motivazione.strip():
                    st.error("Il campo 'Motivazione' non può essere vuoto.")
                elif len(reg_partecipazione) == 0:
                    st.error("Seleziona almeno una modalità di partecipazione.")
                elif not reg_consenso_dati:
                    st.error("È obbligatorio fornire il consenso al trattamento dei dati per registrarsi.")
                else:
                    profilo_completo = {
                        "eta": reg_eta,
                        "background": reg_background,
                        "settore_professione": reg_settore_professione,
                        "altro_background": reg_altro_background,
                        "come_saputo": reg_canale,
                        "motivazione": reg_motivazione,
                        "modalita_partecipazione": reg_partecipazione,
                        "consenso_privacy": reg_consenso_dati
                    }
                    registra_utente(reg_user, reg_email, reg_pass, profilo_completo)

        # --- TAB 3: RECUPERO PASSWORD ---
        with tab3:
            st.subheader("Recupera la tua Password")
            rec_user = st.text_input("Inserisci il tuo Username", key="rec_user")
            if rec_user:
                user_email = recupera_password_db(rec_user)
                if user_email:
                    email_protetta = oscura_email(user_email)
                    st.info(f"La password verrà generata e mostrata a schermo. Dovrebbe essere idealmente inviata a: **{email_protetta}**")
                    
                    if st.button("Conferma", type="primary", use_container_width=True):
                        nuova_password = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
                        aggiorna_password_db(rec_user, nuova_password)
                        st.success("Nuova password configurata con successo nel sistema!")
                        st.code(f"Nuova password temporanea: {nuova_password}")
                else:
                    st.error("Username non trovato.")

else:
    # --- UTENTE LOGGATO ---
    st.sidebar.title(f"👋 Ciao, {st.session_state.user_profile['username']}!")
    st.sidebar.write(f"**Ruolo:** {st.session_state.user_profile['ruolo']}")
    
    st.sidebar.markdown("---")
    with st.sidebar.expander("🔑 Cambia Password"):
        vecchia_pw = st.text_input("Password Attuale", type="password", key="old_pw")
        nuova_pw = st.text_input("Nuova Password", type="password", key="new_pw")
        conferma_pw = st.text_input("Conferma Nuova Password", type="password", key="confirm_pw")
        
        if st.button("Aggiorna Password", use_container_width=True):
            username_corrente = st.session_state.user_profile['username']
            
            try:
                # Recuperiamo la password attuale dal DB Postgres per il controllo
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT password FROM utenti WHERE username = %s", (username_corrente,))
                pw_corretta = cursor.fetchone()[0]
                cursor.close()
                conn.close()
                
                if vecchia_pw != pw_corretta:
                    st.error("La password attuale inserita non è corretta.")
                elif nuova_pw != conferma_pw:
                    st.error("Le nuove password non corrispondono.")
                elif len(nuova_pw) < 4:
                    st.error("La nuova password deve contenere almeno 4 caratteri.")
                else:
                    # Aggiorniamo sul database
                    aggiorna_password_db(username_corrente, nuova_pw)
                    st.success("Password aggiornata con successo sul Database!")
            except Exception as e:
                st.error(f"Errore durante l'aggiornamento della password: {e}")
    
    st.sidebar.markdown("---")
    if st.sidebar.button("Logout", type="secondary"):
        st.session_state.logged_in = False
        st.session_state.user_profile = None
        st.rerun()

    # --- CARICAMENTO DELL'APP IN BASE AL RUOLO ---
    if st.session_state.user_profile['ruolo'] == "Admin":
        show_dashboard()
    else:
        st.title("👋 Benvenuto")
        st.info("Le funzionalità della dashboard sono riservate agli Amministratori di CHE TEMPO CHE FA.")
