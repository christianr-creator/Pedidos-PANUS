import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd

# --- 1. CONFIGURACIÓN ---
st.set_page_config(page_title="Dashboard PANUS", layout="wide")

st.markdown("""
    <style>
    th { vertical-align: bottom !important; text-align: center !important; height: 150px !important; }
    th > div { writing-mode: vertical-rl !important; transform: rotate(180deg) !important; white-space: nowrap !important; font-family: sans-serif !important; font-size: 13px !important; }
    td { white-space: nowrap !important; text-align: center !important; padding: 0 10px !important; }
    </style>
""", unsafe_allow_html=True)

# --- 2. CONEXIÓN ---
def obtener_cliente():
    try:
        if "gcp_service_account" not in st.secrets:
            st.error("❌ Secrets no configurados.")
            return None
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"❌ Error: {e}")
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

# --- 3. CARGA DE DATOS ---
@st.cache_data(ttl=60)
def cargar_maestros():
    client = obtener_cliente()
    if not client: return [], [], pd.DataFrame()
    try:
        sh = client.open("Ventas PANUS 2026")
        ws = sh.worksheet("Resumen")
        datos = ws.get_values()
        if len(datos) < 2: return [], [], pd.DataFrame()
        
        df = pd.DataFrame(datos[2:], columns=limpiar_columnas(datos[1]))
        df.rename(columns={df.columns[0]: 'Día', df.columns[1]: 'Tienda_ID'}, inplace=True)
        
        # --- CORRECCIÓN AQUÍ: RELLENAR DÍAS VACÍOS ---
        df['Día'] = df['Día'].replace('', None).ffill()
        
        df['Tienda_ID'] = df['Tienda_ID'].astype(str).str.strip()
        
        excluir = ['Día', 'Tienda_ID', 'T.I.', 'T.C.G', 'T.M', 'OC', 'idx_orig', '']
        productos = [c for c in df.columns if c not in excluir and "_DUPLICADO_" not in c and not c.startswith('Col_')]
        tiendas = sorted([t for t in df['Tienda_ID'].unique() if str(t).upper().startswith(('T', 'E'))])
        
        return productos, tiendas, df
    except Exception as e:
        st.error(f"❌ Error: {e}")
        return [], [], pd.DataFrame()

# --- 4. INTERFAZ ---
st.title("🥐 Sistema de Gestión PANUS")

with st.spinner("Actualizando datos..."):
    lista_prod, lista_tiendas, df_actual = cargar_maestros()

if not lista_tiendas:
    st.stop()

st.sidebar.title("🚀 Menú Principal")
menu = st.sidebar.radio("Ir a:", ["📅 Semana Actual", "📚 Historial"])

if menu == "📅 Semana Actual":
    sel = st.selectbox("Seleccionar Tienda:", lista_tiendas)
    if sel:
        res = df_actual[df_actual['Tienda_ID'] == sel].copy()
        
        # Seleccionamos columnas con datos
        cols_vivas = ['Día', 'Tienda_ID']
        for p in lista_prod:
            if p in res.columns:
                val = pd.to_numeric(res[p], errors='coerce').fillna(0)
                if val.sum() > 0:
                    cols_vivas.append(p)
                    res[p] = val.apply(lambda x: int(x) if x != 0 else "")
        
        if 'OC' in res.columns: cols_vivas.append('OC')
        
        # Mostramos tabla
        st.write(res[cols_vivas].to_html(escape=False, index=False), unsafe_allow_html=True)

else:
    archivo_h = st.sidebar.selectbox("Año:", ["Resumen Pedidos 2026", "Resumen Pedidos 2025"])
    id_busq = st.selectbox("Selecciona la tienda para rastreo anual:", [""] + lista_tiendas)
    
    if st.button("Iniciar Rastreo") and id_busq:
        client = obtener_cliente()
        sh = client.open(archivo_h)
        hojas = [ws for ws in sh.worksheets() if ws.title.lower() not in ['resumen', 'config', 'indices', 'totales', 'base']]
        
        lista_res = []
        prog = st.progress(0)
        for i, ws in enumerate(hojas):
            prog.progress((i+1)/len(hojas))
            rows = ws.get_values()
            if len(rows) < 3: continue
            
            df_tmp = pd.DataFrame(rows[2:], columns=limpiar_columnas(rows[1]))
            df_tmp.rename(columns={df_tmp.columns[0]: 'Día', df_tmp.columns[1]: 'Tienda_ID'}, inplace=True)
            
            # --- TAMBIÉN RELLENAMOS DÍA EN EL HISTORIAL ---
            df_tmp['Día'] = df_tmp['Día'].replace('', None).ffill()
            df_tmp['Tienda_ID'] = df_tmp['Tienda_ID'].astype(str).str.strip()
            
            match = df_tmp[df_tmp['Tienda_ID'].str.lower() == id_busq.lower()].copy()
            if not match.empty:
                match['Semana'] = ws.title
                lista_res.append(match)
        
        prog.empty()
        if lista_res:
            df_g = pd.concat(lista_res, ignore_index=True, sort=False)
            cols_p = []
            fila_t = {'Semana': '---', 'Día': '---', 'Tienda_ID': '<strong>TOTAL</strong>'}
            
            for p in lista_prod:
                if p in df_g.columns:
                    nums = pd.to_numeric(df_g[p], errors='coerce').fillna(0)
                    if nums.sum() > 0:
                        cols_p.append(p)
                        df_g[p] = nums.apply(lambda x: int(x) if x != 0 else "")
                        fila_t[p] = f"<strong>{int(nums.sum())}</strong>"
            
            c_fin = ['Semana', 'Día', 'Tienda_ID'] + cols_p
            if 'OC' in df_g.columns: 
                c_fin.append('OC')
                fila_t['OC'] = '---'
            
            res_g = pd.concat([df_g[c_fin], pd.DataFrame([fila_t])], ignore_index=True)
            st.write(res_g.to_html(escape=False, index=False), unsafe_allow_html=True)
