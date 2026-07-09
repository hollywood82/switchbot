import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import sqlite3
import sys, os
import pydeck as pdk


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
    # Modifica la query per includere latitudine (lat) e longitudine (lon)
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
    # Filtriamo df_completo tenendo solo i sensori attivi (selezionati in Temp O in Umidità)
    df_export = df_completo[
        ((df_completo['nome_sensore'].isin(sensori_temp_scelti)) & (df_completo['tipologia'] == 'Temperatura')) |
        ((df_completo['nome_sensore'].isin(sensori_umid_scelti)) & (df_completo['tipologia'] == 'Umidità'))
    ]
    
    if not df_export.empty:
        # Ricostruiamo una tabella Pivot ordinata e leggibile (es: Data/Ora | Nome Sensore | Temperatura | Umidità)
        df_pivot = df_export.pivot_table(
            index=['timestamp', 'nome_sensore'], 
            columns='tipologia', 
            values='valore'
        ).reset_index()
        
        # Ordiniamo per data
        df_pivot = df_pivot.sort_values(by='timestamp')
        
        # Funzione di conversione per non appesantire la memoria di Streamlit
        @st.cache_data
        def convert_df_to_csv(df):
            return df.to_csv(index=False).encode('utf-8')
            
        csv_data = convert_df_to_csv(df_pivot)
        
        # Posizionamento del pulsante sotto il terzo grafico
        col_btn, _ = st.columns([1, 3])
        with col_btn:
            st.download_button(
                label="📥 Scarica dati grafici (CSV)",
                data=csv_data,
                file_name=f"dati_sensori_{aggregazione.replace(' ', '_').lower()}.csv",
                mime="text/csv",
                use_container_width=True
            )
# --- NUOVA SEZIONE: MAPPA DEI SENSORI CON ZOOM DINAMICO ---
st.subheader("📍 Posizione Sensori Selezionati")

sensori_scelti_totali = list(set(sensori_temp_scelti + sensori_umid_scelti))

if sensori_scelti_totali:
    # 1. Filtriamo df_sensori e puliamo i dati
    df_mappa = df_sensori[df_sensori['nome_sensore'].isin(sensori_scelti_totali)].copy()
    df_mappa['lat'] = pd.to_numeric(df_mappa['lat'], errors='coerce')
    df_mappa['lon'] = pd.to_numeric(df_mappa['lon'], errors='coerce')
    df_mappa_pulito = df_mappa.dropna(subset=['lat', 'lon'])

    if not df_mappa_pulito.empty:

        # 2. Colore per SENSORE, coerente con le linee nei grafici sopra
        df_mappa_pulito['colore'] = df_mappa_pulito['nome_sensore'].apply(
            lambda nome: hex_to_rgb(color_map[nome])
        )

        # Manteniamo comunque il tipo per il tooltip
        def assegna_tipo(nome):
            if nome in sensori_temp_scelti:
                return "Temperatura"
            elif nome in sensori_umid_scelti:
                return "Umidità"
            return "Altro"

        df_mappa_pulito['tipo_sensore'] = df_mappa_pulito['nome_sensore'].apply(assegna_tipo)

        # 3. Dimensionamento dinamico del raggio in base al valore misurato
        # <-- ADATTA 'valore' al nome reale della colonna con l'ultima misura
        col_valore = 'valore'
        if col_valore in df_mappa_pulito.columns:
            v = pd.to_numeric(df_mappa_pulito[col_valore], errors='coerce').fillna(0)
            v_min, v_max = v.min(), v.max()
            RAGGIO_MIN, RAGGIO_MAX = 30, 150  # metri
            if v_max > v_min:
                df_mappa_pulito['raggio'] = RAGGIO_MIN + (v - v_min) / (v_max - v_min) * (RAGGIO_MAX - RAGGIO_MIN)
            else:
                df_mappa_pulito['raggio'] = RAGGIO_MIN
        else:
            df_mappa_pulito['raggio'] = 50  # fallback statico se la colonna non esiste

        # Calcoliamo il centro della mappa basandoci sui sensori presenti
        centro_lat = df_mappa_pulito['lat'].mean()
        centro_lon = df_mappa_pulito['lon'].mean()

        # Configurazione dello strato dei punti (ScatterplotLayer)
        layer = pdk.Layer(
            "ScatterplotLayer",
            data=df_mappa_pulito,
            get_position="[lon, lat]",
            get_fill_color="colore",       # colore dinamico per categoria
            get_radius="raggio",           # raggio dinamico in metri reali
            radius_min_pixels=4,
            radius_max_pixels=60,
            pickable=True,
        )

        # Stato iniziale della visualizzazione della mappa
        view_state = pdk.ViewState(
            latitude=centro_lat,
            longitude=centro_lon,
            zoom=10,
            pitch=0
        )

        # Rendering del grafico PyDeck con tooltip al passaggio del mouse
        st.pydeck_chart(
            pdk.Deck(
                layers=[layer],
                initial_view_state=view_state,
                tooltip={"text": "{nome_sensore}\n{tipo_sensore}: {valore}"}
            )
        )

        # 4. LEGENDA (pydeck non ha una legenda nativa, la costruiamo con HTML/CSS)
        legend_items = "".join(
            f'<div style="display:flex; align-items:center; gap:6px;">'
            f'<div style="width:14px; height:14px; border-radius:50%; background-color:{color_map[nome]};"></div>'
            f'{nome}</div>'
            for nome in sorted(sensori_scelti_totali)
        )
        legenda_html = f"""
        <div style="display:flex; flex-wrap:wrap; gap:16px; margin-top:8px; font-size:14px;">
            {legend_items}
        </div>
        <div style="font-size:12px; color:gray; margin-top:4px;">
            La dimensione del pallino è proporzionale al valore misurato. Il colore corrisponde a quello del sensore nei grafici.
        </div>
        """
        st.markdown(legenda_html, unsafe_allow_html=True)

    else:
        st.warning("⚠️ I sensori selezionati non hanno coordinate geografiche valide o sono incomplete nel database.")
else:
    st.info("💡 Seleziona almeno un sensore dal pannello di controllo per vederlo sulla mappa.")

st.markdown("---")