import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import os

st.set_page_config(page_title="Dashboard PANUS", layout="wide")

# --- 1. CSS PARA CABECERAS VERTICALES ---
st.markdown("""
    <style>
    th { vertical-align: bottom !important; text-align: center !important; height: 150px !important; }
    th > div {
        writing-mode: vertical-rl !important;
        transform: rotate(180deg) !important;
        white-space: nowrap !important;
        font-family: sans-serif !important;
        font-size: 13px !important;
    }
    </style>
""", unsafe_allow_html=True)

# --- 2. CONEXIÓN ---
def obtener_cliente():
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        # Esta línea permite que funcione en la nube usando los Secrets que ya configuraste
        if "gcp_service_account" in st.secrets:
            creds_dict = dict(st.secrets["gcp_service_account"])
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        else:
            # Esto es para cuando lo pruebes tú en tu PC
            ruta_json = os.path.join(os.path.dirname(__file__), "credenciales.json")
            creds = ServiceAccountCredentials.from_json_keyfile_name(ruta_json, scope)
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"Error de credenciales: {e}")
        return None

@st.cache_data(ttl=5)
def cargar_datos_seguro(nombre_archivo, nombre_pestana):
    client = obtener_cliente()
    if not client: return pd.DataFrame()
    
    try:
        sh = client.open(nombre_archivo)
    except gspread.exceptions.SpreadsheetNotFound:
        archivos_visibles = [f.get('name') for f in client.list_spreadsheet_files()]
        st.error(f"❌ No se encontró el archivo '{nombre_archivo}'")
        st.info(f"Archivos que sí puedo ver: {archivos_visibles}")
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Fallo al abrir libro: {e}")
        return pd.DataFrame()

    try:
        worksheets = sh.worksheets()
        target_ws = next((ws for ws in worksheets if ws.title.strip().lower() == nombre_pestana.lower()), None)
        
        if not target_ws:
            st.error(f"❌ Pestaña '{nombre_pestana}' no encontrada en {nombre_archivo}")
            return pd.DataFrame()

        lista_datos = target_ws.get_values()
        if not lista_datos or len(lista_datos) < 2: return pd.DataFrame()

        df = pd.DataFrame(lista_datos[2:], columns=lista_datos[1])
        df.columns.values[0] = 'Día'
        df['Día'] = df['Día'].replace('', None).ffill()
        df['idx_orig'] = range(3, len(df) + 3)
        df.columns.values[1] = 'Tienda_ID'
        df['Tienda_ID'] = df['Tienda_ID'].astype(str).str.strip()
        
        if len(df.columns) >= 35: df.columns.values[34] = 'OC'
        return df
    except Exception as e:
        st.error(f"Fallo crítico procesando datos: {e}")
        return pd.DataFrame()

# --- 3. INTERFAZ ---
st.sidebar.title("🚀 Panel de Control")
opcion = st.sidebar.radio("Ir a:", ["📅 Semana Actual", "📚 Historial"])

if opcion == "📅 Semana Actual":
    archivo, pestana = "Ventas PANUS 2026", "Resumen"
    st.title("📊 Semana Actual")
else:
    st.sidebar.subheader("Configuración Historial")
    # USAMOS LOS NOMBRES QUE CONFIRMASTE
    archivo = st.sidebar.selectbox("Selecciona el archivo:", ["Resumen Pedidos 2026", "Resumen Pedidos 2025"])
    
    client_aux = obtener_cliente()
    if client_aux:
        try:
            sh_h = client_aux.open(archivo)
            lista_p = [ws.title for ws in sh_h.worksheets()]
            pestana = st.sidebar.selectbox("Selecciona la Pestaña (Semana):", lista_p)
            st.title(f"📖 Historial: {archivo}")
        except Exception as e:
            st.sidebar.error(f"No se pudo acceder a {archivo}. Verifica que esté compartido con el correo del JSON.")
            pestana = None
    else:
        pestana = None

# --- 4. PROCESAMIENTO Y TABLAS ---
if archivo and pestana:
    df = cargar_datos_seguro(archivo, pestana)
    
    if not df.empty:
        st.sidebar.divider()
        tipo = st.sidebar.radio("Buscar:", ["🏪 Tienda Individual", "🚛 Despachos del Día"])
        
        if tipo == "🏪 Tienda Individual":
            tiendas = sorted([t for t in df['Tienda_ID'].unique() if str(t).upper().startswith(('T', 'E'))])
            sel = st.selectbox("Tienda:", tiendas)
            if sel:
                res = df[df['Tienda_ID'] == sel]
                cols_f = ['Día', 'Tienda_ID']
                for c in df.columns[2:31]:
                    if any(x for x in res[c] if str(x).strip() not in ['', '0', '0.0']):
                        cols_f.append(c)
                if 'OC' in df.columns: cols_f.append('OC')
                final = res[cols_f].copy()
                final.columns = [f"<div>{c}</div>" for c in final.columns]
                st.write(final.to_html(escape=False, index=False), unsafe_allow_html=True)
        
        else:
            dia = st.selectbox("Día:", ["Lunes", "Martes", "Miercoles", "Jueves", "Viernes", "Sabado", "Domingo"])
            df_dia = df[df['Día'].astype(str).str.upper().str.contains(dia.upper())]
            def dibujar(sub_df, titulo):
                st.subheader(titulo)
                if sub_df.empty: return
                c_dia = ['Día', 'Tienda_ID']
                for c in sub_df.columns[2:31]:
                    if any(x for x in sub_df[c] if str(x).strip() not in ['', '0', '0.0']): c_dia.append(c)
                if 'OC' in sub_df.columns: c_dia.append('OC')
                f = sub_df[list(dict.fromkeys(c_dia))].copy()
                f.columns = [f"<div>{x}</div>" for x in f.columns]
                st.write(f.to_html(escape=False, index=False), unsafe_allow_html=True)
            
            dibujar(df_dia[df_dia['idx_orig'] < 214], "🏘️ Capital")
            st.divider()
            dibujar(df_dia[df_dia['idx_orig'] >= 214], "🚛 Interior")
