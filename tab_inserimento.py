import streamlit as st
import sqlite3
import os, sys
from streamlit_folium import st_folium
import folium
import pandas as pd
from config import DB_PATH
from database import get_connection, update_schema_dynamic, clean_column_name
from importer import parse_date, clean_value


def resolve_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

def get_next_free_id():
    try:
        conn = sqlite3.connect(resolve_path('sensori.db'))
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM sensori")
        ids = [row[0] for row in cursor.fetchall()]
        conn.close()
        
        numeric_ids = []
        for i in ids:
            try:
                numeric_ids.append(int(i))
            except ValueError:
                continue
        
        next_id = 1
        while next_id in numeric_ids:
            next_id += 1
            
        return f"{next_id:02d}" 
    except Exception:
        return "01"

def main_insert():
    # 1. PRIMA DI TUTTO: Inizializza la session_state se non esiste!
    if "sotto_sezione" not in st.session_state:
        st.session_state.sotto_sezione = None

    st.subheader("🛠️ Pannello Gestione Dati e Stazioni")
    st.markdown("Seleziona l'operazione che desideri effettuare:")

    # Triplo bottone (usiamo tre colonne affiancate)
    col_btn1, col_btn2, col_btn3 = st.columns(3)

    with col_btn2:
        azione_carica = st.button("📥 Carica Dati (CSV)", use_container_width=True, type="primary")
    with col_btn1:
        azione_crea = st.button("➕ Crea Nuova Stazione", use_container_width=True, type="primary")
    with col_btn3:
        azione_rinomina = st.button("✏️ Rinomina Stazione", use_container_width=True, type="primary")
        
    # Assegnazione della sotto-sezione in base al click
    if azione_carica:
        st.session_state.sotto_sezione = "carica_csv"
    if azione_crea:
        st.session_state.sotto_sezione = "crea_stazione"
    if azione_rinomina:
        st.session_state.sotto_sezione = "rinomina_stazione"
        
    # --- FORM 1: CARICAMENTO FILE CSV (Adattato al Backend) ---
    if st.session_state.sotto_sezione == "carica_csv":
        st.markdown("---")
        st.markdown("### 📥 Importazione Misure tramite CSV")
        
        try:
            # Usiamo il metodo di connessione nativo
            conn = get_connection()
            df_stazioni = pd.read_sql_query("SELECT id, nome FROM sensori", conn)
            conn.close()
            
            if df_stazioni.empty:
                st.warning("⚠️ Non ci sono stazioni registrate nel database. Crea prima una stazione!")
                st.session_state.sotto_sezione = "crea_stazione"
                st.rerun()
            
            # Creiamo l'elenco per la selectbox
            opzioni_stazioni = [f"{row['id']} - {row['nome']}" for _, row in df_stazioni.iterrows()]
            
            stazione_selezionata = st.selectbox(
                "🎯 Seleziona la stazione a cui associare le misure:", 
                options=opzioni_stazioni
            )
            
            # Otteniamo l'ID numerico corretto (il backend usa gli INTEGER per sensor_id)
            id_sensore_scelto = int(stazione_selezionata.split(" - ")[0])
            
        except Exception as e:
            st.error(f"Errore nel recupero delle stazioni dal database: {e}")
            id_sensore_scelto = None
    st.markdown("---")
    st.markdown("### 📥 Importazione Misure tramite CSV")
    
    try:
        # Usiamo il metodo di connessione nativo
        conn = get_connection()
        df_stazioni = pd.read_sql_query("SELECT id, nome FROM sensori", conn)
        conn.close()
        
        if df_stazioni.empty:
            st.warning("⚠️ Non ci sono stazioni registrate nel database. Crea prima una stazione!")
            st.session_state.sotto_sezione = "crea_stazione"
            st.rerun()
        
        # Creiamo l'elenco per la selectbox
        opzioni_stazioni = [f"{row['id']} - {row['nome']}" for _, row in df_stazioni.iterrows()]
        
        stazione_selezionata = st.selectbox(
            "🎯 Seleziona la stazione a cui associare le misure:", 
            options=opzioni_stazioni
        )
        
        # Otteniamo l'ID numerico corretto (il backend usa gli INTEGER per sensor_id)
        id_sensore_scelto = int(stazione_selezionata.split(" - ")[0])
        
    except Exception as e:
        st.error(f"Errore nel recupero delle stazioni dal database: {e}")
        id_sensore_scelto = None

    st.info("💡 Il file CSV deve contenere una colonna per la data (es. `Date` o `timestamp`) e le colonne numeriche dei sensori. I nomi verranno normalizzati automaticamente.")
    
    uploaded_file = st.file_uploader("Trascina o seleziona il file CSV", type=["csv"], key="uploader_gestione")
    
    if uploaded_file is not None and id_sensore_scelto is not None:
        try:
            # Leggiamo il file (il backend gestisce i dialetti, qui usiamo una lettura standard di anteprima)
            df_raw = pd.read_csv(uploaded_file)
            st.success("File letto correttamente! Elaborazione dello schema in corso...")
            
            # --- APPLICAZIONE LOGICHE BACKEND ---
            # 1. Identifichiamo la colonna data (cerchiamo 'Date', 'date', 'timestamp' o la prima colonna)
            colonne_raw = list(df_raw.columns)
            colonna_data_originale = None
            for c in ['Date', 'date', 'timestamp', 'Timestamp']:
                if c in colonne_raw:
                    colonna_data_originale = c
                    break
            if not colonna_data_originale:
                colonna_data_originale = colonne_raw[0] # Fallback sulla prima colonna
            
            # 2. Aggiorniamo dinamicamente lo schema del database (crea colonne se non esistono)
            conn = get_connection()
            try:
                # Passiamo i raw_headers come fa importer.py
                update_schema_dynamic(conn, colonne_raw)
            except ValueError as ve:
                st.error(f"❌ Errore di collisione nello schema: {ve}")
                conn.close()
                st.stop()
            conn.close()

            # 3. Costruiamo il nuovo DataFrame normalizzato pronto per il DB
            df_elaborato = pd.DataFrame()
            
            # Convertiamo le date usando la funzione parse_date del tuo importer.py
            df_elaborato['date'] = df_raw[colonna_data_originale].astype(str).apply(lambda x: parse_date(x))
            
            # Impostiamo la colonna chiave esterna corretta: 'sensor_id'
            df_elaborato['sensor_id'] = id_sensore_scelto
            
            # Mappiamo e puliamo le altre colonne numeriche
            for col in colonne_raw:
                if col == colonna_data_originale:
                    continue
                col_pulita = clean_column_name(col)
                # Applichiamo la pulizia dei decimali europei (virgole in punti) del tuo backend
                df_elaborato[col_pulita] = df_raw[col].astype(str).apply(clean_value)
            
            # Mostriamo l'anteprima di come i dati verranno strutturati nel DB
            st.markdown("##### Anteprima dati normalizzati secondo le regole del Database:")
            st.dataframe(df_elaborato.head())
            
            if st.button("Conferma e Salva nel Database", key="save_csv_btn", use_container_width=True):
                conn = get_connection()
                cursor = conn.cursor()
                
                # Inserimento record per record per gestire l'IntegrityError (chiave unica date + sensor_id)
                # esattamente come fa process_files() nel backend
                record_inseriti = 0
                duplicati_ignorati = 0
                
                # Prepariamo la query dinamica
                colonne_db = list(df_elaborato.columns)
                placeholders = ', '.join(['?'] * len(colonne_db))
                query = f"INSERT INTO misure ({', '.join(colonne_db)}) VALUES ({placeholders})"
                
                for row in df_elaborato.itertuples(index=False):
                    try:
                        cursor.execute(query, list(row))
                        record_inseriti += 1
                    except sqlite3.IntegrityError:
                        duplicati_ignorati += 1
                
                conn.commit()
                conn.close()
                
                if record_inseriti > 0:
                    st.success(f"✔️ {record_inseriti} Nuovi record salvati con successo per la stazione {stazione_selezionata}!")
                if duplicati_ignorati > 0:
                    st.info(f"⏳ {duplicati_ignorati} Righe sono state ignorate perché già esistenti (Data + Sensore duplicati).")
                
                st.session_state.sotto_sezione = None
                st.cache_data.clear() 
                st.rerun()
                
        except Exception as e:
            st.error(f"❌ Errore durante l'elaborazione dei dati secondo le regole del backend: {e}")
                
    # --- FORM 2: CREAZIONE NUOVA STAZIONE / SENSORE ---
    elif st.session_state.sotto_sezione == "crea_stazione":
        st.markdown("---")
        st.markdown("### ➕ Configurazione Nuova Stazione / Sensore")
        
        id_proposto = get_next_free_id()
        
        # Creiamo un layout a due colonne: Mappa a sinistra, Form a destra
        col_mappa, col_form = st.columns([1.2, 1])
        
        with col_mappa:
            st.markdown("**📍 Clicca sulla mappa per selezionare la posizione:**")
            
            # Mappa Folium di partenza centrata sull'Italia (o dove preferisci)
            m = folium.Map(location=[45.0, 7.5], zoom_start=8)
            
            # Script JavaScript per aggiungere un marker visivo dinamico al click senza ricaricare la pagina
            clicca_js = """
            function onClick(e) {
                if (window.currentMarker) {
                    window.currentMarker.setLatLng(e.latlng);
                } else {
                    window.currentMarker = L.marker(e.latlng).addTo(this);
                }
            }
            """
            m.add_child(folium.ClickForMarker(popup="Nuova Stazione"))
            
            # Renderizziamo la mappa. Restituisce i dati in tempo reale
            mappa_output = st_folium(m, height=400, use_container_width=True, key="mappa_creazione")
        
        # Estraiamo le coordinate cliccate se presenti, altrimenti usiamo valori di default
        lat_cliccata = 45.0
        lon_cliccata = 7.5
        if mappa_output and mappa_output.get("last_clicked"):
            lat_cliccata = mappa_output["last_clicked"]["lat"]
            lon_cliccata = mappa_output["last_clicked"]["lng"]
            
        with col_form:
            st.markdown("**📝 Dati Stazione:**")
            # Usiamo un form Streamlit classico affiancato alla mappa
            with st.form("form_nuova_stazione", clear_on_submit=True):
                nuovo_id = st.text_input("ID Sensore:", value=id_proposto)
                nuovo_nome = st.text_input("Nome Stazione / Posizione:", placeholder="es. Salone, Serra Nord")
                
                # Campi coordinate aggiornati in tempo reale dal click sulla mappa
                nuova_lat = st.number_input("Latitudine:", format="%.6f", value=lat_cliccata)
                nuova_lon = st.number_input("Longitudine:", format="%.6f", value=lon_cliccata)
                
                submit_stazione = st.form_submit_button("Registra Stazione", use_container_width=True)
                
                if submit_stazione:
                    if nuovo_id.strip() == "" or nuovo_nome.strip() == "":
                        st.error("L'ID e il Nome del sensore sono obbligatori.")
                    else:
                        try:
                            conn = sqlite3.connect(resolve_path('sensori.db'))
                            cursor = conn.cursor()
                            cursor.execute(
                                "INSERT INTO sensori (id, nome, lat, lon) VALUES (?, ?, ?, ?)",
                                (nuovo_id, nuovo_nome, nuova_lat, nuova_lon)
                            )
                            conn.commit()
                            conn.close()
                            st.success(f"Stazione '{nuovo_nome}' creata!")
                            
                            st.session_state.sotto_sezione = None
                            st.cache_data.clear() 
                            st.rerun()
                        except sqlite3.IntegrityError:
                            st.error("Errore: Esiste già una stazione con questo ID.")
                        except Exception as e:
                            st.error(f"Errore nel salvataggio: {e}")
    
    
    # --- FORM 3: RINOMINA STAZIONE (Risolto errore Selectbox/Form) ---
    elif st.session_state.sotto_sezione == "rinomina_stazione":
        st.markdown("---")
        st.markdown("### ✏️ Rinomina Stazione / Sensore Esistente")
        
        try:
            conn = get_connection()
            df_stazioni = pd.read_sql_query("SELECT id, nome FROM sensori", conn)
            conn.close()
            
            if df_stazioni.empty:
                st.warning("⚠️ Non ci sono stazioni da rinominare.")
                st.session_state.sotto_sezione = "crea_stazione"
                st.rerun()
                
            opzioni_stazioni = [f"{row['id']} - {row['nome']}" for _, row in df_stazioni.iterrows()]
            
            # 1. Mettiamo la SELECTBOX FUORI dal form (così Streamlit aggiorna i dati sottostanti senza errori)
            stazione_da_rinominare = st.selectbox(
                "🎯 Seleziona la stazione da modificare:", 
                options=opzioni_stazioni
            )
            
            id_da_modificare = int(stazione_da_rinominare.split(" - ")[0])
            vecchio_nome = " - ".join(stazione_da_rinominare.split(" - ")[1:])
            
            # 2. Il FORM racchiude SOLO l'input di testo e il pulsante di conferma
            with st.form("form_esecutivo_rinomina", clear_on_submit=True):
                nuovo_nome = st.text_input(
                    f"Nuovo nome per la stazione (Nome attuale: '{vecchio_nome}'):",
                    placeholder="Inserisci il nuovo nome..."
                )
                
                submit_rinomina = st.form_submit_button("Aggiorna Nome Stazione", use_container_width=True)
                
                if submit_rinomina:
                    if nuovo_nome.strip() == "":
                        st.error("Il nuovo nome non può essere vuoto.")
                    elif nuovo_nome.strip() == vecchio_nome:
                        st.warning("Il nuovo nome è identico a quello attuale.")
                    else:
                        try:
                            conn = get_connection()
                            cursor = conn.cursor()
                            cursor.execute("UPDATE sensori SET nome = ? WHERE id = ?", (nuovo_nome.strip(), id_da_modificare))
                            conn.commit()
                            conn.close()
                            
                            st.success(f"✔️ Stazione rinominata in '{nuovo_nome}'!")
                            st.session_state.sotto_sezione = None
                            st.cache_data.clear()
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ Errore durante l'aggiornamento: {e}")
                            
        except Exception as e:
            st.error(f"Errore nel recupero dei dati: {e}")