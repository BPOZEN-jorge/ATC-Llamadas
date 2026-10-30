import base64
import hmac
import json
import random
import time as time_lib
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st
from github import Github, GithubException

# ==========================================
# CONFIGURACIÓN DE PÁGINA
# ==========================================
st.set_page_config(
    page_title="Turnero de Transferencias ATC a Ventas",
    page_icon="📞",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ARCHIVOS DE PERSISTENCIA EN GITHUB
FILE_ATC_VENTAS = "atc_ventas_ruleta.json"   # Fila, historial de transferencias y cambios de estado
FILE_LOG_SALTOS = "atc_saltos_log.json"      # Log independiente con la foto de la fila en cada salto

# Rotación: primero el coordinador (en este orden) y luego un asesor suyo
COORDINADORES = ["Jose", "Paula", "Victor"]
SIGUIENTES_A_MOSTRAR = 6     # Turno disponible + próximos
REFRESCO_SEGUNDOS = 5        # Actualización automática del panel de turnos
MAX_INTENTOS_PIN = 5         # Intentos de PIN por sesión del ATC

# Tipos de registro en el historial
TIPO_TRANSFERIDO = "Transferido (turno)"            # Cuenta como salto
TIPO_TRANSFERIDO_ANTERIOR = "Siguiente en Ruleta"   # Registros de la versión anterior (también cuentan)
TIPO_NO_DISPONIBLE = "No disponible (saltado)"       # No cuenta como transferencia, pero pasa al final de su grupo
TIPO_REASIGNADO = "Reasignado al Mismo Agente"       # Cliente recurrente: no mueve la rotación
TIPOS_QUE_CUENTAN = {TIPO_TRANSFERIDO, TIPO_TRANSFERIDO_ANTERIOR}

# Tipos de cambio de estado
TIPO_INACTIVO = "INACTIVO"
TIPO_REACTIVADO = "REACTIVADO"
TIPO_RESET_DIARIO = "RESET_DIARIO"
MOTIVO_LLEGADA = "Llegada / inicio de jornada"

# ==========================================
# INICIALIZACIÓN DE ESTADO PARA FORMULARIO
# ==========================================
if "input_telefono" not in st.session_state:
    st.session_state["input_telefono"] = ""
if "limpiar_formulario" not in st.session_state:
    st.session_state["limpiar_formulario"] = False

# Si se marcó la bandera de limpieza en la ejecución anterior, limpiamos
if st.session_state["limpiar_formulario"]:
    st.session_state["input_telefono"] = ""
    st.session_state["input_call_id"] = ""
    st.session_state["pin_atc"] = ""
    st.session_state["limpiar_formulario"] = False

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
# DATOS INICIALES DE USUARIOS (VENTAS) Y SU COORDINADOR
# ==========================================
USUARIOS_INICIALES = [
    {"posicion": 1, "real": "Alisson Correa Gaviria", "alias": "Alisson", "coordinador": "Paula"},
    {"posicion": 2, "real": "Ana Maria Sanchez Gamboa", "alias": "Maria Sanchez", "coordinador": "Paula"},
    {"posicion": 3, "real": "Andrea Mileidy londoño Bedoya", "alias": "Andrea Valverde", "coordinador": "Paula"},
    {"posicion": 4, "real": "Angie Valeria Quirama Hernández", "alias": "Valeria Hernandez", "coordinador": "Victor"},
    {"posicion": 5, "real": "Angie Vanessa García", "alias": "Maria Antonia García", "coordinador": "Jose"},
    {"posicion": 6, "real": "Brayan Andrey Bustamante", "alias": "Marcos Garcia", "coordinador": "Paula"},
    {"posicion": 7, "real": "Carlos Alberto Herrera Cardeño", "alias": "Carlos Herrera / Alberto Fernandez", "coordinador": "Jose"},
    {"posicion": 8, "real": "Claudia Marcela Manco Vargas", "alias": "Marcela", "coordinador": "Paula"},
    {"posicion": 9, "real": "Cristian David Acosta Montoya", "alias": "Manuel Vasquez", "coordinador": "Jose"},
    {"posicion": 10, "real": "Dayana Botero Rojas", "alias": "Isabel Botero", "coordinador": "Jose"},
    {"posicion": 11, "real": "Evelin Acevedo Cortés", "alias": "Gabriela", "coordinador": "Victor"},
    {"posicion": 12, "real": "Gustavo Adolfo Barrientos Serna", "alias": "Gustavo", "coordinador": "Victor"},
    {"posicion": 13, "real": "Iris Sabiana Cano Cano", "alias": "Maria Cano", "coordinador": "Paula"},
    {"posicion": 14, "real": "Janis Henao Vasco", "alias": "María José", "coordinador": "Victor"},
    {"posicion": 15, "real": "Johana Osorio Bedoya", "alias": "Johana Sanchez", "coordinador": "Paula"},
    {"posicion": 16, "real": "Juan Esteban Acevedo Garces", "alias": "Juan Esteban", "coordinador": "Jose"},
    {"posicion": 17, "real": "Juan Sebastian Serna Sepulveda", "alias": "Juan Sebastian", "coordinador": "Paula"},
    {"posicion": 18, "real": "Karen Herrera Gonzalez", "alias": "Karen", "coordinador": "Victor"},
    {"posicion": 19, "real": "Libia Paola Romero Cantillo", "alias": "Paola Romero", "coordinador": "Victor"},
    {"posicion": 20, "real": "Linda Liceth Pérez Pineda", "alias": "Linda Pérez / Elena Pérez", "coordinador": "Paula"},
    {"posicion": 21, "real": "Luis Alberto Lozano Ibarra", "alias": "Luis Lozano", "coordinador": "Paula"},
    {"posicion": 22, "real": "Manuela villegas Giraldo", "alias": "Manuela Villegas", "coordinador": "Jose"},
    {"posicion": 23, "real": "María Karolina Viana Cancio", "alias": "Karolina", "coordinador": "Victor"},
    {"posicion": 24, "real": "Mateo Cano Hincapié", "alias": "Antonio de la villa", "coordinador": "Jose"},
    {"posicion": 25, "real": "Omar David Barboza Carbonero", "alias": "Omar", "coordinador": "Paula"},
    {"posicion": 26, "real": "Oscar José Llanos Mendinueta", "alias": "Oscar", "coordinador": "Jose"},
    {"posicion": 27, "real": "Paula Andrea Guzman Jaramillo", "alias": "Paula", "coordinador": "Paula"},
    {"posicion": 28, "real": "Rosa Elvira Agamez López", "alias": "Flor Lopez", "coordinador": "Paula"},
    {"posicion": 29, "real": "Sara Gómez Bayona", "alias": "Sara Gómez", "coordinador": "Jose"},
    {"posicion": 30, "real": "Tatiana Magreth Acevedo Marín", "alias": "Tatiana", "coordinador": "Victor"},
    {"posicion": 31, "real": "Tomas Castaño Gómez", "alias": "Tomas", "coordinador": "Paula"},
    {"posicion": 32, "real": "Viviana Pacheco Córdoba", "alias": "Viviana Gómez", "coordinador": "Victor"},
    {"posicion": 33, "real": "Yarlen Biviana Son Cedeño", "alias": "Maria Rodriguez", "coordinador": "Paula"},
    {"posicion": 34, "real": "Yarnedis Cecilia Urrutia Pérez", "alias": "Cecilia López", "coordinador": "Jose"},
    {"posicion": 35, "real": "Yeismer Miranda Ramirez", "alias": "Leo Miranda", "coordinador": "Victor"},
    {"posicion": 36, "real": "Yesica Paola Lopez Arango", "alias": "Yesica López", "coordinador": "Victor"},
    {"posicion": 37, "real": "Yesly Marilyn Carrero Rivera", "alias": "Marilyn Carrero", "coordinador": "Victor"},
]
COORDINADOR_POR_AGENTE = {u["real"]: u["coordinador"] for u in USUARIOS_INICIALES}


def obtener_fecha_hora_colombia() -> datetime:
    """Retorna objeto datetime actual en Zona Horaria de Colombia."""
    return datetime.now(ZoneInfo("America/Bogota"))


def obtener_hora_colombia_str() -> str:
    """Retorna la fecha y hora actual formateada en hora de Colombia."""
    return obtener_fecha_hora_colombia().strftime("%Y-%m-%d %H:%M:%S")


def hoy_colombia() -> str:
    return obtener_fecha_hora_colombia().strftime("%Y-%m-%d")


# ==========================================
# CONEXIÓN Y OPERACIONES ATÓMICAS EN GITHUB
# ==========================================
@st.cache_resource(show_spinner=False)
def _conectar_repo(token: str, repo_name: str):
    """Se reutiliza la conexión: evita una llamada extra a la API de GitHub en cada lectura/escritura."""
    return Github(token).get_repo(repo_name)


def obtener_repositorio_github():
    token = st.secrets.get("github", {}).get("token")
    repo_name = st.secrets.get("github", {}).get("repo")
    if not token or not repo_name:
        st.error("⚠️ Configuración incompleta de GitHub en los secretos (`st.secrets`).")
        st.stop()
    return _conectar_repo(token, repo_name)


class ConflictoGithub(Exception):
    """Otro usuario guardó el mismo archivo entre nuestra lectura y nuestra escritura."""


def sha_leido(file_path: str):
    """SHA de la última lectura de este archivo en esta ejecución (para escritura segura)."""
    return st.session_state.get(f"_sha_{file_path}")


def ejecutar_con_reintentos(operacion, intentos: int = 6):
    """
    Ejecuta una operación de lectura+escritura. Si otro usuario guardó en medio (ConflictoGithub),
    se repite TODA la operación con datos frescos. Así nunca se pisan los saltos de dos ATC.
    """
    for _ in range(intentos):
        try:
            return operacion()
        except ConflictoGithub:
            time_lib.sleep(0.2 + random.random() * 0.6)
    return False, "❌ Muchas personas guardaron al mismo tiempo. Espera un momento e intenta nuevamente."


def _leer_contenido(file_path: str):
    """Devuelve (datos, sha) o (None, None) si el archivo no existe."""
    repo = obtener_repositorio_github()
    branch = st.secrets.get("github", {}).get("branch", "main")
    try:
        content = repo.get_contents(file_path, ref=branch)
    except GithubException as e:
        if e.status == 404:
            return None, None
        raise
    if getattr(content, "encoding", None) == "base64":
        raw_data = content.decoded_content.decode("utf-8")
    else:
        # Para archivos > 1MB la API no trae el contenido: se consulta el blob por su SHA
        blob = repo.get_git_blob(content.sha)
        raw_data = base64.b64decode(blob.content).decode("utf-8")
    return json.loads(raw_data), content.sha


def leer_json_github(file_path: str, default_payload: dict) -> dict:
    """Lectura fresca (para operaciones que van a escribir). Guarda el SHA leído."""
    try:
        data, sha = _leer_contenido(file_path)
    except GithubException as e:
        st.error(f"Error leyendo {file_path}: {e}")
        st.stop()
    if data is None:
        escribir_json_github(file_path, default_payload, f"Inicializar {file_path}")
        return json.loads(json.dumps(default_payload))
    st.session_state[f"_sha_{file_path}"] = sha
    return data


@st.cache_data(ttl=3, show_spinner=False)
def leer_para_mostrar(file_path: str) -> dict | None:
    """
    Lectura compartida entre todas las sesiones durante 3 s, solo para MOSTRAR (panel que se
    refresca solo). Las acciones siempre leen fresco. Así no se agota el límite de la API de GitHub.
    """
    data, _ = _leer_contenido(file_path)
    return data


def escribir_json_github(file_path: str, payload: dict, mensaje_commit: str, retries: int = 3,
                         sha_esperado: str | None = None):
    """
    Guarda un JSON en GitHub.
    - Con sha_esperado (el SHA de la lectura): escritura segura. Si otro usuario guardó en medio,
      GitHub responde 409 y se lanza ConflictoGithub para repetir la operación con datos frescos.
    - Sin sha_esperado: escritura directa (solo para crear archivos que no existen).
    """
    repo = obtener_repositorio_github()
    branch = st.secrets.get("github", {}).get("branch", "main")
    json_str = json.dumps(payload, indent=4, ensure_ascii=False)

    if sha_esperado is not None:
        try:
            resultado = repo.update_file(
                path=file_path,
                message=f"Auto-update: {mensaje_commit}",
                content=json_str,
                sha=sha_esperado,
                branch=branch,
            )
            st.session_state[f"_sha_{file_path}"] = resultado["content"].sha
            leer_para_mostrar.clear()
            return True
        except GithubException as e:
            if e.status == 409 or (e.status == 422 and "sha" in str(e.data).lower()):
                raise ConflictoGithub(file_path) from e
            st.error(f"❌ Error al guardar en {file_path}: {e}")
            return False

    for intento in range(retries):
        try:
            try:
                content = repo.get_contents(file_path, ref=branch)
                repo.update_file(
                    path=file_path,
                    message=f"Auto-update: {mensaje_commit}",
                    content=json_str,
                    sha=content.sha,
                    branch=branch,
                )
            except GithubException as ex:
                if ex.status == 404:
                    repo.create_file(
                        path=file_path,
                        message=f"Crear archivo: {mensaje_commit}",
                        content=json_str,
                        branch=branch,
                    )
                else:
                    raise ex
            leer_para_mostrar.clear()
            return True
        except GithubException as e:
            if intento < retries - 1:
                time_lib.sleep(0.5)
            else:
                st.error(f"❌ Error al guardar en {file_path} tras varios intentos: {e}")
                return False


def guardar_turnero(data: dict, mensaje: str) -> bool:
    return escribir_json_github(FILE_ATC_VENTAS, data, mensaje, sha_esperado=sha_leido(FILE_ATC_VENTAS))


# ==========================================
# LOG INDEPENDIENTE DE SALTOS (FOTO DE LA FILA)
# ==========================================
def guardar_eventos_log_salto(eventos: list):
    """Guarda uno o varios registros en atc_saltos_log.json (un solo commit)."""
    if not eventos:
        return
    primero = eventos[0]
    if len(eventos) == 1:
        msg = f"Log {primero.get('tipo')}: {primero.get('alias')} - {str(primero.get('motivo', ''))[:60]}"
    else:
        msg = f"Log cambios de estado: {len(eventos)} agentes - {str(primero.get('motivo', ''))[:60]}"

    # El log se reintenta por su cuenta: el cambio principal ya quedó guardado.
    for _ in range(5):
        log_actual = leer_json_github(FILE_LOG_SALTOS, {"saltos": []})
        log_actual.setdefault("saltos", [])
        for ev in eventos:
            ev["id_evento"] = len(log_actual["saltos"]) + 1
            log_actual["saltos"].insert(0, dict(ev))
        try:
            escribir_json_github(FILE_LOG_SALTOS, log_actual, msg, sha_esperado=sha_leido(FILE_LOG_SALTOS))
            return
        except ConflictoGithub:
            time_lib.sleep(0.3 + random.random() * 0.7)
    st.warning("⚠️ El cambio se guardó, pero no se pudo escribir en el log de saltos (mucha concurrencia).")


def obtener_log_saltos_df() -> pd.DataFrame:
    saltos = (leer_para_mostrar(FILE_LOG_SALTOS) or {}).get("saltos", [])
    if not saltos:
        return pd.DataFrame()
    return pd.DataFrame([{
        "ID Evento": s.get("id_evento"),
        "Tipo": s.get("tipo"),
        "Fecha/Hora (Colombia)": s.get("fecha_hora"),
        "Teléfono": s.get("telefono", ""),
        "Agente (Alias)": s.get("alias"),
        "Agente (Real)": s.get("nombre_real"),
        "Coordinador": s.get("coordinador", ""),
        "ATC": s.get("agente_atc", ""),
        "Motivo": s.get("motivo", ""),
        "Solapado": "⚠️ Sí" if s.get("solapado") else "",
        "Registrado por": s.get("registrado_por", ""),
        "Siguientes en ese momento": " → ".join(s.get("siguientes_snapshot", [])),
    } for s in saltos]).astype(str)


# ==========================================
# ESTRUCTURA DEL TURNERO
# ==========================================
def _default_turnero() -> dict:
    return {
        "turnos": [dict(u, activo=False) for u in USUARIOS_INICIALES],
        "historial": [],
        "puntero_coordinador": 0,
        "cambios_estado": [],
    }


def _normalizar_turnero(data: dict) -> dict:
    """
    Completa campos nuevos sin borrar nada de la versión anterior (historial incluido).
    Cada agente toma su coordinador de la tabla; 'activo' por defecto es False.
    """
    data.setdefault("historial", [])
    data.setdefault("puntero_coordinador", 0)
    data.setdefault("cambios_estado", [])
    turnos = data.get("turnos") or [dict(u) for u in USUARIOS_INICIALES]
    existentes = {t["real"] for t in turnos}
    turnos += [dict(u, activo=False) for u in USUARIOS_INICIALES if u["real"] not in existentes]
    for t in turnos:
        t["coordinador"] = COORDINADOR_POR_AGENTE.get(t["real"], t.get("coordinador", ""))
        t["activo"] = bool(t.get("activo", False))
    data["turnos"] = sorted(turnos, key=lambda x: x.get("posicion", 999))
    return data


def obtener_turnero_fresco() -> dict:
    return _normalizar_turnero(leer_json_github(FILE_ATC_VENTAS, _default_turnero()))


def obtener_turnero_para_mostrar() -> dict:
    data = leer_para_mostrar(FILE_ATC_VENTAS)
    return _normalizar_turnero(json.loads(json.dumps(data)) if data else _default_turnero())


def estadisticas_hoy(data: dict) -> dict:
    """
    Por agente, solo HOY (hora Colombia), a partir del historial:
    - transferencias: las que cuentan para la prioridad.
    - no_disponible / reasignaciones: informativas.
    - ultimo_turno: último momento en que le tocó (transferencia o no disponible) -> rotación.
    """
    hoy = hoy_colombia()
    stats = {}
    for h in data.get("historial", []):
        fecha = str(h.get("fecha_hora", ""))
        real = h.get("agente_ventas_real")
        if not real or not fecha.startswith(hoy):
            continue
        s = stats.setdefault(real, {"transferencias": 0, "no_disponible": 0, "reasignaciones": 0,
                                    "ultimo_turno": "", "ultima_transferencia": ""})
        tipo = h.get("tipo")
        if tipo in TIPOS_QUE_CUENTAN:
            s["transferencias"] += 1
            s["ultima_transferencia"] = max(s["ultima_transferencia"], fecha)
            s["ultimo_turno"] = max(s["ultimo_turno"], fecha)
        elif tipo == TIPO_NO_DISPONIBLE:
            s["no_disponible"] += 1
            s["ultimo_turno"] = max(s["ultimo_turno"], fecha)
        elif tipo == TIPO_REASIGNADO:
            s["reasignaciones"] += 1
    return stats


def _orden_del_dia(coordinador: str, nombres: list) -> dict:
    """Sorteo al azar de los asesores de cada coordinador, fijo durante el día (todos ven lo mismo)."""
    orden = sorted(nombres)
    random.Random(f"{hoy_colombia()}|{coordinador}").shuffle(orden)
    return {n: i for i, n in enumerate(orden)}


def calcular_siguientes(data: dict, cantidad: int = SIGUIENTES_A_MOSTRAR) -> list:
    """
    Próximos turnos (el primero es el TURNO ACTUAL):
    1) Coordinador en rotación Jose → Paula → Victor (se salta al que no tenga asesores disponibles).
    2) Dentro del coordinador: menos transferencias hoy → hace más tiempo que no le toca → sorteo del día.
    Solo asesores ACTIVOS.
    """
    stats = estadisticas_hoy(data)
    por_coord = {}
    for c in COORDINADORES:
        candidatos = [t for t in data["turnos"]
                      if t.get("activo") and t.get("coordinador") == c]
        sorteo = _orden_del_dia(c, [t["real"] for t in candidatos])
        candidatos.sort(key=lambda t: (stats.get(t["real"], {}).get("transferencias", 0),
                                       stats.get(t["real"], {}).get("ultimo_turno", ""),
                                       sorteo[t["real"]]))
        por_coord[c] = candidatos

    puntero = int(data.get("puntero_coordinador", 0)) % len(COORDINADORES)
    usados = {c: 0 for c in COORDINADORES}
    resultado = []
    while len(resultado) < cantidad:
        for salto in range(len(COORDINADORES)):
            c = COORDINADORES[(puntero + salto) % len(COORDINADORES)]
            if usados[c] < len(por_coord[c]):
                t = por_coord[c][usados[c]]
                usados[c] += 1
                resultado.append({"real": t["real"], "alias": t["alias"], "coordinador": c})
                puntero = (puntero + salto + 1) % len(COORDINADORES)
                break
        else:
            break  # No quedan asesores disponibles
    return resultado


def _agente(data: dict, real: str) -> dict:
    return next(t for t in data["turnos"] if t["real"] == real)


def _registro_historial(data: dict, **campos) -> dict:
    reg = {"id": len(data["historial"]) + 1, "fecha_hora": obtener_hora_colombia_str(), **campos}
    data["historial"].insert(0, reg)
    return reg


# ==========================================
# ACCIONES DEL ATC: REGISTRAR EL SALTO CON SU PIN
# ==========================================
def atc_por_pin(pin: str) -> str | None:
    """El PIN identifica al ATC (secrets [pins]): no tiene que seleccionar su nombre."""
    pin_clean = (pin or "").strip()
    if not pin_clean:
        return None
    encontrado = None
    for nombre, correcto in st.secrets.get("pins", {}).items():
        if hmac.compare_digest(pin_clean.encode(), str(correcto).strip().encode()):
            encontrado = nombre
    return encontrado


def _evento_log(tipo: str, agente: dict, agente_atc: str, siguientes: list, **extra) -> dict:
    return {
        "tipo": tipo,
        "fecha_hora": obtener_hora_colombia_str(),
        "nombre_real": agente["real"],
        "alias": agente["alias"],
        "coordinador": agente.get("coordinador", ""),
        "agente_atc": agente_atc,
        "siguientes_snapshot": [f"{s['alias']} ({s['coordinador']})" for s in siguientes],
        **extra,
    }


def registrar_salto_atc(tipo: str, pin: str, real_visto: str | None, telefono: str = "", call_id: str = "",
                        motivo: str = "", forzar: bool = False) -> tuple[str, str]:
    """
    Registra el salto del TURNO DISPONIBLE que el ATC tenía en pantalla.
    - tipo TIPO_TRANSFERIDO: cuenta como transferencia.  TIPO_NO_DISPONIBLE (un solo botón, sin motivo): no cuenta, pasa al siguiente.
    - Se valida (con escritura atómica) que ese asesor siga siendo el turno disponible. Si otro ATC lo
      registró en esos segundos, devuelve 'cambio' para preguntar, en vez de asignar a otro en silencio.
    - forzar=True: el ATC confirma que SÍ transfirió a ese asesor; se registra marcado como solapado.
    Devuelve (codigo, mensaje) con codigo 'ok' | 'cambio' | 'pin' | 'error'.
    """
    atc = atc_por_pin(pin)
    if not atc:
        return "pin", "❌ PIN incorrecto. Escribe tu PIN de ATC de 4 dígitos."
    telefono_clean, call_id_clean, motivo_clean = telefono.strip(), call_id.strip(), motivo.strip()
    if tipo == TIPO_TRANSFERIDO and not telefono_clean:
        return "error", "⚠️ Debes ingresar el teléfono del cliente."
    if not real_visto:
        return "error", "⚠️ No hay un turno disponible en pantalla. Espera a que se actualice."

    def operacion():
        data = obtener_turnero_fresco()
        siguientes = calcular_siguientes(data)
        actual = siguientes[0] if siguientes else None
        agente = next((t for t in data["turnos"] if t["real"] == real_visto), None)
        if not agente:
            return "error", "❌ El asesor ya no está en la fila. Actualiza la página."
        coincide = bool(actual) and actual["real"] == real_visto
        if not coincide and not forzar:
            ahora = f" Ahora el turno disponible es **{actual['alias']}** ({actual['coordinador']})." if actual else ""
            return "cambio", f"⚠️ **{agente['alias']}** ya no es el turno disponible: otro ATC acaba de registrarle un salto.{ahora}"

        _registro_historial(
            data, telefono=telefono_clean, call_id=call_id_clean, agente_atc=atc,
            agente_ventas_real=agente["real"], agente_ventas_alias=agente["alias"],
            coordinador=agente["coordinador"], tipo=tipo, motivo=motivo_clean, solapado=not coincide,
        )
        if coincide:  # la rotación de coordinadores avanza solo con el turno que tocaba
            data["puntero_coordinador"] = (COORDINADORES.index(agente["coordinador"]) + 1) % len(COORDINADORES)
        if tipo == TIPO_TRANSFERIDO:
            mensaje = f"Transferencia cliente {telefono_clean} a {agente['alias']} (ATC {atc})"
        else:
            mensaje = f"No disponible: {agente['alias']} (ATC {atc})"
        if not guardar_turnero(data, mensaje + (" [solapado]" if not coincide else "")):
            return "error", "❌ Hubo un fallo temporal de comunicación con GitHub. Intenta nuevamente."
        guardar_eventos_log_salto([_evento_log(tipo, agente, atc, siguientes, telefono=telefono_clean,
                                               call_id=call_id_clean, motivo=motivo_clean, solapado=not coincide)])
        nuevo = calcular_siguientes(data, cantidad=1)
        sigue = f" Ahora el turno disponible es **{nuevo[0]['alias']}** ({nuevo[0]['coordinador']})." if nuevo else ""
        if tipo == TIPO_TRANSFERIDO:
            return "ok", f"✅ {atc}: transferencia registrada → **{agente['alias']}** (cliente `{telefono_clean}`).{sigue}"
        return "ok", f"⏭️ {atc}: **{agente['alias']}** quedó como no disponible.{sigue}"

    resultado = ejecutar_con_reintentos(operacion)
    return ("error", resultado[1]) if resultado[0] is False else resultado


def buscar_transferencia_previa(telefono: str) -> dict | None:
    """Busca en el historial si el número de teléfono ya fue derivado previamente."""
    telefono_clean = telefono.strip()
    if not telefono_clean:
        return None
    historial = obtener_turnero_para_mostrar()["historial"]
    return next((h for h in historial if h.get("telefono") == telefono_clean
                 and h.get("tipo") != TIPO_NO_DISPONIBLE), None)


def reasignar_al_mismo(pin: str, telefono: str) -> tuple[str, str]:
    """Cliente recurrente: se envía a su asesor anterior. No mueve la rotación."""
    atc = atc_por_pin(pin)
    if not atc:
        return "pin", "❌ PIN incorrecto. Escribe tu PIN de ATC de 4 dígitos."
    telefono_clean = telefono.strip()

    def operacion():
        data = obtener_turnero_fresco()
        previo = next((h for h in data["historial"] if h.get("telefono") == telefono_clean
                       and h.get("tipo") != TIPO_NO_DISPONIBLE), None)
        if not previo:
            return "error", "❌ No se encontró registro previo para reasignar a este cliente."
        _registro_historial(
            data, telefono=telefono_clean, call_id="", agente_atc=atc,
            agente_ventas_real=previo["agente_ventas_real"], agente_ventas_alias=previo["agente_ventas_alias"],
            coordinador=COORDINADOR_POR_AGENTE.get(previo["agente_ventas_real"], ""), tipo=TIPO_REASIGNADO,
        )
        if guardar_turnero(data, f"Reasignación cliente {telefono_clean} a {previo['agente_ventas_alias']} (ATC {atc})"):
            return "ok", f"✅ {atc}: cliente `{telefono_clean}` reasignado a **{previo['agente_ventas_alias']}** (no mueve el turno)."
        return "error", "❌ Hubo un fallo temporal de comunicación con GitHub. Intenta nuevamente."

    resultado = ejecutar_con_reintentos(operacion)
    return ("error", resultado[1]) if resultado[0] is False else resultado


# ==========================================
# ACTIVO / INACTIVO (ADMIN)
# ==========================================
def _validar_registrado_por(registrado_por: str):
    """Quien hace el cambio debe identificarse."""
    nombre = (registrado_por or "").strip()
    if len(nombre) < 2:
        return None, "⚠️ Escribe tu nombre en **Tu nombre (admin)** en la barra lateral antes de guardar cambios."
    return nombre, None


def guardar_cambios_estado_admin(estados_seleccionados: dict, motivo: str, registrado_por: str) -> tuple[bool, str]:
    """
    estados_seleccionados: {nombre_real: activo(bool)} SOLO con los interruptores que el admin movió.
    Si otro admin ya lo dejó en ese estado, no se toca (no se duplica ni se revierte).
    """
    motivo_clean = motivo.strip()
    registrado_por_clean, error = _validar_registrado_por(registrado_por)
    if error:
        return False, error

    def operacion():
        data = obtener_turnero_fresco()
        estado_actual = {t["real"]: t["activo"] for t in data["turnos"]}
        cambios = [(n, v) for n, v in estados_seleccionados.items() if n in estado_actual and estado_actual[n] != v]
        if not cambios:
            if estados_seleccionados:
                return False, "ℹ️ No hay nada que guardar: esa(s) persona(s) ya estaban en ese estado (quizá otro admin lo hizo)."
            return False, "ℹ️ No moviste ningún interruptor."
        if len(motivo_clean) < 5:
            return False, "⚠️ Debes escribir el motivo del cambio de estado (mínimo 5 caracteres)."

        now_col = obtener_hora_colombia_str()
        siguientes = [f"{s['alias']} ({s['coordinador']})" for s in calcular_siguientes(data)]
        eventos = []
        for nombre, nuevo_activo in cambios:
            agente = _agente(data, nombre)
            agente["activo"] = nuevo_activo
            ev = {
                "fecha_hora": now_col,
                "tipo": TIPO_REACTIVADO if nuevo_activo else TIPO_INACTIVO,
                "nombre_real": nombre,
                "alias": agente["alias"],
                "coordinador": agente["coordinador"],
                "motivo": motivo_clean,
                "registrado_por": registrado_por_clean,
            }
            data["cambios_estado"].insert(0, ev)
            eventos.append(dict(ev, siguientes_snapshot=siguientes))

        resumen = ", ".join(f"{e['alias']}→{'Activo' if e['tipo'] == TIPO_REACTIVADO else 'Inactivo'}" for e in eventos)
        if guardar_turnero(data, f"Admin: estados ({resumen[:120]}) - Motivo: {motivo_clean[:60]}"):
            guardar_eventos_log_salto(eventos)
            return True, f"✅ Se guardaron {len(eventos)} cambio(s) de estado: {resumen}"
        return False, "❌ Hubo un fallo temporal de comunicación con GitHub. Intenta nuevamente."
    return ejecutar_con_reintentos(operacion)


def registrar_llegada(nombre_real: str, registrado_por: str) -> tuple[bool, str]:
    return guardar_cambios_estado_admin({nombre_real: True}, MOTIVO_LLEGADA, registrado_por)


def horas_activacion_hoy(data: dict) -> dict:
    """llegada = primera activación de hoy; activo_desde = última activación de hoy."""
    hoy = hoy_colombia()
    horas = {}
    for c in data.get("cambios_estado", []):
        fecha = str(c.get("fecha_hora", ""))
        nombre = c.get("nombre_real")
        if c.get("tipo") != TIPO_REACTIVADO or not nombre or not fecha.startswith(hoy):
            continue
        h = horas.setdefault(nombre, {"llegada": fecha, "activo_desde": fecha})
        h["llegada"] = min(h["llegada"], fecha)
        h["activo_desde"] = max(h["activo_desde"], fecha)
    return horas


# ==========================================
# RESET DIARIO 00:00 (HORA COLOMBIA)
# ==========================================
def aplicar_reset_diario_si_corresponde():
    """
    En la PRIMERA carga de la app después de las 00:00 (hora Colombia) todos quedan inactivos,
    y la rotación empieza otra vez por el primer coordinador.
    """
    hoy = hoy_colombia()
    if st.session_state.get("reset_diario_verificado") == hoy:
        return

    def operacion():
        data = obtener_turnero_fresco()
        if data.get("ultimo_reset_diario", "") >= hoy:
            return None
        for t in data["turnos"]:
            t["activo"] = False
        data["puntero_coordinador"] = 0
        data["ultimo_reset_diario"] = hoy
        data["cambios_estado"].insert(0, {
            "fecha_hora": obtener_hora_colombia_str(),
            "tipo": TIPO_RESET_DIARIO,
            "nombre_real": "TODOS",
            "alias": "TODOS",
            "coordinador": "",
            "motivo": "Reset automático 00:00 (hora Colombia)",
            "registrado_por": "Sistema",
        })
        return guardar_turnero(data, f"Auto: Reset diario 00:00 - todos inactivos ({hoy})")

    resultado = ejecutar_con_reintentos(operacion)
    if resultado is True or resultado is None:  # None = ya estaba hecho hoy
        st.session_state.reset_diario_verificado = hoy  # si falló, se reintenta en la próxima carga


def vaciar_historial_atc(registrado_por: str):
    def operacion():
        data = obtener_turnero_fresco()
        data["historial"] = []
        return guardar_turnero(data, f"Admin: Vaciar historial ATC ({registrado_por})")
    return ejecutar_con_reintentos(operacion)


# ==========================================
# INTERFAZ Y NAVEGACIÓN
# ==========================================
aplicar_reset_diario_si_corresponde()

st.sidebar.title("📌 Turnero ATC a Ventas")
opcion_vista = st.sidebar.radio("Navegación:", ["🎧 Transferir a Ventas", "🛡️ Vista Administrador"])


def _hora(fecha: str) -> str:
    return fecha[11:16] if fecha else "—"


@st.fragment(run_every=REFRESCO_SEGUNDOS)
def panel_turnos():
    """Turno disponible y siguientes. Se actualiza solo para que nadie vea un turno desactualizado."""
    data = obtener_turnero_para_mostrar()
    siguientes = calcular_siguientes(data)

    if siguientes:
        actual = siguientes[0]
        # Lo que el ATC tiene en pantalla: al registrar se valida que siga siendo el disponible.
        st.session_state["turno_visto"] = actual["real"]
        st.metric(label=f"🎯 TURNO DISPONIBLE · Coordinador {actual['coordinador']}", value=actual["alias"])
        st.caption(f"👤 {actual['real']}")
        if len(siguientes) > 1:
            st.markdown("**Siguen:**")
            st.dataframe(pd.DataFrame([
                {"#": i, "Asesor": s["alias"], "Coordinador": s["coordinador"]}
                for i, s in enumerate(siguientes[1:], start=2)
            ]), use_container_width=True, hide_index=True)
    else:
        st.session_state["turno_visto"] = None
        st.error("⚠️ No hay asesores activos disponibles en este momento.")

    hoy = hoy_colombia()
    ultimo = next((h for h in data["historial"] if str(h.get("fecha_hora", "")).startswith(hoy)
                   and h.get("tipo") in (TIPO_TRANSFERIDO, TIPO_NO_DISPONIBLE)), None)
    if ultimo:
        st.caption(f"Último salto: **{ultimo['agente_ventas_alias']}** · {ultimo['tipo']} · "
                   f"ATC {ultimo.get('agente_atc', '')} · {_hora(ultimo['fecha_hora'])}")
    st.caption(f"Actualizado: {obtener_hora_colombia_str()[11:]} · se refresca cada {REFRESCO_SEGUNDOS} s")


def _resultado_atc(codigo: str, msj: str, limpiar: bool = True):
    if codigo == "ok":
        st.session_state["intentos_pin"] = 0
        if limpiar:
            st.session_state["limpiar_formulario"] = True
        st.session_state["aviso_atc"] = msj
        st.rerun()
    if codigo == "pin":
        st.session_state["intentos_pin"] = st.session_state.get("intentos_pin", 0) + 1
        if st.session_state["intentos_pin"] >= MAX_INTENTOS_PIN:
            st.rerun()  # muestra el bloqueo de inmediato
        msj += f" Intentos restantes: {MAX_INTENTOS_PIN - st.session_state['intentos_pin']}."
    st.error(msj)


# ------------------------------------------
# VISTA 1: TRANSFERIR A VENTAS (ATC)
# ------------------------------------------
if opcion_vista == "🎧 Transferir a Ventas":
    st.title("📞 Turnero de Transferencias: ATC ➔ Ventas")
    st.caption(
        f"Hora Colombia: `{obtener_hora_colombia_str()}` · Rotación por coordinador: "
        f"{' → '.join(COORDINADORES)} → … y dentro de cada uno, el asesor con menos transferencias hoy."
    )

    aviso = st.session_state.pop("aviso_atc", None)
    if aviso:
        st.success(aviso)

    # Turno que el ATC tenía en pantalla ANTES de pulsar (el panel se recalcula en esta misma ejecución)
    turno_visto = st.session_state.get("turno_visto")

    col_info, col_form = st.columns([2, 3])
    with col_info:
        panel_turnos()

    with col_form:
        conflicto = st.session_state.get("conflicto_turno")
        bloqueado = st.session_state.get("intentos_pin", 0) >= MAX_INTENTOS_PIN

        if bloqueado:
            st.error("🔒 Demasiados PIN incorrectos. Recarga la página para intentarlo de nuevo.")
        elif conflicto:
            st.subheader("⚠️ El turno cambió")
            st.warning(conflicto["mensaje"])
            st.write(f"¿Ya le transferiste la llamada a **{conflicto['alias']}**?")
            c1, c2 = st.columns(2)
            with c1:
                if st.button(f"Sí, la transferí a {conflicto['alias']}", type="primary", use_container_width=True):
                    st.session_state.pop("conflicto_turno", None)
                    _resultado_atc(*registrar_salto_atc(
                        TIPO_TRANSFERIDO, conflicto["pin"], conflicto["real"],
                        conflicto["telefono"], conflicto["call_id"], forzar=True))
            with c2:
                if st.button("No, la transfiero al nuevo turno", use_container_width=True):
                    st.session_state.pop("conflicto_turno", None)
                    st.rerun()
        else:
            st.subheader("📋 Registrar el salto")
            st.caption("Transfiere la llamada al **turno disponible** y registra aquí con tu PIN.")
            telefono_input = st.text_input(
                "📱 Teléfono del Cliente:", key="input_telefono", placeholder="Ej: +573001234567, +14155552671..."
            )
            call_id_input = st.text_input("🆔 ID de la llamada (opcional):", key="input_call_id")
            pin_input = st.text_input("🔑 Tu PIN de ATC:", type="password", max_chars=4, key="pin_atc")

            registro_previo = buscar_transferencia_previa(telefono_input) if telefono_input else None
            if registro_previo:
                st.warning(
                    f"⚠️ **¡Cliente recurrente!** El número `{telefono_input.strip()}` ya fue transferido a "
                    f"**{registro_previo['agente_ventas_alias']}** ({registro_previo['agente_ventas_real']}) "
                    f"el `{registro_previo['fecha_hora']}`."
                )
                if st.button(f"🔄 Reasignar a {registro_previo['agente_ventas_alias']} (no usa el turno)",
                             use_container_width=True):
                    _resultado_atc(*reasignar_al_mismo(pin_input, telefono_input))

            if st.button("✅ Registrar transferencia al turno disponible", type="primary", use_container_width=True):
                codigo, msj = registrar_salto_atc(TIPO_TRANSFERIDO, pin_input, turno_visto, telefono_input, call_id_input)
                if codigo == "cambio":
                    st.session_state["conflicto_turno"] = {
                        "mensaje": msj, "real": turno_visto, "pin": pin_input,
                        "alias": next((t["alias"] for t in USUARIOS_INICIALES if t["real"] == turno_visto), turno_visto),
                        "telefono": telefono_input, "call_id": call_id_input,
                    }
                    st.rerun()
                _resultado_atc(codigo, msj)

            if st.button("⏭️ No contesta / no disponible: pasar al siguiente", use_container_width=True):
                codigo, msj = registrar_salto_atc(TIPO_NO_DISPONIBLE, pin_input, turno_visto)
                if codigo == "cambio":
                    st.info(msj + " No se registró nada.")
                else:
                    _resultado_atc(codigo, msj, limpiar=False)

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
        admin_nombre = st.sidebar.text_input(
            "👤 Tu nombre (admin)", key="admin_nombre", placeholder="Obligatorio para guardar cambios",
            help="Queda registrado en cada activación e inactivación.",
        )
        if st.sidebar.button("Cerrar Sesión Admin", use_container_width=True):
            st.session_state.admin_logged = False
            st.rerun()

        aviso = st.session_state.pop("aviso_admin", None)
        if aviso:
            st.success(aviso)

        tab_gestion, tab_historial, tab_estados, tab_log, tab_consulta = st.tabs([
            "⚙️ Gestión de la Fila",
            "📊 Historial de Transferencias",
            "👥 Cambios Activo / Inactivo",
            "📜 Log de Saltos",
            "🔎 Consulta",
        ])

        # ------------------------------------------
        # TAB 1: GESTIÓN DE LA FILA
        # ------------------------------------------
        with tab_gestion:
            data_adm = obtener_turnero_fresco()
            stats = estadisticas_hoy(data_adm)
            activaciones = horas_activacion_hoy(data_adm)
            siguientes_adm = calcular_siguientes(data_adm, cantidad=len(data_adm["turnos"]))
            orden_turno = {s["real"]: i for i, s in enumerate(siguientes_adm, start=1)}

            st.subheader("📋 Fila actual")
            st.caption(
                f"**Rotación:** {' → '.join(COORDINADORES)} y, dentro de cada coordinador, el asesor con "
                "**menos transferencias hoy**; a igualdad, a quien hace más tiempo no le toca y luego sorteo del día. "
                "**No disponible** no suma transferencias pero lo pasa al final de su grupo."
            )
            filas = []
            for t in sorted(data_adm["turnos"], key=lambda x: (orden_turno.get(x["real"], 999), not x["activo"], x["alias"])):
                s = stats.get(t["real"], {})
                a = activaciones.get(t["real"], {})
                filas.append({
                    "Turno": "🎯 Disponible" if orden_turno.get(t["real"]) == 1 else orden_turno.get(t["real"], ""),
                    "Estado": "🟢 Activo" if t["activo"] else "🔴 Inactivo",
                    "Coordinador": t["coordinador"],
                    "Alias": t["alias"],
                    "Nombre Real": t["real"],
                    "🕒 Llegada hoy": _hora(a.get("llegada", "")),
                    "Activo desde": _hora(a.get("activo_desde", "")) if t["activo"] else "—",
                    "📞 Transferencias hoy": s.get("transferencias", 0),
                    "Última transferencia": _hora(s.get("ultima_transferencia", "")),
                    "⏭️ No disponible hoy": s.get("no_disponible", 0),
                    "🔄 Reasignaciones hoy": s.get("reasignaciones", 0),
                })
            st.dataframe(pd.DataFrame(filas).astype(str), use_container_width=True, hide_index=True)

            st.markdown("---")
            st.subheader("🚪 Registrar Llegada")
            st.caption("A las 00:00 (hora Colombia) todos quedan inactivos. Activa a cada persona cuando llegue.")
            inactivos = [t for t in data_adm["turnos"] if not t["activo"]]
            if not inactivos:
                st.success("✅ Todos los asesores están activos.")
            else:
                for coord in COORDINADORES:
                    del_coord = sorted([t for t in inactivos if t["coordinador"] == coord], key=lambda x: x["alias"].lower())
                    if not del_coord:
                        continue
                    st.markdown(f"**{coord}**")
                    cols = st.columns(3)
                    for i, t in enumerate(del_coord):
                        with cols[i % 3]:
                            if st.button(f"✅ {t['alias']}", key=f"llegada_{t['real']}", use_container_width=True, help=t["real"]):
                                exito, msj = registrar_llegada(t["real"], admin_nombre)
                                if exito:
                                    st.toast(f"{t['alias']} activado/a")
                                    st.rerun()
                                elif msj.startswith("ℹ️"):
                                    st.info(f"{t['alias']} ya estaba activo/a (otro admin lo activó). Se actualizó la vista.")
                                else:
                                    st.error(msj)

            st.markdown("---")
            st.subheader("👥 Marcar Activo / Inactivo")
            with st.expander("Ver y gestionar estados", expanded=False):
                # Solo se envían los interruptores que ESTE admin movió y se sincronizan con el estado real,
                # para que un guardado nunca revierta lo que otro admin hizo mientras tanto.
                estados_seleccionados = {}
                for coord in COORDINADORES:
                    st.markdown(f"**{coord}**")
                    for t in sorted([x for x in data_adm["turnos"] if x["coordinador"] == coord], key=lambda x: x["alias"].lower()):
                        k_toggle, k_base = f"toggle_agente_{t['real']}", f"base_agente_{t['real']}"
                        if st.session_state.get(k_base) != t["activo"]:
                            st.session_state[k_base] = t["activo"]
                            st.session_state[k_toggle] = t["activo"]
                        col_name, col_status = st.columns([3, 1])
                        with col_name:
                            st.write(f"**{t['alias']}** ({t['real']})")
                        with col_status:
                            nuevo = st.toggle("Activo" if t["activo"] else "Inactivo", key=k_toggle)
                        if nuevo != t["activo"]:
                            estados_seleccionados[t["real"]] = nuevo
                if estados_seleccionados:
                    st.caption("Cambios pendientes por guardar: " + ", ".join(
                        f"{_agente(data_adm, n)['alias']}→{'Activo' if v else 'Inactivo'}" for n, v in estados_seleccionados.items()))
                motivo_estado = st.text_input(
                    "Motivo del cambio (obligatorio):",
                    placeholder="Ej: Almuerzo / Capacitación / Terminó jornada / Regresó de pausa",
                    key="motivo_estado",
                )
                if st.button("💾 Guardar Cambios de Estado", type="primary", use_container_width=True):
                    exito, msj = guardar_cambios_estado_admin(estados_seleccionados, motivo_estado, admin_nombre)
                    if exito:
                        st.session_state["aviso_admin"] = msj
                        st.rerun()
                    elif msj.startswith("ℹ️"):
                        st.info(msj)
                    else:
                        st.error(msj)

            st.markdown("---")
            st.subheader("🗑️ Limpiar Historial")
            st.caption("Borra todos los registros de transferencias (también reinicia los conteos del día).")
            confirm_del = st.checkbox("Confirmo vaciar historial.", key="chk_del")
            if st.button("Vaciar Historial", disabled=not confirm_del, use_container_width=True):
                nombre_ok, err = _validar_registrado_por(admin_nombre)
                if err:
                    st.error(err)
                elif vaciar_historial_atc(nombre_ok) is True:
                    st.session_state["aviso_admin"] = "✅ Historial de transferencias vaciado."
                    st.rerun()
                else:
                    st.error("❌ No se pudo guardar. Intenta nuevamente.")

        # ------------------------------------------
        # TAB 2: HISTORIAL DE TRANSFERENCIAS
        # ------------------------------------------
        with tab_historial:
            st.subheader("📊 Historial de Transferencias ATC ➔ Ventas")
            historial = obtener_turnero_para_mostrar()["historial"]
            if not historial:
                st.info("Aún no se han registrado transferencias.")
            else:
                df_historial = pd.DataFrame(historial).rename(columns={
                    "id": "ID Reg",
                    "telefono": "Teléfono Cliente",
                    "call_id": "ID Llamada",
                    "agente_atc": "Atendido Por (ATC)",
                    "agente_ventas_real": "Asignado A (Ventas)",
                    "agente_ventas_alias": "Alias Ventas",
                    "coordinador": "Coordinador",
                    "tipo": "Tipo",
                    "motivo": "Motivo",
                    "solapado": "⚠️ Solapado",
                    "fecha_hora": "Fecha / Hora (Colombia)",
                }).astype(str)
                tipos = ["Todos"] + sorted(df_historial["Tipo"].unique())
                filtro = st.selectbox("Filtrar por tipo:", tipos, key="filtro_tipo_hist")
                vista = df_historial if filtro == "Todos" else df_historial[df_historial["Tipo"] == filtro]
                st.dataframe(vista, use_container_width=True, hide_index=True)
                st.download_button(
                    label="📥 Descargar Reporte CSV de Transferencias",
                    data=df_historial.to_csv(index=False).encode("utf-8"),
                    file_name=f"reporte_transferencias_atc_{obtener_fecha_hora_colombia().strftime('%Y%m%d_%H%M')}.csv",
                    mime="text/csv",
                    use_container_width=True,
                )

        # ------------------------------------------
        # TAB 3: CAMBIOS DE ESTADO
        # ------------------------------------------
        with tab_estados:
            st.subheader("👥 Historial de Cambios Activo / Inactivo")
            cambios = obtener_turnero_para_mostrar()["cambios_estado"]
            if not cambios:
                st.info("Aún no se han registrado cambios de estado.")
            else:
                df_cambios = pd.DataFrame(cambios).rename(columns={
                    "fecha_hora": "Fecha / Hora (Colombia)",
                    "tipo": "Cambio",
                    "nombre_real": "Nombre Real",
                    "alias": "Alias",
                    "coordinador": "Coordinador",
                    "motivo": "Motivo",
                    "registrado_por": "Registrado por",
                }).astype(str)
                st.dataframe(df_cambios, use_container_width=True, hide_index=True)
                st.download_button(
                    label="📥 Descargar Cambios de Estado (CSV)",
                    data=df_cambios.to_csv(index=False).encode("utf-8"),
                    file_name=f"cambios_estado_atc_{obtener_fecha_hora_colombia().strftime('%Y%m%d_%H%M')}.csv",
                    mime="text/csv",
                    use_container_width=True,
                )

        # ------------------------------------------
        # TAB 4: LOG DE SALTOS
        # ------------------------------------------
        with tab_log:
            st.subheader("📜 Log de Saltos (`atc_saltos_log.json`)")
            st.caption("Cada transferencia, no disponible y cambio de estado, con la lista de siguientes en ese momento.")
            df_log = obtener_log_saltos_df()
            if df_log.empty:
                st.info("Aún no hay registros en el log.")
            else:
                st.dataframe(df_log, use_container_width=True, hide_index=True)
                st.download_button(
                    label="📥 Descargar Log de Saltos (CSV)",
                    data=df_log.to_csv(index=False).encode("utf-8"),
                    file_name=f"log_saltos_atc_{obtener_fecha_hora_colombia().strftime('%Y%m%d_%H%M')}.csv",
                    mime="text/csv",
                    use_container_width=True,
                )

        # ------------------------------------------
        # TAB 5: CONSULTA
        # ------------------------------------------
        with tab_consulta:
            st.subheader("🔎 Consulta por teléfono, asesor o ATC")
            texto = st.text_input("Buscar:", placeholder="Teléfono, nombre del asesor o del ATC", key="consulta_txt")
            historial = obtener_turnero_para_mostrar()["historial"]
            if texto.strip():
                q = texto.strip().lower()
                encontrados = [h for h in historial if any(q in str(h.get(c, "")).lower() for c in (
                    "telefono", "agente_ventas_real", "agente_ventas_alias", "agente_atc", "call_id"))]
                if encontrados:
                    st.dataframe(pd.DataFrame(encontrados).astype(str), use_container_width=True, hide_index=True)
                else:
                    st.info("Sin resultados.")
