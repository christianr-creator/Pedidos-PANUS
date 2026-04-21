import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import os

st.set_page_config(page_title="Dashboard PANUS", layout="wide")

@st.cache_data(ttl=60)
def cargar_datos_resumen():
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        
        # --- LÓGICA PARA DETECTAR SI ESTÁ EN LA NUBE O EN TU PC ---
        if "gcp_service_account" in st.secrets:
            # Si está en Streamlit Cloud, usa los Secrets
            creds_dict = dict(st.secrets["gcp_service_account"])
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        else:
            # Si está en tu PC, usa el archivo local
            ruta_actual = os.path.dirname(os.path.abspath(__file__))
            ruta_json = os.path.join(ruta_actual, "credenciales.json")
            creds = ServiceAccountCredentials.from_json_keyfile_name(ruta_json, scope)
        
        client = gspread.authorize(creds)
        spreadsheet = client.open("Ventas PANUS 2026")
        
        nombres_pestanas = [s.title for s in spreadsheet.worksheets()]
        sheet_name_final = next((s for s in nombres_pestanas if s.strip().upper() == "RESUMEN"), None)
        
        if not sheet_name_final:
            st.error("❌ No encontré la pestaña RESUMEN")
            return pd.DataFrame()

        sheet = spreadsheet.worksheet(sheet_name_final)
        all_values = sheet.get_all_values()
        
        df = pd.DataFrame(all_values[2:], columns=all_values[1])

        # Configuración de Día y OC
        nuevos_nombres = list(df.columns)
        nuevos_nombres[0] = 'Día'
        df.columns = nuevos_nombres
        df['indice_original'] = range(3, len(df) + 3)
        df['Día'] = df['Día'].replace('', None).ffill()
        
        if len(df.columns) >= 35:
            nuevos_nombres = list(df.columns)
            nuevos_nombres[34] = 'OC'
            df.columns = nuevos_nombres

        col_tienda = next((c for c in df.columns if 'Tienda' in c or 'Producto' in c), df.columns[1])
        df = df.rename(columns={col_tienda: 'Codigo Tienda / Producto'})
        df['Codigo Tienda / Producto'] = df['Codigo Tienda / Producto'].astype(str).str.strip()
        
        return df
    except Exception as e:
        st.error(f"Error detallado: {e}")
        return pd.DataFrame()
# --- INTERFAZ ---
st.title("📊 Análisis de Ventas PANUS")

df = cargar_datos_resumen()

if not df.empty:
    opcion = st.sidebar.radio("Menú:", ["Buscar por Tienda", "Reporte de Despachos"])

    # ---------------------------------------------------------
    # OPCIÓN 1: BUSCAR POR TIENDA (NO SE TOCA)
    # ---------------------------------------------------------
    if opcion == "Buscar por Tienda":
        st.subheader("🏪 Resumen de Pedido")
        lista_tiendas = sorted([
            t for t in df['Codigo Tienda / Producto'].unique() 
            if t and str(t).strip() != "" and str(t).upper().startswith(('T', 'E'))
        ])
        tienda_sel = st.selectbox("Selecciona Tienda:", lista_tiendas)

        if tienda_sel:
            datos_tienda = df[df['Codigo Tienda / Producto'] == tienda_sel]
            
            def es_valido(val):
                try:
                    return float(str(val).replace(',','.')) > 0
                except:
                    return False

            columnas_finales = ['Día', 'Codigo Tienda / Producto']
            for i in range(2, 31):
                if i < len(datos_tienda.columns):
                    col_actual = datos_tienda.columns[i]
                    if any(es_valido(x) for x in datos_tienda[col_actual]):
                        columnas_finales.append(col_actual)
            
            if 'OC' in datos_tienda.columns:
                if any(str(x).strip() != "" for x in datos_tienda['OC']):
                    columnas_finales.append('OC')
            
            columnas_finales = list(dict.fromkeys(columnas_finales))
            st.table(datos_tienda[columnas_finales])

    # ---------------------------------------------------------
    # OPCIÓN 2: REPORTE DE DESPACHOS (NUEVO ENFOQUE)
    # ---------------------------------------------------------
    elif opcion == "Reporte de Despachos":
        st.subheader("📅 Reporte de Despachos por Día")
        
        dias_semana = ["Lunes", "Martes", "Miercoles", "Jueves", "Viernes", "Sabado", "Domingo"]
        dia_sel = st.selectbox("Selecciona el Día de Despacho:", dias_semana)

        # Filtro 1: Por el día seleccionado
        # Filtro 2: Que empiecen con T o E
        df_dia = df[
            (df['Día'].astype(str).str.upper().str.contains(dia_sel.upper())) & 
            (df['Codigo Tienda / Producto'].str.upper().str.startswith(('T', 'E')))
        ].copy()

        if not df_dia.empty:
            # Separamos Capital (Filas < 214) e Interior (Filas >= 214)
            df_capital = df_dia[df_dia['indice_original'] < 214]
            df_interior = df_dia[df_dia['indice_original'] >= 214]

            # Función para limpiar columnas de cada bloque (solo productos con datos > 0)
            def filtrar_columnas_con_datos(df_bloque):
                if df_bloque.empty: return pd.DataFrame()
                
                def es_valido(val):
                    try: return float(str(val).replace(',','.')) > 0
                    except: return False
                
                cols_finales = ['Día', 'Codigo Tienda / Producto']
                # Revisamos productos C a AE
                for i in range(2, 31):
                    col = df_bloque.columns[i]
                    if any(es_valido(x) for x in df_bloque[col]):
                        cols_finales.append(col)
                
                if 'OC' in df_bloque.columns:
                    cols_finales.append('OC')
                
                return df_bloque[list(dict.fromkeys(cols_finales))]

            # Mostrar Capital
            st.markdown("### 🏘️ Tiendas Capital")
            if not df_capital.empty:
                st.table(filtrar_columnas_con_datos(df_capital))
            else:
                st.write("No hay despachos para Capital este día.")

            st.divider()

            # Mostrar Interior
            st.markdown("### 🚛 Tiendas Interior")
            if not df_interior.empty:
                st.table(filtrar_columnas_con_datos(df_interior))
            else:
                st.write("No hay despachos para el Interior este día.")
        else:
            st.warning(f"No se encontraron registros para el día {dia_sel} con tiendas T o E.")
