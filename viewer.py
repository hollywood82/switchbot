import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import sqlite3
import sys, os
import pydeck as pdk
import folium
from folium import plugins
from streamlit_folium import st_folium
from tab_inserimento import main_insert
import requests


# --- PALETTE COLORI CONDIVISA (grafici + mappa) ---
PALETTE = px.colors.qualitative.Plotly

def hex_to_rgb(hex_color, alpha=200):
    """Converte un colore hex Plotly (es. '#636EFA') in lista RGBA per pydeck."""
    hex_color = hex_color.lstrip('#')
    r, g, b = tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
    return [r, g, b, alpha]


def resolve_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

# --- 1. CARICAMENTO DATI DA DATABASE REALE ---
@st.cache_data
def load_data():
    conn = sqlite3.connect(resolve_path('sensori.db'))
    
    # Carichiamo i dati rispettando i nomi reali delle colonne nel DB
    df_sensori = pd.read_sql_query("SELECT id AS id_sensore, nome AS nome_sensore, lat, lon FROM sensori", conn)
    df_misure_raw = pd.read_sql_query("SELECT sensor_id AS id_sensore, date AS timestamp, Temperature_Celsius_C AS Temperatura, Relative_Humidity_pct AS Umidità FROM misure", conn)
    
    conn.close()
    
    # Conversione della colonna date in formato datetime
    df_misure_raw['timestamp'] = pd.to_datetime(df_misure_raw['timestamp'])
    
    # Trasformiamo la tabella misure nel formato "long" richiesto dalla logica della dashboard
    df_misure = df_misure_raw.melt(
        id_vars=['id_sensore', 'timestamp'], 
        value_vars=['Temperatura', 'Umidità'],
        var_name='tipologia', 
        value_name='valore'
    )
    
    return df_sensori, df_misure

# --- SISTEMA DI NAVIGAZIONE PRINCIPALE ---
# Creiamo due macro-aree: Visualizzazione Dashboard e Gestione/Inserimento Dati
tab_dashboard, tab_inserimento = st.tabs(["📊 Visualizza Mappe & Grafici", "⚙️ Gestione & Inserimento Dati"])

# --- CONTENUTO DELLA SCHEDA INSERIMENTO (PAGINA PULITA) ---
with tab_inserimento:
    main_insert()


# --- CONTENUTO DELLA DASHBOARD ORIGINALE ---
with tab_dashboard:


    # Caricamento iniziale dei dati
    df_sensori, df_misure = load_data()

    # Mappa colore stabile per ogni sensore (ordine alfabetico), riusata in grafici e mappa
    color_map = {
        nome: PALETTE[i % len(PALETTE)]
        for i, nome in enumerate(sorted(df_sensori['nome_sensore'].unique()))
    }

    # --- 2. CONFIGURAZIONE INTERFACCIA E FILTRI ---
    st.set_page_config(layout="wide")
    st.title("📊 Dashboard Monitoraggio Sensori Switchbot")

    st.sidebar.header("🎛️ Pannello di Controllo")


    # --- FILTRO TEMPORALE ---
    st.sidebar.subheader("📅 Filtro Temporale")
    min_date = df_misure['timestamp'].min().date()
    max_date = df_misure['timestamp'].max().date()

    data_inizio = st.sidebar.date_input("Data inizio:", min_date, min_value=min_date, max_value=max_date)
    data_fine = st.sidebar.date_input("Data fine:", max_value=max_date, min_value=min_date, value=max_date)

    # Applicazione del filtro data alle misure
    df_misure_filtrate = df_misure[
        (df_misure['timestamp'].dt.date >= data_inizio) & 
        (df_misure['timestamp'].dt.date <= data_fine)
    ]

    # --- SELETTORE DI AGGREGAZIONE TEMPORALE ---
    st.sidebar.subheader("📉 Risoluzione Dati")
    aggregazione = st.sidebar.selectbox(
        "Seleziona granularità temporale:",
        options=["Dati Originali", "Media Oraria", "Media Giornaliera", "Media Settimanale"],
        index=1
    )

    # Mappatura delle regole di resampling di pandas
    agg_rules = {
        "Media Oraria": "h",
        "Media Giornaliera": "D",
        "Media Settimanale": "W"
    }

    # Applichiamo il ricampionamento se richiesto
    if aggregazione != "Dati Originali":
        rule = agg_rules[aggregazione]
        df_misure_filtrate = (
            df_misure_filtrate.set_index('timestamp')
            .groupby(['id_sensore', 'tipologia'])
            .resample(rule)['valore']
            .mean()
            .reset_index()
        )

    # Merge finale con i dati aggregati/filtrati e i nomi dei sensori
    df_completo = pd.merge(df_misure_filtrate, df_sensori, on='id_sensore')

    # --- SELEZIONE MODALITÀ E SENSORI ---
    modalita = st.sidebar.radio(
        "Cosa vuoi visualizzare?",
        ["Temperatura e Umidità", "Solo Temperatura", "Solo Umidità"]
    )

    # Filtriamo le liste sensori unici per i componenti multiselect
    sensori_temp_options = df_completo[df_completo['tipologia'] == 'Temperatura']['nome_sensore'].unique().tolist()
    sensori_umid_options = df_completo[df_completo['tipologia'] == 'Umidità']['nome_sensore'].unique().tolist()

    sensori_temp_scelti = []
    sensori_umid_scelti = []

    if modalita in ["Temperatura e Umidità", "Solo Temperatura"]:
        st.sidebar.subheader("🌡️ Sensori di Temperatura")
        sensori_temp_scelti = st.sidebar.multiselect(
            "Seleziona sensori Temp:", 
            options=sensori_temp_options,
            default=sensori_temp_options[:1] if sensori_temp_options else []
        )

    if modalita in ["Temperatura e Umidità", "Solo Umidità"]:
        st.sidebar.subheader("💧 Sensori di Umidità")
        sensori_umid_scelti = st.sidebar.multiselect(
            "Seleziona sensori Umidità:", 
            options=sensori_umid_options,
            default=sensori_umid_options[:1] if sensori_umid_options else []
        )

    # --- 3. GRAFICI ---
    suffisso_titolo = f" ({aggregazione})" if aggregazione != "Dati Originali" else " (Dati Originali)"

    fig_temp = go.Figure()
    if sensori_temp_scelti:
        df_t = df_completo[(df_completo['nome_sensore'].isin(sensori_temp_scelti)) & (df_completo['tipologia'] == 'Temperatura')]
        for nome, group in df_t.groupby('nome_sensore'):
            fig_temp.add_trace(go.Scatter(
                x=group['timestamp'], y=group['valore'], name=nome, mode='lines',
                line=dict(color=color_map[nome])
            ))
    fig_temp.update_layout(title=f"Andamento Temperature (°C){suffisso_titolo}", xaxis_title="Data/Ora", yaxis_title="°C")

    fig_umid = go.Figure()
    if sensori_umid_scelti:
        df_u = df_completo[(df_completo['nome_sensore'].isin(sensori_umid_scelti)) & (df_completo['tipologia'] == 'Umidità')]
        for nome, group in df_u.groupby('nome_sensore'):
            fig_umid.add_trace(go.Scatter(
                x=group['timestamp'], y=group['valore'], name=nome, mode='lines',
                line=dict(color=color_map[nome])
            ))
    fig_umid.update_layout(title=f"Andamento Umidità (%){suffisso_titolo}", xaxis_title="Data/Ora", yaxis_title="% RH")

    fig_comb = go.Figure()
    if sensori_temp_scelti:
        df_t = df_completo[(df_completo['nome_sensore'].isin(sensori_temp_scelti)) & (df_completo['tipologia'] == 'Temperatura')]
        for nome, group in df_t.groupby('nome_sensore'):
            fig_comb.add_trace(go.Scatter(
                x=group['timestamp'], y=group['valore'], name=f"{nome} (°C)", mode='lines',
                line=dict(color=color_map[nome])
            ))

    if sensori_umid_scelti:
        df_u = df_completo[(df_completo['nome_sensore'].isin(sensori_umid_scelti)) & (df_completo['tipologia'] == 'Umidità')]
        for nome, group in df_u.groupby('nome_sensore'):
            fig_comb.add_trace(go.Scatter(
                x=group['timestamp'], y=group['valore'], name=f"{nome} (%)", mode='lines', yaxis="y2",
                line=dict(color=color_map[nome], dash="dot")
            ))

    fig_comb.update_layout(
        title=f"Analisi Combinata (Temperatura & Umidità){suffisso_titolo}",
        xaxis=dict(title=dict(text="Data/Ora")),
        yaxis=dict(
            title=dict(text="Temperatura (°C)", font=dict(color="#1f77b4")), 
            tickfont=dict(color="#1f77b4")
        ),
        yaxis2=dict(
            title=dict(text="Umidità (%)", font=dict(color="#ff7f0e")), 
            tickfont=dict(color="#ff7f0e"), 
            anchor="x", 
            overlaying="y", 
            side="right"
        )
    )

    # --- 4. RENDERING ---
    if modalita == "Solo Temperatura":
        st.plotly_chart(fig_temp, width='stretch')
    elif modalita == "Solo Umidità":
        st.plotly_chart(fig_umid, width='stretch')
    else:
        col1, col2 = st.columns(2)
        with col1:
            st.plotly_chart(fig_temp, width='stretch')
        with col2:
            st.plotly_chart(fig_umid, width='stretch')
            
        st.markdown("---")
        st.subheader("🔄 Confronto Incrociato")
        st.plotly_chart(fig_comb, width='stretch')
        
        # --- NUOVO: ESPORTAZIONE DATI ATTIVI DEL TERZO GRAFICO ---
        df_export = df_completo[
            ((df_completo['nome_sensore'].isin(sensori_temp_scelti)) & (df_completo['tipologia'] == 'Temperatura')) |
            ((df_completo['nome_sensore'].isin(sensori_umid_scelti)) & (df_completo['tipologia'] == 'Umidità'))
        ]
        
        if not df_export.empty:
            df_pivot = df_export.pivot_table(
                index=['timestamp', 'nome_sensore'], 
                columns='tipologia', 
                values='valore'
            ).reset_index()
            
            df_pivot = df_pivot.sort_values(by='timestamp')
            
            @st.cache_data
            def convert_df_to_csv(df):
                return df.to_csv(index=False).encode('utf-8')
                
            csv_data = convert_df_to_csv(df_pivot)
            
            col_btn, _ = st.columns([1, 3])
            with col_btn:
                st.download_button(
                    label="📥 Scarica dati grafici (CSV)",
                    data=csv_data,
                    file_name=f"dati_sensori_{aggregazione.replace(' ', '_').lower()}.csv",
                    mime="text/csv",
                    use_container_width=True
                )

    # ===== PREPARAZIONE DATI MAPPA =====
    st.subheader("📍 Posizione Sensori Selezionati")

    sensori_scelti_totali = list(set(sensori_temp_scelti + sensori_umid_scelti))

    if sensori_scelti_totali:

        df_valori = (
            df_completo.sort_values("timestamp")
            .groupby(["id_sensore","tipologia"])
            .last()
            .reset_index()
        )

        # df_valori deriva da df_completo, che è già frutto del merge con df_sensori:
        # contiene già nome_sensore, lat, lon. Un secondo merge qui duplicherebbe
        # quelle colonne (nome_sensore_x/_y) e romperebbe la query sotto.
        df_mappa = (
            df_valori
            .query("nome_sensore in @sensori_scelti_totali")
            .copy()
        )

        df_mappa["lat"] = pd.to_numeric(df_mappa["lat"], errors="coerce")
        df_mappa["lon"] = pd.to_numeric(df_mappa["lon"], errors="coerce")
        df_mappa = df_mappa.dropna(subset=["lat","lon"])

        if not df_mappa.empty:

            def assegna_tipo(nome):
                if nome in sensori_temp_scelti:
                    return "Temperatura"
                elif nome in sensori_umid_scelti:
                    return "Umidità"
                return ""

            df_mappa["tipo"] = df_mappa["nome_sensore"].apply(assegna_tipo)

            valori = pd.to_numeric(df_mappa["valore"], errors="coerce").fillna(0)
            vmin, vmax = valori.min(), valori.max()
            RMIN, RMAX = 8, 20
            if vmax > vmin:
                df_mappa["raggio"] = RMIN + (valori-vmin)/(vmax-vmin)*(RMAX-RMIN)
            else:
                df_mappa["raggio"] = RMIN

            # Inizializziamo la mappa vuota (senza tile impliciti), poi aggiungiamo
            # i base layer esplicitamente così il LayerControl mostra nomi puliti
            # invece dell'URL grezzo.
            centro = [df_mappa["lat"].mean(), df_mappa["lon"].mean()]
            m = folium.Map(
                location=centro,
                zoom_start=12,
                tiles=None,
                control_scale=True
            )

            folium.TileLayer(
                tiles="https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
                attr="Google Satellite",
                name="Google",
                overlay=False,
                control=True
            ).add_to(m)

            folium.TileLayer("OpenStreetMap", name="OpenStreetMap").add_to(m)

            folium.WmsTileLayer(
                url="https://opengis.csi.it/mp/regp_agea_2024/service",
                layers="regp_agea_2024",
                fmt="image/png",
                version="1.3.0",
                transparent=True,
                overlay=True,
                name="Ortofoto AGEA 2024",
                attr="CSI Piemonte",
                show=True,
            ).add_to(m)


            # ==========================================
            # INTEGRAZIONE RETE STAZIONI TORINOMETEO (DAL DB)
            # ==========================================
            import sqlite3

            fg_torinometeo = folium.FeatureGroup(name="Stazioni TorinoMeteo", show=True)

            try:
                # 1. Ci connettiamo al database SQLite locale
                # Sostituisci "torinometeo.db" con il percorso corretto del tuo file se necessario
                conn = sqlite3.connect("sensori.db")
                
                # Usiamo sqlite3.Row per poter accedere alle colonne tramite il loro nome (es. riga['name'])
                conn.row_factory = sqlite3.Row 
                cursor = conn.cursor()
                
                # 2. Selezioniamo tutte le stazioni memorizzate
                cursor.execute("SELECT id, name, latitude, longitude, altitude, province, station_type FROM stazioni_meteo WHERE active = 1")
                lista_stazioni = cursor.fetchall()
                
                conn.close()

                if lista_stazioni:
                    # 3. Iteriamo sulle stazioni estratte dal DB
                    for st_info in lista_stazioni:
                        try:
                            lat_tm = st_info["latitude"]
                            lon_tm = st_info["longitude"]
                            
                            # Salta la stazione se mancano le coordinate fondamentali
                            if lat_tm is None or lon_tm is None:
                                continue
                                
                            lat_tm = float(lat_tm)
                            lon_tm = float(lon_tm)
                            nome_tm = st_info["name"]
                            alt_tm = st_info["altitude"] or "N/D"
                            prov_tm = st_info["province"] or "N/D"
                            tipo_tm = st_info["station_type"] or "N/D"
                            
                            # NOTA: Poiché i dati realtime (Temperatura/Umidità) cambiano continuamente,
                            # se non li hai salvati in una tabella storica separata nel DB, qui mostriamo i dati anagrafici fisici.
                            popup_html = f"""
                            <div style='font-family: sans-serif; font-size: 12px; width: 200px;'>
                                <b style='color: #0066cc;'>{nome_tm} ({prov_tm})</b><br>
                                <small style='color: gray;'>Rete TorinoMeteo (da DB)</small>
                                <hr style='margin: 4px 0; border: 0; border-top: 1px solid #eee;'>
                                Altitudine: <b>{alt_tm} m s.l.m.</b><br>
                                Sensore: <span>{tipo_tm}</span><br>
                                <small style='color: gray;'>Coord: {lat_tm:.4f}, {lon_tm:.4f}</small>
                            </div>
                            """
                            
                            # Aggiungiamo il Marker al FeatureGroup
                            folium.Marker(
                                location=[lat_tm, lon_tm],
                                tooltip=nome_tm,
                                popup=folium.Popup(popup_html, max_width=250),
                                icon=folium.Icon(color="blue", icon="cloud", prefix="fa")
                            ).add_to(fg_torinometeo)
                            
                        except Exception:
                            # Se una singola riga ha problemi di formattazione, passa alla successiva senza bloccare la mappa
                            continue
                            
                    # Aggiungiamo l'intero FeatureGroup alla mappa 'm'
                    fg_torinometeo.add_to(m)
                else:
                    st.warning("Il database delle stazioni TorinoMeteo è vuoto. Esegui prima lo script di importazione.")
                    
            except Exception as e:
                st.warning(f"Errore durante l'integrazione di TorinoMeteo dal DB: {e}")
            # ==========================================

            # I tuoi CircleMarker originali per i sensori già selezionati
            for _, r in df_mappa.iterrows():
                folium.CircleMarker(
                    location=[r["lat"], r["lon"]],
                    radius=float(r["raggio"]),
                    color=color_map[r["nome_sensore"]],
                    fill=True,
                    fill_color=color_map[r["nome_sensore"]],
                    fill_opacity=0.8,
                    weight=2,
                    tooltip=r["nome_sensore"],
                    popup=folium.Popup(
                        f"<b>{r['nome_sensore']}</b><br>"
                        f"Tipo: {r['tipo']}<br>"
                        f"Valore: <b>{r['valore']:.1f}</b><br>"
                        f"Coordinate:<br>{r['lat']:.6f}, {r['lon']:.6f}",
                        max_width=250
                    )
                ).add_to(m)

            m.fit_bounds([
                [df_mappa["lat"].min(), df_mappa["lon"].min()],
                [df_mappa["lat"].max(), df_mappa["lon"].max()]
            ])

            plugins.Fullscreen().add_to(m)
            plugins.MeasureControl().add_to(m)
            plugins.MousePosition().add_to(m)
            folium.LatLngPopup().add_to(m)
            
            # Il LayerControl ora mostrerà anche la checkbox "Stazioni TorinoMeteo"
            folium.LayerControl(collapsed=False).add_to(m)
            

            legend = """
            <div style="position:fixed;bottom:20px;left:20px;z-index:9999;
            background:white;padding:10px;border:2px solid gray;border-radius:6px;
            color:black;font-size:13px;">
            <b style="color:black;">Sensori</b><br>
            """
            for nome in sorted(sensori_scelti_totali):
                legend += f'<div style="color:black;"><span style="display:inline-block;width:12px;height:12px;border-radius:50%;background:{color_map[nome]};margin-right:6px;"></span>{nome}</div>'
            legend += "<hr>Dimensione del cerchio proporzionale al valore.</div>"
            m.get_root().html.add_child(folium.Element(legend))

            st_folium(m, width=None, height=650)

        else:
            st.warning("I sensori selezionati non hanno coordinate valide.")
    else:
        st.info("Seleziona almeno un sensore.")

    st.markdown("---")
