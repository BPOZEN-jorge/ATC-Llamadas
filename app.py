import json
import random
import time as time_lib
from datetime import datetime
from zoneinfo import ZoneInfo
import pandas as pd
import streamlit as st
from github import Github, GithubException

# ==========================================
# CONFIGURACIÓN DE PÁGINA
# ==========================================
st.set_page_config(
    page_title="Ruleta de Transferencias ATC a Ventas",
    page_icon="📞",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ARCHIVO DE PERSISTENCIA EN GITHUB
FILE_ATC_VENTAS = "atc_ventas_ruleta.json"

# ==========================================
# INICIALIZACIÓN DE ESTADO PARA LIMPIEZA DE FORMULARIO
# ==========================================
if "input_telefono" not in st.session_state:
    st.session_state["input_telefono"] = ""
if "input_agente_atc" not in st.session_state:
    st.session_state["input_agente_atc"] = ""

def limpiar_campos():
    """Limpia las variables del formulario en st.session_state mediante callback."""
    st.session_state["input_telefono"] = ""
    st.session_state["input_agente_atc"] = ""

# ==========================================
# DATOS INICIALES DE AGENTES ATC QUE TRANSFIEREN
# ==========================================
AGENTES_ATC_INICIALES = [
    "Wensly Hurtado",
    "Lizeth Vanessa Cifuentes",
    "Camila Blandon",
    "Daniela Ramirez",
    "Geraldine Arrieta",
    "Esmeralda Garcia",
    "Mitchell Morales",
    "Evelin Rios Zuleta",
    "Wendys Johanna Garavito",
    "Erika Buritica",
    "Barbara Fratello",
    "Yully Buitrago",
    "Maria del Pilar Galindo",
    "Lorena Botero",
    "Yiseth Daniela Moreno",
    "Diana Castro",
    "Gonzalo Mejia",
    "Jhon Benjumea",
    "Johnny Llano",
    "Mariana Sierra",
    "Paula Andrea Vanegas Serna",
    "MIGUEL ANGEL ZUÑIGA MOSQUERA",
    "Yurley Palacios Córdoba",
    "Britney Valentina Niño Fuentes",
    "Raymar Carolina Ramírez Martínez",
    "Nataly De castro Henao",
    "Katerin Johana Gutiérrez villa",
    "Glendys Sayago Sayago",
    "Mariana Marulanda Mesa",
    "Nazlin Yudith Robledo Blando",
    "dany isaza",
    "maria fernanda",
    "María José Hernández Aldana",
    "Joyke Machacon Suarez"
]

# ==========================================
# DATOS INICIALES DE USUARIOS (VENTAS)
# ==========================================
USUARIOS_INICIALES = [
    {"posicion": 1, "real": "Alisson Correa Gaviria", "alias": "Alisson"},
    {"posicion": 2, "real": "Ana Maria Sanchez Gamboa", "alias": "Maria Sanchez"},
    {"posicion": 3, "real": "Andrea Mileidy londoño Bedoya", "alias": "Andrea Valverde"},
    {"posicion": 4, "real": "Angie Valeria Quirama Hernández", "alias": "Valeria Hernandez"},
    {"posicion": 5, "real": "Angie Vanessa García", "alias": "Maria Antonia García"},
    {"posicion": 6, "real": "Brayan Andrey Bustamante", "alias": "Marcos Garcia"},
    {"posicion": 7, "real": "Carlos Alberto Herrera Cardeño", "alias": "Carlos Herrera / Alberto Fernandez"},
    {"posicion": 8, "real": "Claudia Marcela Manco Vargas", "alias": "Marcela"},
    {"posicion": 9, "real": "Cristian David Acosta Montoya", "alias": "Manuel Vasquez"},
    {"posicion": 10, "real": "Dayana Botero Rojas", "alias": "Isabel Botero"},
    {"posicion": 11, "real": "Evelin Acevedo Cortés", "alias": "Gabriela"},
    {"posicion": 12, "real": "Gustavo Adolfo Barrientos Serna", "alias": "Gustavo"},
    {"posicion": 13, "real": "Iris Sabiana Cano Cano", "alias": "Maria Cano"},
    {"posicion": 14, "real": "Janis Henao Vasco", "alias": "María José"},
    {"posicion": 15, "real": "Johana Osorio Bedoya", "alias": "Johana Sanchez"},
    {"posicion": 16, "real": "Juan Esteban Acevedo Garces", "alias": "Juan Esteban"},
    {"posicion": 17, "real": "Juan Sebastian Serna Sepulveda", "alias": "Juan Sebastian"},
    {"posicion": 18, "real": "Julián Andrés Osorio Aristizabal", "alias": "Andrés Aristizábal"},
    {"posicion": 19, "real": "Karen Herrera Gonzalez", "alias": "Karen"},
    {"posicion": 20, "real": "Kelly Jhoana Salas Ibarguen", "alias": "Kelly Salas"},
    {"posicion": 21, "real": "Libia Paola Romero Cantillo", "alias": "Paola Romero"},
    {"posicion": 22, "real": "Linda Liceth Pérez Pineda", "alias": "Linda Pérez / Elena Pérez"},
    {"posicion": 23, "real": "Luis Alberto Lozano Ibarra", "alias": "Luis Lozano"},
    {"posicion": 24, "real": "Manuela villegas Giraldo", "alias": "Manuela Villegas"},
    {"posicion": 25, "real": "María Karolina Viana Cancio", "alias": "Karolina"},
    {"posicion": 26, "real": "Mateo Cano Hincapié", "alias": "Antonio de la villa"},
    {"posicion": 27, "real": "Omar David Barboza Carbonero", "alias": "Omar"},
    {"posicion": 28, "real": "Oscar José Llanos Mendinueta", "alias": "Oscar"},
    {"posicion": 29, "real": "Paula Andrea Guzman Jaramillo", "alias": "Paula"},
    {"posicion": 30, "real": "Rosa Elvira Agamez López", "alias": "Flor Lopez"},
    {"posicion": 31, "real": "Sara Gómez Bayona", "alias": "Sara Gómez"},
    {"posicion": 32, "real": "Stefany Vanegas Arbelaez", "alias": "Stefany"},
    {"posicion": 33, "real": "Tatiana Magreth Acevedo Marín", "alias": "Tatiana"},
    {"posicion": 34, "real": "Tomas Castaño Gómez", "alias": "Tomas"},
    {"posicion": 35, "real": "Viviana Pacheco Córdoba", "alias": "Viviana Gómez"},
    {"posicion": 36, "real": "Yarlen Biviana Son Cedeño", "alias": "Maria Rodriguez"},
    {"posicion": 37, "real": "Yarnedis Cecilia Urrutia Pérez", "alias": "Cecilia López"},
    {"posicion": 38, "real": "Yeismer Miranda Ramirez", "alias": "Leo Miranda"},
    {"posicion": 39, "real": "Yesica Paola Lopez Arango", "alias": "Yesica López"},
    {"posicion": 40, "real": "Yesly Marilyn Carrero Rivera", "alias": "Marilyn Carrero"},
]

def obtener_fecha_hora_colombia() -> datetime:
    """Retorna objeto datetime actual en Zona Horaria de Colombia."""
    return datetime.now(ZoneInfo("America/Bogota"))

def obtener_hora_colombia_str() -> str:
    """Retorna la fecha y hora actual formateada en hora de Colombia."""
    return obtener_fecha_hora_colombia().strftime("%Y-%m-%d %H:%M:%S")

# ==========================================
# CONEXIÓN Y OPERACIONES EN GITHUB
# ==========================================
def obtener_repositorio_github():
    token = st.secrets.get("github", {}).get("token")
    repo_name = st.secrets.get("github", {}).get("repo")
    if not token or not repo_name:
        st.error("⚠️ Configuración incompleta de GitHub en los secretos (`st.secrets`).")
        st.stop()
    g = Github(token)
    return g.get_repo(repo_name)

def leer_json_github(file_path: str, default_payload: dict) -> dict:
    repo = obtener_repositorio_github()
    branch = st.secrets.get("github", {}).get("branch", "main")
    try:
        content = repo.get_contents(file_path, ref=branch)
        return json.loads(content.decoded_content.decode("utf-8"))
    except GithubException as e:
        if e.status == 404:
            escribir_json_github(file_path, default_payload, f"Inicializar {file_path}")
            return default_payload
        st.error(f"Error leyendo {file_path}: {e}")
        st.stop()

def escribir_json_github(file_path: str, payload: dict, mensaje_commit: str, retries: int = 3):
    repo = obtener_repositorio_github()
    branch = st.secrets.get("github", {}).get("branch", "main")
    json_str = json.dumps(payload, indent=4, ensure_ascii=False)

    for intento in range(retries):
        try:
            try:
                content = repo.get_contents(file_path, ref=branch)
                repo.update_file(
                    path=file_path,
                    message=f"Auto-update: {mensaje_commit}",
                    content=json_str,
                    sha=content.sha,
                    branch=branch
                )
            except GithubException as ex:
                if ex.status == 404:
                    repo.create_file(
                        path=file_path,
                        message=f"Crear archivo: {mensaje_commit}",
                        content=json_str,
                        branch=branch
                    )
                else:
                    raise ex
            return True
        except GithubException as e:
            if intento < retries - 1:
                time_lib.sleep(0.5)
            else:
                st.error(f"❌ Error al guardar en {file_path} tras varios intentos: {e}")
                return False

# ==========================================
# LÓGICA DE NEGOCIO Y PERSISTENCIA
# ==========================================
def obtener_datos_atc() -> tuple[list, list]:
    def_payload = {
        "turnos": USUARIOS_INICIALES,
        "historial": []
    }
    data = leer_json_github(FILE_ATC_VENTAS, def_payload)
    turnos = sorted(data.get("turnos", USUARIOS_INICIALES), key=lambda x: x["posicion"])
    historial = data.get("historial", [])
    return turnos, historial

def buscar_transferencia_previa(telefono: str) -> dict | None:
    """Busca en el historial si el número de teléfono ya fue derivado previamente."""
    telefono_clean = telefono.strip()
    if not telefono_clean:
        return None
    _, historial = obtener_datos_atc()
    return next((h for h in historial if h.get("telefono") == telefono_clean), None)

def procesar_transferencia(
    telefono: str, 
    agente_atc_nombre: str, 
    modo_reasignacion: str = "siguiente"
) -> tuple[bool, str]:
    telefono_clean = telefono.strip()
    agente_atc_clean = agente_atc_nombre.strip()

    if not telefono_clean:
        return False, "⚠️ Debes ingresar un número de teléfono válido."
    if not agente_atc_clean:
        return False, "⚠️ Debes seleccionar qué agente ATC está realizando la transferencia."

    turnos, historial = obtener_datos_atc()
    now_col = obtener_hora_colombia_str()

    if modo_reasignacion == "mismo":
        previo = next((h for h in historial if h.get("telefono") == telefono_clean), None)
        if not previo:
            return False, "❌ No se encontró registro previo para reasignar a este cliente."
        
        agente_asignado_real = previo["agente_ventas_real"]
        agente_asignado_alias = previo["agente_ventas_alias"]
        
        nuevo_registro = {
            "id": len(historial) + 1,
            "telefono": telefono_clean,
            "agente_atc": agente_atc_clean,
            "agente_ventas_real": agente_asignado_real,
            "agente_ventas_alias": agente_asignado_alias,
            "tipo": "Reasignado al Mismo Agente",
            "fecha_hora": now_col
        }
        historial.insert(0, nuevo_registro)
        nuevos_turnos = turnos

    else:  # Modo 'siguiente'
        agente_asignado = turnos[0]
        agente_asignado_real = agente_asignado["real"]
        agente_asignado_alias = agente_asignado["alias"]

        nuevo_registro = {
            "id": len(historial) + 1,
            "telefono": telefono_clean,
            "agente_atc": agente_atc_clean,
            "agente_ventas_real": agente_asignado_real,
            "agente_ventas_alias": agente_asignado_alias,
            "tipo": "Siguiente en Ruleta",
            "fecha_hora": now_col
        }
        historial.insert(0, nuevo_registro)

        # Rotar ruleta: El primero pasa al final
        nuevos_turnos = turnos[1:] + [agente_asignado]
        for idx, t in enumerate(nuevos_turnos, start=1):
            t["posicion"] = idx

    data_payload = {
        "turnos": nuevos_turnos,
        "historial": historial
    }

    if escribir_json_github(FILE_ATC_VENTAS, data_payload, f"Transferencia cliente {telefono_clean} a {agente_asignado_alias}"):
        return True, f"✅ Transferencia exitosa. Cliente `{telefono_clean}` asignado a **{agente_asignado_alias}** ({agente_asignado_real})."
    else:
        return False, "❌ Error de comunicación con GitHub. Reintenta la operación."

def vaciar_historial_atc():
    turnos, _ = obtener_datos_atc()
    data = {"turnos": turnos, "historial": []}
    escribir_json_github(FILE_ATC_VENTAS, data, "Admin: Vaciar historial ATC")

def reiniciar_turnos_originales_atc():
    _, historial = obtener_datos_atc()
    data = {"turnos": [dict(u) for u in USUARIOS_INICIALES], "historial": historial}
    escribir_json_github(FILE_ATC_VENTAS, data, "Admin: Restablecer ruleta ATC al orden inicial")

def reorganizar_turnos_al_azar_atc():
    turnos, historial = obtener_datos_atc()
    random.shuffle(turnos)
    for idx, t in enumerate(turnos, start=1):
        t["posicion"] = idx
    data = {"turnos": turnos, "historial": historial}
    escribir_json_github(FILE_ATC_VENTAS, data, "Admin: Reorganizar ruleta ATC al azar")

# ==========================================
# INTERFAZ Y NAVEGACIÓN
# ==========================================
st.sidebar.title("📌 Módulo ATC a Ventas")
opcion_vista = st.sidebar.radio("Navegación:", ["🎧 Transferir a Ventas", "🛡️ Vista Administrador"])

# ------------------------------------------
# VISTA 1: TRANSFERIR A VENTAS
# ------------------------------------------
if opcion_vista == "🎧 Transferir a Ventas":
    st.title("📞 Ruleta de Transferencias Libre: ATC ➔ Ventas")
    st.caption(f"Hora Colombia: `{obtener_hora_colombia_str()}`")
    st.caption("Ingresa el número del cliente para transferir libremente al ejecutivo de Ventas disponible.")

    turnos_actuales, _ = obtener_datos_atc()
    siguiente_agente = turnos_actuales[0] if turnos_actuales else None

    st.markdown("---")
    col_info, col_form = st.columns([2, 3])

    with col_info:
        st.subheader("🎯 Próximo Agente en Ruleta")
        if siguiente_agente:
            st.metric(label="RECIBE TRANSFERENCIA", value=siguiente_agente["alias"])
            st.write(f"👤 **Nombre Real:** {siguiente_agente['real']}")
            st.caption("Si el ejecutivo de ventas no responde, realiza el salto y la ruleta rotará automáticamente al siguiente.")
        else:
            st.error("No hay agentes configurados en la lista.")

    with col_form:
        st.subheader("📋 Datos de la Transferencia")
        
        # Inputs vinculados a st.session_state
        telefono_input = st.text_input(
            "📱 Teléfono del Cliente:", 
            key="input_telefono", 
            placeholder="Ej: 3001234567"
        )
        
        agente_atc_selected = st.selectbox(
            "🎧 Agente ATC que transfiere:", 
            [""] + AGENTES_ATC_INICIALES,
            key="input_agente_atc"
        )

        # VALIDACIÓN DE DUPLICADOS EN TIEMPO REAL
        registro_previo = buscar_transferencia_previa(telefono_input) if telefono_input else None

        if registro_previo:
            st.warning(
                f"⚠️ **¡Cliente recurrente detectado!**\n\n"
                f"El número `{telefono_input.strip()}` ya fue transferido anteriormente a "
                f"**{registro_previo['agente_ventas_alias']}** ({registro_previo['agente_ventas_real']}) "
                f"el día `{registro_previo['fecha_hora']}`."
            )
            
            st.write("Elige cómo deseas proceder:")
            col_b1, col_b2 = st.columns(2)
            
            with col_b1:
                if st.button("🔄 Reasignar al Mismo Agente", use_container_width=True, type="secondary", on_click=limpiar_campos):
                    exito, msj = procesar_transferencia(
                        telefono=telefono_input,
                        agente_atc_nombre=agente_atc_selected,
                        modo_reasignacion="mismo"
                    )
                    if exito:
                        st.success(msj)
                        time_lib.sleep(1.2)
                        st.rerun()
                    else:
                        st.error(msj)

            with col_b2:
                if st.button("➡️ Omitir y Asignar al Siguiente", use_container_width=True, type="primary", on_click=limpiar_campos):
                    exito, msj = procesar_transferencia(
                        telefono=telefono_input,
                        agente_atc_nombre=agente_atc_selected,
                        modo_reasignacion="siguiente"
                    )
                    if exito:
                        st.success(msj)
                        time_lib.sleep(1.2)
                        st.rerun()
                    else:
                        st.error(msj)

        else:
            # Botón libre de transferencia con callback on_click
            if st.button("🚀 Transferir Cliente Libremente ➡️", use_container_width=True, type="primary", on_click=limpiar_campos):
                exito, msj = procesar_transferencia(
                    telefono=telefono_input,
                    agente_atc_nombre=agente_atc_selected,
                    modo_reasignacion="siguiente"
                )
                if exito:
                    st.success(msj)
                    time_lib.sleep(1.2)
                    st.rerun()
                else:
                    st.error(msj)

    st.markdown("---")
    st.subheader("📋 Orden Actual de la Ruleta (Ventas)")
    tabla_display = [
        {
            "Posición": t["posicion"],
            "Nombre Real": t["real"],
            "Alias / Sistema": t["alias"]
        } for t in turnos_actuales
    ]
    st.dataframe(pd.DataFrame(tabla_display), use_container_width=True, hide_index=True)

# ------------------------------------------
# VISTA 2: ADMINISTRADOR
# ------------------------------------------
elif opcion_vista == "🛡️ Vista Administrador":
    st.title("🛡️ Panel de Control Administrador - ATC a Ventas")

    if "admin_logged" not in st.session_state:
        st.session_state.admin_logged = False

    if not st.session_state.admin_logged:
        with st.form("form_admin_pass"):
            admin_pass = st.text_input("Contraseña de Administrador:", type="password")
            btn_admin = st.form_submit_button("Ingresar", use_container_width=True)

        if btn_admin:
            if admin_pass == st.secrets.get("passwords", {}).get("admin_password", "admin123"):
                st.session_state.admin_logged = True
                st.success("✅ Acceso concedido.")
                st.rerun()
            else:
                st.error("❌ Contraseña incorrecta.")

    else:
        if st.sidebar.button("Cerrar Sesión Admin", use_container_width=True):
            st.session_state.admin_logged = False
            st.rerun()

        st.subheader("📊 Historial de Transferencias ATC ➔ Ventas")
        _, historial = obtener_datos_atc()

        if not historial:
            st.info("Aún no se han registrado transferencias.")
        else:
            df_historial = pd.DataFrame(historial).rename(columns={
                "id": "ID Reg",
                "telefono": "Teléfono Cliente",
                "agente_atc": "Atendido Por (ATC)",
                "agente_ventas_real": "Asignado A (Ventas)",
                "agente_ventas_alias": "Alias Ventas",
                "tipo": "Tipo Asignación",
                "fecha_hora": "Fecha / Hora (Colombia)"
            })
            st.dataframe(df_historial, use_container_width=True, hide_index=True)

            csv_data = df_historial.to_csv(index=False).encode("utf-8")
            st.download_button(
                label="📥 Descargar Reporte CSV de Transferencias",
                data=csv_data,
                file_name=f"reporte_transferencias_atc_{obtener_fecha_hora_colombia().strftime('%Y%m%d_%H%M')}.csv",
                mime="text/csv",
                use_container_width=True
            )

        st.markdown("---")
        st.subheader("⚙️ Opciones de Reordenamiento y Limpieza de Ruleta")
        
        col_adm1, col_adm2, col_adm3 = st.columns(3)

        with col_adm1:
            st.markdown("### 🎲 Rebobinar Ruleta al Azar")
            st.caption("Mezcla las posiciones actuales de la ruleta al azar.")
            confirm_random = st.checkbox("Confirmo mezclar al azar.", key="chk_rnd")
            if st.button("🔀 Mezclar Orden", disabled=not confirm_random, type="primary", use_container_width=True):
                reorganizar_turnos_al_azar_atc()
                st.success("✅ Ruleta reorganizada al azar.")
                st.rerun()

        with col_adm2:
            st.markdown("### 🔄 Restablecer Orden Inicial")
            st.caption("Restablece la ruleta al orden alfabético inicial.")
            confirm_reset = st.checkbox("Confirmo reiniciar orden.", key="chk_rst")
            if st.button("Restablecer Fila", disabled=not confirm_reset, use_container_width=True):
                reiniciar_turnos_originales_atc()
                st.success("✅ Orden de ruleta restablecido.")
                st.rerun()

        with col_adm3:
            st.markdown("### 🗑️ Limpiar Historial")
            st.caption("Borra todos los registros acumulados de transferencias.")
            confirm_del = st.checkbox("Confirmo vaciar historial.", key="chk_del")
            if st.button("Vaciar Historial", disabled=not confirm_del, use_container_width=True):
                vaciar_historial_atc()
                st.success("✅ Historial de transferencias vaciado.")
                st.rerun()