import streamlit as st
import sqlite3
import os, sys
from streamlit_folium import st_folium
import folium
import pandas as pd
from config import DB_PATH
from database import get_connection, update_schema_dynamic, clean_column_name
from importer import parse_date, clean_value
from shapely.geometry import Point
from shapely.wkt import loads  # Se la geometria è salvata come testo (WKT)
# import shapely.wkb as wkb   # Se la geometria è salvata come BLOB binario (WKB)


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

def get_closest_comune_and_provincia(lat, lon):
    """
    Trova provincia e comune leggendo la geometria WKT in EPSG:4326.
    X = Longitudine (~7 per il Piemonte), Y = Latitudine (~45 per il Piemonte)
    """
    try:
        conn = get_connection()
        query = "SELECT provin_nom, comune_nom, geometry FROM limiti_amministrativi"
        df_limiti = pd.read_sql_query(query, conn)
        conn.close()
        
        if df_limiti.empty:
            return "DB vuoto", "DB vuoto"
            
        # IMPORTANTE: Shapely vuole Point(X, Y) -> Point(Longitudine, Latitudine)
        punto_cliccato = Point(lon, lat)
        
        comune_piu_vicino = None
        distanza_minima = float('inf')
        
        for _, row in df_limiti.iterrows():
            geom_wkt = row['geometry']
            if not geom_wkt:
                continue
                
            try:
                poligono = loads(str(geom_wkt))
                
                # 1. Tentativo di contenimento esatto
                if poligono.contains(punto_cliccato):
                    return str(row['provin_nom']).strip(), str(row['comune_nom']).strip()
                
                # 2. Calcolo distanza di sicurezza (fallback)
                distanza = punto_cliccato.distance(poligono)
                if distanza < distanza_minima:
                    distanza_minima = distanza
                    comune_piu_vicino = (str(row['provin_nom']).strip(), str(row['comune_nom']).strip())
            except Exception:
                continue
                
        # Se il click è leggermente fuori dal bordo del poligono (tolleranza ~4km)
        if comune_piu_vicino and distanza_minima < 0.04:
            return comune_piu_vicino[0], comune_piu_vicino[1]
            
    except Exception as e:
        st.error(f"Errore nell'elaborazione geometrica: {e}")
        
    return "Non rilevata", "Non rilevato"

def main_insert():
    if "sotto_sezione" not in st.session_state:
        st.session_state.sotto_sezione = "crea_stazione"

    st.subheader("🛠️ Pannello Gestione Dati e Stazioni")
    st.markdown("Seleziona l'operazione che desideri effettuare:")

    col_btn1, col_btn2, col_btn3 = st.columns(3)
    with col_btn1:
        azione_crea = st.button("➕ Crea Nuova Stazione", use_container_width=True, type="primary")
    with col_btn2:
        azione_carica = st.button("📥 Carica Dati (CSV)", use_container_width=True, type="primary")
    with col_btn3:
        azione_rinomina = st.button("✏️ Rinomina Stazione", use_container_width=True, type="primary")
        
    if azione_crea:
        st.session_state.sotto_sezione = "crea_stazione"
    if azione_carica:
        st.session_state.sotto_sezione = "carica_csv"
    if azione_rinomina:
        st.session_state.sotto_sezione = "rinomina_stazione"
        
    # --- FORM 1: CREAZIONE NUOVA STAZIONE / SENSORE ---
    if st.session_state.sotto_sezione == "crea_stazione":
        st.markdown("---")
        st.markdown("### ➕ Configurazione Nuova Stazione / Sensore")
        
        id_proposto = get_next_free_id()
        
        # Inizializzazione dello stato al primo caricamento (Centro Piemonte come default)
        if "lat_cliccata" not in st.session_state:
            st.session_state.lat_cliccata = 45.04
            st.session_state.lon_cliccata = 7.68
            st.session_state.provincia_rilevata = ""
            st.session_state.comune_rilevato = ""
            st.session_state.ha_cliccato = False

        col_mappa, col_form = st.columns([1.2, 1])
        
        with col_mappa:
            st.markdown("**📍 Clicca sulla mappa per selezionare la posizione:**")
            
            # Mappa centrata sulle coordinate correnti dello stato
            m = folium.Map(location=[st.session_state.lat_cliccata, st.session_state.lon_cliccata], zoom_start=8)
            
            if st.session_state.ha_cliccato:
                folium.Marker(
                    [st.session_state.lat_cliccata, st.session_state.lon_cliccata],
                    popup=f"{st.session_state.comune_rilevato} ({st.session_state.provincia_rilevata})",
                    icon=folium.Icon(color="red", icon="info-sign")
                ).add_to(m)
            
            mappa_output = st_folium(m, height=400, use_container_width=True, key="mappa_creazione")
        
        # Intercettiamo il click in tempo reale
        if mappa_output and mappa_output.get("last_clicked"):
            click_lat = mappa_output["last_clicked"]["lat"]
            click_lon = mappa_output["last_clicked"]["lng"]
            
            # Se le coordinate differiscono da quelle in memoria, l'utente ha fatto un nuovo click
            if click_lat != st.session_state.lat_cliccata or click_lon != st.session_state.lon_cliccata:
                st.session_state.lat_cliccata = click_lat
                st.session_state.lon_cliccata = click_lon
                st.session_state.ha_cliccato = True
                
                # Eseguiamo la query passando correttamente (Lat, Lon) alla nostra funzione
                prov, com = get_closest_comune_and_provincia(click_lat, click_lon)
                
                st.session_state.provincia_rilevata = prov
                st.session_state.comune_rilevato = com
                st.rerun() # Forza l'aggiornamento immediato dei campi di testo
            
        with col_form:
            st.markdown("**📝 Dati Stazione:**")
            
            nuovo_id = st.text_input("ID Sensore:", value=id_proposto)
            nuovo_nome = st.text_input("Nome Stazione / Posizione:", placeholder="es. Salone, Serra Nord")
            
            # Input di testo collegati direttamente alle variabili aggiornate dallo st.rerun()
            nuova_provincia = st.text_input("Provincia:", value=st.session_state.provincia_rilevata)
            nuovo_comune = st.text_input("Comune:", value=st.session_state.comune_rilevato)
            
            nuova_lat_input = st.number_input("Latitudine:", format="%.6f", value=st.session_state.lat_cliccata)
            nuova_lon_input = st.number_input("Longitudine:", format="%.6f", value=st.session_state.lon_cliccata)
            
            submit_stazione = st.button("Registra Stazione", use_container_width=True, type="primary")
            
            if submit_stazione:
                if nuovo_id.strip() == "" or nuovo_nome.strip() == "":
                    st.error("L'ID e il Nome del sensore sono obbligatori.")
                else:
                    try:
                        conn = sqlite3.connect(resolve_path('sensori.db'))
                        cursor = conn.cursor()
                        cursor.execute(
                            "INSERT INTO sensori (id, nome, lat, lon, provincia, comune) VALUES (?, ?, ?, ?, ?, ?)",
                            (nuovo_id, nuovo_nome, nuova_lat_input, nuova_lon_input, nuova_provincia, nuovo_comune)
                        )
                        conn.commit()
                        conn.close()
                        st.success(f"Stazione '{nuovo_nome}' creata con successo!")
                        
                        # Reset dello stato temporaneo geografico
                        del st.session_state.lat_cliccata
                        del st.session_state.lon_cliccata
                        del st.session_state.provincia_rilevata
                        del st.session_state.comune_rilevato
                        del st.session_state.ha_cliccato
                        
                        st.session_state.sotto_sezione = None
                        st.cache_data.clear() 
                        st.rerun()
                    except sqlite3.IntegrityError:
                        st.error("Errore: Esiste già una stazione con questo ID.")
                    except Exception as e:
                        st.error(f"Errore nel salvataggio: {e}")
    
    # --- FORM 2: CARICAMENTO FILE CSV ---
    elif st.session_state.sotto_sezione == "carica_csv":
        st.markdown("---")
        st.markdown("### 📥 Importazione Misure tramite CSV")
        
        try:
            conn = get_connection()
            df_stazioni = pd.read_sql_query("SELECT id, nome FROM sensori", conn)
            conn.close()
            
            if df_stazioni.empty:
                st.warning("⚠️ Non ci sono stazioni registrate nel database. Crea prima una stazione!")
                st.session_state.sotto_sezione = "crea_stazione"
                st.rerun()
            
            opzioni_stazioni = [f"{row['id']} - {row['nome']}" for _, row in df_stazioni.iterrows()]
            stazione_selezionata = st.selectbox("🎯 Seleziona la stazione a cui associare le misure:", options=opzioni_stazioni)
            id_sensore_scelto = int(stazione_selezionata.split(" - ")[0])
            
        except Exception as e:
            st.error(f"Errore nel recupero delle stazioni dal database: {e}")
            id_sensore_scelto = None

        st.info("💡 Il file CSV deve contenere una colonna per la data (es. `Date` o `timestamp`) e le colonne numeriche dei sensori.")
        uploaded_file = st.file_uploader("Trascina o seleziona il file CSV", type=["csv"], key="uploader_gestione")
        
        if uploaded_file is not None and id_sensore_scelto is not None:
            try:
                df_raw = pd.read_csv(uploaded_file)
                st.success("File letto correttamente! Elaborazione dello schema in corso...")
                
                colonne_raw = list(df_raw.columns)
                colonna_data_originale = None
                for c in ['Date', 'date', 'timestamp', 'Timestamp']:
                    if c in colonne_raw:
                        colonna_data_originale = c
                        break
                if not colonna_data_originale:
                    colonna_data_originale = colonne_raw[0]
                
                conn = get_connection()
                try:
                    update_schema_dynamic(conn, colonne_raw)
                except ValueError as ve:
                    st.error(f"❌ Errore di collisione nello schema: {ve}")
                    conn.close()
                    st.stop()
                conn.close()

                df_elaborato = pd.DataFrame()
                df_elaborato['date'] = df_raw[colonna_data_originale].astype(str).apply(lambda x: parse_date(x))
                df_elaborato['sensor_id'] = id_sensore_scelto
                
                for col in colonne_raw:
                    if col == colonna_data_originale:
                        continue
                    col_pulita = clean_column_name(col)
                    df_elaborato[col_pulita] = df_raw[col].astype(str).apply(clean_value)
                
                st.markdown("##### Anteprima dati normalizzati secondo le regole del Database:")
                st.dataframe(df_elaborato.head())
                
                if st.button("Conferma e Salva nel Database", key="save_csv_btn", use_container_width=True):
                    conn = get_connection()
                    cursor = conn.cursor()
                    record_inseriti = 0
                    duplicati_ignorati = 0
                    
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
                        st.info(f"⏳ {duplicati_ignorati} Righe sono state ignorate perché già esistenti.")
                    
                    st.session_state.sotto_sezione = None
                    st.cache_data.clear() 
                    st.rerun()
                    
            except Exception as e:
                st.error(f"❌ Errore durante l'elaborazione dei dati: {e}")
                
    # --- FORM 3: RINOMINA STAZIONE ---
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
            stazione_da_rinominare = st.selectbox("🎯 Seleziona la stazione da modificare:", options=opzioni_stazioni)
            
            id_da_modificare = int(stazione_da_rinominare.split(" - ")[0])
            vecchio_nome = " - ".join(stazione_da_rinominare.split(" - ")[1:])
            
            with st.form("form_esecutivo_rinomina", clear_on_submit=True):
                nuovo_nome = st.text_input(f"Nuovo nome per la stazione (Nome attuale: '{vecchio_nome}'):", placeholder="Inserisci il nuovo nome...")
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
