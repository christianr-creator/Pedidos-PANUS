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
    .header-zona { background-color: #262730; color: white; font-weight: bold; text-align: center !important; padding: 5px !important; margin-top: 15px; }
    </style>
""", unsafe_allow_html=True)

# --- 2. CONEXIÓN ---
def obtener_cliente():
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        if "gcp_service_account" in st.secrets:
            creds_dict = dict(st.secrets["gcp_service_account"])
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        else:
            import os
            ruta_json = os.path.join(os.path.dirname(__file__), "credenciales.json")
            creds = ServiceAccountCredentials.from_json_keyfile_name(ruta_json, scope)
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"Error de conexión: {e}")
        return None

def limpiar_columnas(columns):
    cols = []
    counts = {}
    for item in columns:
        item = item.strip() if item else ""
        if item in counts:
            counts[item] += 1
            cols.append(f"{item}_DUP_{counts[item]}")
        else:
            counts[item] = 1
            cols.append(item)
    return cols

# --- 3. CARGA DE DATOS ---
@st.cache_data(ttl=60)
def cargar_maestros():
    client = obtener_cliente()
    if not client: return [], [], pd.DataFrame(), []
    try:
        sh = client.open("Ventas PANUS 2026")
        ws = sh.worksheet("Resumen")
        datos = ws.get_values()
        df = pd.DataFrame(datos[2:], columns=limpiar_columnas(datos[1]))
        df.rename(columns={df.columns[0]: 'Día', df.columns[1]: 'Tienda_ID'}, inplace=True)
        
        df['fila_excel'] = df.index + 3
        
        # Filtro estricto T o E
        df['Valido'] = df['Tienda_ID'].apply(lambda x: str(x).strip().upper().startswith(('T', 'E')))
        df = df[df['Valido'] == True].copy()
        
        # Clasificación por filas
        df['Zona'] = df['fila_excel'].apply(lambda f: 'CAPITAL' if 3 <= f <= 212 else ('INTERIOR' if f >= 214 else 'SALTO'))
        df['Día'] = df['Día'].replace('', None).ffill()
        df['Tienda_ID'] = df['Tienda_ID'].astype(str).str.strip()
        
        excluir = ['Día', 'Tienda_ID', 'Zona', 'fila_excel', 'Valido', 'T.I.', 'T.C.G', 'T.M', 'OC', '']
        productos = [c for c in df.columns if c not in excluir and "_DUP_" not in c and not c.startswith('Col_')]
        tiendas = sorted([t for t in df[df['Zona'] != 'SALTO']['Tienda_ID'].unique() if t])
        dias = [d for d in df['Día'].unique().tolist() if d]
        
        return productos, tiendas, df, dias
    except: return [], [], pd.DataFrame(), []

# --- 4. INTERFAZ ---
st.title("🥐 Sistema de Gestión PANUS")
lista_prod, lista_tiendas, df_actual, lista_dias = cargar_maestros()

if not lista_tiendas:
    st.stop()

st.sidebar.title("🚀 Menú Principal")
menu = st.sidebar.radio("Ir a:", ["📅 Semana Actual", "📚 Historial"])

if menu == "📅 Semana Actual":
    opcion = st.radio("Ver por:", ["Tienda", "Día Completo"], horizontal=True)
    
    if opcion == "Tienda":
        sel_t = st.selectbox("Tienda:", [""] + lista_tiendas)
        if sel_t:
            res = df_actual[df_actual['Tienda_ID'] == sel_t].copy()
            cols = ['Día', 'Tienda_ID']
            for p in lista_prod:
                if p in res.columns:
                    val = pd.to_numeric(res[p], errors='coerce').fillna(0)
                    if val.sum() > 0:
                        cols.append(p); res[p] = val.apply(lambda x: int(x) if x != 0 else "")
            if 'OC' in res.columns: cols.append('OC')
            st.write(res[cols].to_html(escape=False, index=False), unsafe_allow_html=True)

    else:
        sel_d = st.selectbox("Día:", [""] + lista_dias)
        if sel_d:
            df_dia = df_actual[(df_actual['Día'] == sel_d) & (df_actual['Zona'] != 'SALTO')].copy()
            cols_con_datos = [p for p in lista_prod if p in df_dia.columns and pd.to_numeric(df_dia[p], errors='coerce').sum() > 0]
            
            fila_total = {'Tienda_ID': '<strong>TOTAL</strong>'}
            for zona in ['CAPITAL', 'INTERIOR']:
                df_z = df_dia[df_dia['Zona'] == zona].copy()
                if not df_z.empty:
                    st.markdown(f"<div class='header-zona'>📍 {zona}</div>", unsafe_allow_html=True)
                    for p in cols_con_datos:
                        nums = pd.to_numeric(df_z[p], errors='coerce').fillna(0)
                        df_z[p] = nums.apply(lambda x: int(x) if x != 0 else "")
                        fila_total[p] = fila_total.get(p, 0) + int(nums.sum())
                    
                    c_ver = ['Tienda_ID'] + cols_con_datos
                    if 'OC' in df_z.columns: c_ver.append('OC')
                    st.write(df_z[c_ver].to_html(escape=False, index=False), unsafe_allow_html=True)

            # TOTAL FINAL
            for p in cols_con_datos: fila_total[p] = f"<strong>{fila_total[p]}</strong>"
            st.markdown("---")
            df_tot = pd.DataFrame([fila_total])
            cols_t = ['Tienda_ID'] + cols_con_datos
            if 'OC' in df_dia.columns: cols_t.append('OC'); df_tot['OC'] = '---'
            st.write(df_tot[cols_t].to_html(escape=False, index=False), unsafe_allow_html=True)

else:
    # --- RESTAURACIÓN DEL HISTORIAL ---
    st.header("📚 Historial y Buscador Anual")
    archivo_h = st.sidebar.selectbox("Seleccionar Año:", ["Resumen Pedidos 2026", "Resumen Pedidos 2025"])
    id_busq = st.selectbox("Selecciona la tienda para el rastreo:", [""] + lista_tiendas)
    
    if st.button("Iniciar Rastreo Anual") and id_busq != "":
        client = obtener_cliente()
        if client:
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
                df_tmp['Día'] = df_tmp['Día'].replace('', None).ffill()
                
                match = df_tmp[df_tmp['Tienda_ID'].astype(str).str.strip().str.lower() == id_busq.lower()].copy()
                if not match.empty:
                    match['Semana'] = ws.title
                    lista_res.append(match)
            
            prog.empty()
            if lista_res:
                df_g = pd.concat(lista_res, ignore_index=True, sort=False)
                cols_p = []
                fila_t_h = {'Semana': '---', 'Día': '---', 'Tienda_ID': '<strong>TOTAL ANUAL</strong>'}
                
                for p in lista_prod:
                    if p in df_g.columns:
                        nums = pd.to_numeric(df_g[p], errors='coerce').fillna(0)
                        if nums.sum() > 0:
                            cols_p.append(p)
                            df_g[p] = nums.apply(lambda x: int(x) if x != 0 else "")
                            fila_t_h[p] = f"<strong>{int(nums.sum())}</strong>"
                
                c_fin = ['Semana', 'Día', 'Tienda_ID'] + cols_p
                if 'OC' in df_g.columns: c_fin.append('OC'); fila_t_h['OC'] = '---'
                
                res_g = pd.concat([df_g[c_fin], pd.DataFrame([fila_t_h])], ignore_index=True)
                st.write(res_g.to_html(escape=False, index=False), unsafe_allow_html=True)
            else:
                st.warning("No se encontraron registros para esta tienda en el año seleccionado.")
