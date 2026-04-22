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
    .header-zona { background-color: #f0f2f6; font-weight: bold; text-align: left !important; padding: 10px !important; border-top: 2px solid #d1d1d1; margin-top: 20px; color: #1f77b4; }
    </style>
""", unsafe_allow_html=True)

# --- 2. CONEXIÓN HÍBRIDA ---
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
        st.error(f"❌ Error de conexión: {e}")
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
    if not client: return [], [], pd.DataFrame(), []
    try:
        sh = client.open("Ventas PANUS 2026")
        ws = sh.worksheet("Resumen")
        datos = ws.get_values()
        if len(datos) < 2: return [], [], pd.DataFrame(), []
        
        # Cargamos el DataFrame
        df = pd.DataFrame(datos[2:], columns=limpiar_columnas(datos[1]))
        df.rename(columns={df.columns[0]: 'Día', df.columns[1]: 'Tienda_ID'}, inplace=True)
        
        # Mapeo de filas (datos[2] es la fila 3 del Excel)
        df['fila_excel'] = df.index + 3
        
        # --- LÓGICA DE FILAS ACTUALIZADA ---
        def clasificar_zona(fila):
            if 3 <= fila <= 212:
                return 'CAPITAL'
            elif fila >= 214:
                return 'INTERIOR'
            return 'OCULTO' # Fila 213 o encabezados
        
        df['Zona'] = df['fila_excel'].apply(clasificar_zona)
        df['Día'] = df['Día'].replace('', None).ffill()
        df['Tienda_ID'] = df['Tienda_ID'].astype(str).str.strip()
        
        excluir = ['Día', 'Tienda_ID', 'Zona', 'fila_excel', 'T.I.', 'T.C.G', 'T.M', 'OC', 'idx_orig', '']
        productos = [c for c in df.columns if c not in excluir and "_DUPLICADO_" not in c and not c.startswith('Col_')]
        
        # Solo tomamos tiendas válidas (que no sean vacías ni la fila de separación)
        tiendas = sorted([t for t in df[df['Zona'] != 'OCULTO']['Tienda_ID'].unique() if t and t != 'None'])
        dias = [d for d in df['Día'].unique().tolist() if d]
        
        return productos, tiendas, df, dias
    except Exception as e:
        st.error(f"❌ Error: {e}")
        return [], [], pd.DataFrame(), []

# --- 4. INTERFAZ ---
st.title("🥐 Sistema de Gestión PANUS")

lista_prod, lista_tiendas, df_actual, lista_dias = cargar_maestros()

if not lista_tiendas:
    st.stop()

st.sidebar.title("🚀 Menú Principal")
menu = st.sidebar.radio("Ir a:", ["📅 Semana Actual", "📚 Historial"])

if menu == "📅 Semana Actual":
    st.header("📊 Consulta de Ventas")
    opcion = st.radio("Selecciona vista:", ["Tienda Individual", "Día Completo (Por Zonas)"], horizontal=True)
    
    if opcion == "Tienda Individual":
        sel_t = st.selectbox("Selecciona Tienda:", [""] + lista_tiendas)
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
        sel_d = st.selectbox("Selecciona el Día:", [""] + lista_dias)
        if sel_d:
            df_dia = df_actual[df_actual['Día'] == sel_d].copy()
            
            for zona in ['CAPITAL', 'INTERIOR']:
                res_z = df_dia[df_dia['Zona'] == zona].copy()
                
                if not res_z.empty:
                    # Filtramos tiendas que realmente tengan algún pedido
                    # (opcional, para no ver filas de 0)
                    st.markdown(f"<div class='header-zona'>📍 TIENDAS DE LA {zona}</div>", unsafe_allow_html=True)
                    
                    cols_z = ['Tienda_ID']
                    fila_total = {'Tienda_ID': '<strong>SUBTOTAL</strong>'}
                    columnas_finales = []

                    for p in lista_prod:
                        if p in res_z.columns:
                            nums = pd.to_numeric(res_z[p], errors='coerce').fillna(0)
                            if nums.sum() > 0:
                                columnas_finales.append(p)
                                res_z[p] = nums.apply(lambda x: int(x) if x != 0 else "")
                                fila_total[p] = f"<strong>{int(nums.sum())}</strong>"
                    
                    mostrar_cols = cols_z + columnas_finales
                    if 'OC' in res_z.columns: mostrar_cols.append('OC')
                    
                    # Generar tabla
                    res_html = pd.concat([res_z[mostrar_cols], pd.DataFrame([fila_total])], ignore_index=True)
                    res_html.columns = [f"<div>{c}</div>" for c in res_html.columns]
                    st.write(res_html.to_html(escape=False, index=False), unsafe_allow_html=True)
