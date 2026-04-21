import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd

# --- 1. CONFIGURACIÓN Y ESTILO ---
st.set_page_config(page_title="Dashboard PANUS", layout="wide")

st.markdown("""
    <style>
    th { vertical-align: bottom !important; text-align: center !important; height: 150px !important; }
    th > div {
        writing-mode: vertical-rl !important; transform: rotate(180deg) !important;
        white-space: nowrap !important; font-family: sans-serif !important; font-size: 13px !important;
    }
    td { white-space: nowrap !important; text-align: center !important; padding: 0 10px !important; }
    .stTable { width: auto !important; }
    </style>
""", unsafe_allow_html=True)

st.title("🥐 Sistema de Gestión PANUS")

# --- 2. FUNCIONES DE CONEXIÓN (ST SECRETS) ---
def obtener_cliente():
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        # Lee directamente desde el panel de Secrets de Streamlit Cloud
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"Error de conexión (Secrets): {e}")
        return None

def limpiar_columnas(columns):
    cols = []
    counts = {}
    for item in columns:
        item = item.strip() if item else ""
        if item in counts:
            counts[item] += 1
            cols.append(f"{item}_DUPLICADO_{counts[item]}")
        else:
            counts[item] = 1
            cols.append(item)
    return cols

@st.cache_data(ttl=60)
def cargar_pestana(archivo, pestana):
    client = obtener_cliente()
    if not client: return pd.DataFrame()
    try:
        sh = client.open(archivo)
        ws = sh.worksheet(pestana)
        datos = ws.get_values()
        if len(datos) < 2: return pd.DataFrame()
        df = pd.DataFrame(datos[2:], columns=limpiar_columnas(datos[1]))
        df.rename(columns={df.columns[0]: 'Día', df.columns[1]: 'Tienda_ID'}, inplace=True)
        df['Día'] = df['Día'].replace('', None).ffill()
        df['Tienda_ID'] = df['Tienda_ID'].astype(str).str.strip()
        return df
    except: return pd.DataFrame()

@st.cache_data(ttl=60)
def obtener_datos_maestros():
    """Retorna Productos Oficiales y Lista de Tiendas basados en Resumen 2026"""
    df_m = cargar_pestana("Ventas PANUS 2026", "Resumen")
    if df_m.empty: return [], []
    excluir = ['Día', 'Tienda_ID', 'T.I.', 'T.C.G', 'T.M', 'OC', 'idx_orig', '']
    productos = [c for c in df_m.columns if c not in excluir and "_DUPLICADO_" not in c and not c.startswith('Col_')]
    tiendas = sorted([t for t in df_m['Tienda_ID'].unique() if str(t).upper().startswith(('T', 'E'))])
    return productos, tiendas

# --- 3. LOGICA DE INTERFAZ ---
st.sidebar.title("🚀 Menú Principal")
menu = st.sidebar.radio("Ir a:", ["📅 Semana Actual", "📚 Historial / Buscador Global"])

# Cargamos maestros una sola vez
lista_prod_oficial, lista_tiendas_oficial = obtener_datos_maestros()

if menu == "📅 Semana Actual":
    st.header("📊 Ventas PANUS 2026")
    df = cargar_pestana("Ventas PANUS 2026", "Resumen")
    if not df.empty:
        sel = st.selectbox("Seleccionar Tienda:", lista_tiendas_oficial)
        if sel:
            res = df[df['Tienda_ID'] == sel].copy()
            cols_vivas = ['Día', 'Tienda_ID']
            for p in lista_prod_oficial:
                if p in res.columns:
                    val_num = pd.to_numeric(res[p], errors='coerce').fillna(0)
                    if val_num.sum() > 0:
                        cols_vivas.append(p)
                        res[p] = val_num.apply(lambda x: int(x) if x != 0 else "")
            if 'OC' in res.columns: cols_vivas.append('OC')
            st.write(res[cols_vivas].to_html(escape=False, index=False), unsafe_allow_html=True)

else:
    st.sidebar.divider()
    archivo_h = st.sidebar.selectbox("Año Historial:", ["Resumen Pedidos 2026", "Resumen Pedidos 2025"])
    modo = st.sidebar.radio("Modo:", ["🔍 Por Pestaña", "🌎 Buscador Anual (Global)"])

    if modo == "🔍 Por Pestaña":
        client = obtener_cliente()
        if client:
            sh = client.open(archivo_h)
            p_sel = st.sidebar.selectbox("Elegir Semana:", [w.title for w in sh.worksheets() if w.title.lower() not in ['resumen', 'config', 'indices']])
            df_h = cargar_pestana(archivo_h, p_sel)
            if not df_h.empty:
                sel_h = st.selectbox("Tienda:", lista_tiendas_oficial)
                if sel_h:
                    res_h = df_h[df_h['Tienda_ID'] == sel_h].copy()
                    cols_h = ['Día', 'Tienda_ID']
                    for p in lista_prod_oficial:
                        if p in res_h.columns:
                            val_n = pd.to_numeric(res_h[p], errors='coerce').fillna(0)
                            if val_n.sum() > 0:
                                cols_h.append(p)
                                res_h[p] = val_n.apply(lambda x: int(x) if x != 0 else "")
                    if 'OC' in res_h.columns: cols_h.append('OC')
                    st.write(res_h[cols_h].to_html(escape=False, index=False), unsafe_allow_html=True)
    
    else:
        st.header(f"🌎 Buscador Global: {archivo_h}")
        id_busq = st.selectbox("Selecciona la tienda:", [""] + lista_tiendas_oficial)
        if st.button("Iniciar Rastreo Anual") and id_busq != "":
            client = obtener_cliente()
            if client:
                sh = client.open(archivo_h)
                hojas = sh.worksheets()
                lista_resultados = []
                prog = st.progress(0)
                for i, ws in enumerate(hojas):
                    prog.progress((i+1)/len(hojas))
                    if ws.title.lower() in ['resumen', 'config', 'indices', 'totales', 'base']: continue
                    rows = ws.get_values()
                    if len(rows) < 3: continue
                    df_tmp = pd.DataFrame(rows[2:], columns=limpiar_columnas(rows[1]))
                    df_tmp.rename(columns={df_tmp.columns[0]: 'Día', df_tmp.columns[1]: 'Tienda_ID'}, inplace=True)
                    df_tmp['Tienda_ID'] = df_tmp['Tienda_ID'].astype(str).str.strip()
                    match = df_tmp[df_tmp['Tienda_ID'].str.lower() == id_busq.lower()].copy()
                    if not match.empty:
                        match['Semana'] = ws.title
                        lista_resultados.append(match)
                prog.empty()
                if lista_resultados:
                    df_global = pd.concat(lista_resultados, ignore_index=True, sort=False)
                    cols_prod_ordenados = []
                    fila_t = {'Semana': '---', 'Día': '---', 'Tienda_ID': '<strong>TOTAL</strong>'}
                    for p in lista_prod_oficial:
                        if p in df_global.columns:
                            nums = pd.to_numeric(df_global[p], errors='coerce').fillna(0)
                            total_p = int(nums.sum())
                            if total_p > 0:
                                cols_prod_ordenados.append(p)
                                df_global[p] = nums.apply(lambda x: int(x) if x != 0 else "")
                                fila_t[p] = f"<strong>{total_p}</strong>"
                    cols_finales = ['Semana', 'Día', 'Tienda_ID'] + cols_prod_ordenados
                    if 'OC' in df_global.columns:
                        cols_finales.append('OC'); fila_t['OC'] = '---'
                    res_g = df_global[cols_finales].copy()
                    res_g = pd.concat([res_g, pd.DataFrame([fila_t])], ignore_index=True)
                    res_g.columns = [f"<div>{x}</div>" for x in res_g.columns]
                    st.write(res_g.to_html(escape=False, index=False), unsafe_allow_html=True)
