import base64
import hmac
import json
import random
import threading
import zlib
import time as time_lib
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import streamlit as st
from github import Github, GithubException

# ==========================================
# CONFIGURACIÓN DE PÁGINA
# ==========================================
st.set_page_config(
    page_title="Turnero de Asignaciones ATC a Ventas",
    page_icon="📞",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ARCHIVOS DE PERSISTENCIA EN GITHUB
FILE_ATC_VENTAS = "atc_ventas_ruleta.json"   # Fila, historial de asignaciones y rotación
FILE_LOG_SALTOS = "atc_saltos_log.json"      # Log de la versión anterior (solo lectura)
FILE_ESTADOS_IVR = "turnos_orden.json"       # En el repo de IVR: activo/inactivo (se gestiona en IVR)
REPO_IVR_POR_DEFECTO = "BPOZEN-jorge/IVR-Llamadas"

# Rotación: primero el coordinador (en este orden) y luego un asesor suyo
COORDINADORES = ["Jose", "Paula", "Victor"]
SIGUIENTES_A_MOSTRAR = 6     # Turno disponible + próximos
REFRESCO_SEGUNDOS = 2        # Actualización automática del panel de turnos
MAX_INTENTOS_PIN = 5         # Intentos de PIN por sesión del ATC

# Tipos de registro en el historial
TIPO_TRANSFERIDO = "Transferido (turno)"            # Cuenta como salto
TIPO_TRANSFERIDO_ANTERIOR = "Siguiente en Ruleta"   # Registros de la versión anterior (también cuentan)
TIPO_NO_DISPONIBLE = "No disponible (saltado)"       # No cuenta como transferencia, pero pasa al final de su grupo
TIPO_REASIGNADO = "Reasignado al Mismo Agente"       # Cliente recurrente: no mueve la rotación
TIPO_ELIMINADA = "Eliminada por admin"              # No cuenta y no se le muestra al asesor; queda para auditoría
TIPOS_QUE_CUENTAN = {TIPO_TRANSFERIDO, TIPO_TRANSFERIDO_ANTERIOR}
TIPOS_ASIGNACION_VIGENTE = TIPOS_QUE_CUENTAN | {TIPO_REASIGNADO}
TIPO_VISIBLE = {  # cómo se muestran los tipos guardados en el historial
    "Transferido (turno)": "Asignación (turno)",
    "Siguiente en Ruleta": "Asignación (versión anterior)",
    "Reasignado al Mismo Agente": "Reasignación (cliente recurrente)",
    "No disponible (saltado)": "No disponible (versión anterior)",
}

# Tipo de cambio de estado que marca una activación (en los cambios de IVR)
TIPO_REACTIVADO = "REACTIVADO"

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
    "Joyke Machacon Suarez",
    "Janis Henao Vasco",
    "Tatiana Magreth Acevedo Marín",
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
    {"posicion": 11, "real": "Evelin Acevedo Cortés", "alias": "Gabriela", "coordinador": "Victor"},
    {"posicion": 12, "real": "Gustavo Adolfo Barrientos Serna", "alias": "Gustavo", "coordinador": "Victor"},
    {"posicion": 13, "real": "Iris Sabiana Cano Cano", "alias": "Maria Cano", "coordinador": "Paula"},
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


@st.cache_resource(show_spinner=False)
def _cache_lecturas() -> dict:
    return {"lock": threading.Lock(), "items": {}}


def leer_rapido(repo_name: str, file_path: str, max_edad: float = 1.0):
    """
    Lectura para MOSTRAR, compartida entre todas las sesiones, con petición condicional (ETag):
    si el archivo no cambió, GitHub responde 304 y esa consulta NO gasta el límite de la API.
    Como mucho una consulta por archivo cada `max_edad` segundos (0 = confirmar siempre con GitHub).
    """
    cache = _cache_lecturas()
    clave = f"{repo_name}/{file_path}"
    with cache["lock"]:
        item = cache["items"].get(clave)
        if item and time_lib.time() - item["t"] < max_edad:
            return item["data"]
        gh = st.secrets.get("github", {})
        headers = {
            "Authorization": f"Bearer {gh.get('token', '')}",
            "Accept": "application/vnd.github.raw+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if item:
            headers["If-None-Match"] = item["etag"]
        try:
            r = requests.get(f"https://api.github.com/repos/{repo_name}/contents/{file_path}",
                             params={"ref": gh.get("branch", "main")}, headers=headers, timeout=15)
        except requests.RequestException:
            if item:
                return item["data"]  # sin conexión momentánea: se muestra lo último conocido
            raise
        if r.status_code == 304 and item:
            item["t"] = time_lib.time()
            return item["data"]
        if r.status_code == 404:
            return None
        r.raise_for_status()
        data = r.json()
        cache["items"][clave] = {"etag": r.headers.get("ETag", ""), "data": data, "t": time_lib.time()}
        return data


def _invalidar_lectura(repo_name: str, file_path: str):
    item = _cache_lecturas()["items"].get(f"{repo_name}/{file_path}")
    if item:
        item["t"] = 0


def leer_para_mostrar(file_path: str) -> dict | None:
    return leer_rapido(st.secrets["github"]["repo"], file_path)


def estados_ivr(fresco: bool = False) -> dict:
    """
    Estados activo/inactivo y cambios de estado desde el turnero IVR ([github].repo_ivr o, si no está,
    BPOZEN-jorge/IVR-Llamadas). La activación/desactivación se gestiona SOLO en IVR; aquí se leen.
    """
    repo_ivr = st.secrets.get("github", {}).get("repo_ivr") or REPO_IVR_POR_DEFECTO
    try:
        data = leer_rapido(repo_ivr, FILE_ESTADOS_IVR, max_edad=0 if fresco else 1.0) or {}
    except Exception:  # noqa: BLE001  (token, red o GitHub caído)
        return {"activos": {}, "cambios": [], "error": True}
    return {
        "activos": {t["real"]: bool(t.get("activo", True)) for t in data.get("turnos", [])},
        "cambios": data.get("cambios_estado", []),
    }


def _aplicar_estados(data: dict, estados: dict) -> dict:
    for t in data["turnos"]:
        t["activo"] = estados["activos"].get(t["real"], False)
    data["_estados_error"] = bool(estados.get("error"))  # no se guardan: se quitan antes de escribir
    data["_cambios_ivr"] = estados.get("cambios", [])
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
            _invalidar_lectura(st.secrets["github"]["repo"], file_path)
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
            _invalidar_lectura(st.secrets["github"]["repo"], file_path)
            return True
        except GithubException as e:
            if intento < retries - 1:
                time_lib.sleep(0.5)
            else:
                st.error(f"❌ Error al guardar en {file_path} tras varios intentos: {e}")
                return False


def guardar_turnero(data: dict, mensaje: str) -> bool:
    data.pop("_estados_error", None)
    data.pop("_cambios_ivr", None)
    return escribir_json_github(FILE_ATC_VENTAS, data, mensaje, sha_esperado=sha_leido(FILE_ATC_VENTAS))


# ==========================================
# LOG DE ASIGNACIONES (FOTO DE LA FILA)
# ==========================================
def obtener_log_saltos_df(historial: list) -> pd.DataFrame:
    """
    Cada asignación guarda en el historial la lista de siguientes en ese momento (un solo guardado, más
    rápido). Se agrega el log de la versión anterior (atc_saltos_log.json) para no perder nada.
    """
    filas = [{
        "Tipo": TIPO_VISIBLE.get(h.get("tipo"), h.get("tipo")),
        "Fecha/Hora (Colombia)": h.get("fecha_hora"),
        "Teléfono": h.get("telefono", ""),
        "Agente (Alias)": h.get("agente_ventas_alias"),
        "Agente (Real)": h.get("agente_ventas_real"),
        "Coordinador": h.get("coordinador", ""),
        "ATC": h.get("agente_atc", ""),
        "Solapado": "⚠️ Sí" if h.get("solapado") else "",
        "Siguientes en ese momento": " → ".join(h.get("siguientes_snapshot", [])),
    } for h in historial if h.get("siguientes_snapshot")]
    for s in (leer_para_mostrar(FILE_LOG_SALTOS) or {}).get("saltos", []):
        filas.append({
            "Tipo": TIPO_VISIBLE.get(s.get("tipo"), s.get("tipo")),
            "Fecha/Hora (Colombia)": s.get("fecha_hora"),
            "Teléfono": s.get("telefono", ""),
            "Agente (Alias)": s.get("alias"),
            "Agente (Real)": s.get("nombre_real"),
            "Coordinador": s.get("coordinador", ""),
            "ATC": s.get("agente_atc", ""),
            "Solapado": "⚠️ Sí" if s.get("solapado") else "",
            "Siguientes en ese momento": " → ".join(s.get("siguientes_snapshot", [])),
        })
    return pd.DataFrame(filas).astype(str) if filas else pd.DataFrame()


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
    turnos = [t for t in turnos if t["real"] in COORDINADOR_POR_AGENTE]  # solo el equipo de ventas actual
    existentes = {t["real"] for t in turnos}
    turnos += [dict(u, activo=False) for u in USUARIOS_INICIALES if u["real"] not in existentes]
    for t in turnos:
        t["coordinador"] = COORDINADOR_POR_AGENTE.get(t["real"], t.get("coordinador", ""))
        t["activo"] = bool(t.get("activo", False))
    data["turnos"] = sorted(turnos, key=lambda x: x.get("posicion", 999))
    return data


def obtener_turnero_fresco() -> dict:
    """Para registrar: turnero y estados de IVR confirmados con GitHub en este momento."""
    data = _normalizar_turnero(leer_json_github(FILE_ATC_VENTAS, _default_turnero()))
    return _aplicar_estados(data, estados_ivr(fresco=True))


def obtener_turnero_para_mostrar() -> dict:
    data = leer_para_mostrar(FILE_ATC_VENTAS)
    data = _normalizar_turnero(json.loads(json.dumps(data)) if data else _default_turnero())
    return _aplicar_estados(data, estados_ivr())


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


def orden_turnero(turnos: list, cambios_ivr: list, datos_atc: dict, hoy: str) -> list:
    """
    ORDEN ÚNICO DEL TURNERO: esta función es idéntica en las apps IVR y ATC, así las dos muestran la misma fila.
    Solo asesores ACTIVOS en IVR.
    1) Coordinador en rotación COORDINADORES desde el coordinador en turno de ATC (si no tiene activos, se salta).
    2) Dentro del coordinador: menos asignaciones hoy -> a quien hace más tiempo no le toca ->
       orden de activación en IVR ("activo desde": quien se activó antes va primero) -> nombre.
    Devuelve [{"real", "alias", "coordinador"}] en orden; el primero es el turno disponible.
    """
    activo_desde = {}
    for c in cambios_ivr:
        fecha, nombre = str(c.get("fecha_hora", "")), c.get("nombre_real")
        if c.get("tipo") == "REACTIVADO" and nombre and fecha.startswith(hoy):
            activo_desde[nombre] = max(activo_desde.get(nombre, ""), fecha)

    asignaciones, ultimo = {}, {}
    for h in datos_atc.get("historial", []):
        fecha, nombre, tipo = str(h.get("fecha_hora", "")), h.get("agente_ventas_real"), h.get("tipo")
        if not nombre or not fecha.startswith(hoy):
            continue
        if tipo in ("Transferido (turno)", "Siguiente en Ruleta"):
            asignaciones[nombre] = asignaciones.get(nombre, 0) + 1
        if tipo in ("Transferido (turno)", "Siguiente en Ruleta", "No disponible (saltado)"):
            ultimo[nombre] = max(ultimo.get(nombre, ""), fecha)

    por_coord = {}
    for c in COORDINADORES:
        candidatos = [t for t in turnos if t.get("activo", True) and COORDINADOR_POR_AGENTE.get(t["real"]) == c]
        candidatos.sort(key=lambda t: (asignaciones.get(t["real"], 0), ultimo.get(t["real"], ""),
                                       activo_desde.get(t["real"], "~"), t["real"]))
        por_coord[c] = candidatos

    # Si ATC aún no hizo su reset de hoy, la rotación del día empieza igual por el primer coordinador
    puntero = int(datos_atc.get("puntero_coordinador", 0)) if datos_atc.get("ultimo_reset_diario", "") >= hoy else 0
    puntero %= len(COORDINADORES)
    usados = {c: 0 for c in COORDINADORES}
    resultado = []
    while True:
        for salto in range(len(COORDINADORES)):
            c = COORDINADORES[(puntero + salto) % len(COORDINADORES)]
            if usados[c] < len(por_coord[c]):
                t = por_coord[c][usados[c]]
                usados[c] += 1
                resultado.append({"real": t["real"], "alias": t["alias"], "coordinador": c})
                puntero = (puntero + salto + 1) % len(COORDINADORES)
                break
        else:
            return resultado


def calcular_siguientes(data: dict, cantidad: int = SIGUIENTES_A_MOSTRAR) -> list:
    """Próximos turnos con el orden único (el mismo que muestra el admin de IVR)."""
    return orden_turnero(data["turnos"], data.get("_cambios_ivr", []), data, hoy_colombia())[:cantidad]


def _avanzar_rotacion(data: dict, agente: dict):
    """Tras una asignación del turno disponible, el turno pasa al siguiente coordinador."""
    data["puntero_coordinador"] = (COORDINADORES.index(agente["coordinador"]) + 1) % len(COORDINADORES)
    data["no_disponibles_ronda"] = {}


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


def asignar_cliente(pin: str, telefono: str, real_visto: str | None = None) -> tuple[str, str]:
    """
    Asigna el número del cliente al TURNO DISPONIBLE con el PIN del ATC (el asesor lo ve en IVR).
    El turno se calcula en el momento de guardar con escritura atómica: si otro ATC tomó ese turno en los
    mismos segundos, este cliente queda con el siguiente. Así nunca se asignan dos clientes al mismo turno.
    Devuelve (codigo, mensaje) con codigo 'ok' | 'pin' | 'error'.
    """
    atc = atc_por_pin(pin)
    if not atc:
        return "pin", "❌ PIN incorrecto. Escribe tu PIN de ATC de 4 dígitos."
    telefono_clean = telefono.strip()
    if not telefono_clean:
        return "error", "⚠️ Debes ingresar el teléfono del cliente."

    def operacion():
        data = obtener_turnero_fresco()
        if data.get("_estados_error"):
            return "error", "⚠️ No se pudo leer el estado de los asesores en IVR. Intenta de nuevo en unos segundos."
        siguientes = calcular_siguientes(data)
        if not siguientes:
            return "error", "⚠️ No hay asesores activos disponibles en este momento."
        actual = siguientes[0]
        agente = _agente(data, actual["real"])
        _registro_historial(
            data, telefono=telefono_clean, agente_atc=atc,
            agente_ventas_real=agente["real"], agente_ventas_alias=agente["alias"],
            coordinador=agente["coordinador"], tipo=TIPO_TRANSFERIDO,
            siguientes_snapshot=[f"{x['alias']} ({x['coordinador']})" for x in siguientes],
        )
        _avanzar_rotacion(data, agente)
        if not guardar_turnero(data, f"Asignación cliente {telefono_clean} a {agente['alias']} (ATC {atc})"):
            return "error", "❌ Hubo un fallo temporal de comunicación con GitHub. Intenta nuevamente."
        cambio = ""
        if real_visto and real_visto != agente["real"]:
            visto = next((t["alias"] for t in data["turnos"] if t["real"] == real_visto), real_visto)
            cambio = f" (el turno de **{visto}** lo acababa de tomar otro ATC)"
        nuevo = calcular_siguientes(data, cantidad=1)
        sigue = f" Siguiente turno: **{nuevo[0]['alias']}** ({nuevo[0]['coordinador']})." if nuevo else ""
        return "ok", (f"✅ {atc}: cliente `{telefono_clean}` asignado a **{agente['alias']}** "
                      f"({agente['coordinador']}){cambio}.{sigue}")

    resultado = ejecutar_con_reintentos(operacion)
    return ("error", resultado[1]) if resultado[0] is False else resultado


def buscar_transferencia_previa(telefono: str) -> dict | None:
    """Busca en el historial si el número de teléfono ya fue derivado previamente."""
    telefono_clean = telefono.strip()
    if not telefono_clean:
        return None
    historial = obtener_turnero_para_mostrar()["historial"]
    return next((h for h in historial if h.get("telefono") == telefono_clean
                 and h.get("tipo") not in (TIPO_NO_DISPONIBLE, TIPO_ELIMINADA)), None)


def reasignar_al_mismo(pin: str, telefono: str) -> tuple[str, str]:
    """Cliente recurrente: se envía a su asesor anterior. No mueve la rotación."""
    atc = atc_por_pin(pin)
    if not atc:
        return "pin", "❌ PIN incorrecto. Escribe tu PIN de ATC de 4 dígitos."
    telefono_clean = telefono.strip()

    def operacion():
        data = obtener_turnero_fresco()
        previo = next((h for h in data["historial"] if h.get("telefono") == telefono_clean
                       and h.get("tipo") not in (TIPO_NO_DISPONIBLE, TIPO_ELIMINADA)), None)
        if not previo:
            return "error", "❌ No se encontró registro previo para reasignar a este cliente."
        _registro_historial(
            data, telefono=telefono_clean, agente_atc=atc,
            agente_ventas_real=previo["agente_ventas_real"], agente_ventas_alias=previo["agente_ventas_alias"],
            coordinador=COORDINADOR_POR_AGENTE.get(previo["agente_ventas_real"], ""), tipo=TIPO_REASIGNADO,
        )
        if guardar_turnero(data, f"Reasignación cliente {telefono_clean} a {previo['agente_ventas_alias']} (ATC {atc})"):
            return "ok", f"✅ {atc}: cliente `{telefono_clean}` reasignado a **{previo['agente_ventas_alias']}** (no mueve el turno)."
        return "error", "❌ Hubo un fallo temporal de comunicación con GitHub. Intenta nuevamente."

    resultado = ejecutar_con_reintentos(operacion)
    return ("error", resultado[1]) if resultado[0] is False else resultado


# ==========================================
# ESTADOS (SE GESTIONAN EN IVR) Y ADMIN
# ==========================================
def _validar_registrado_por(registrado_por: str):
    """Quien hace el cambio debe identificarse."""
    nombre = (registrado_por or "").strip()
    if len(nombre) < 2:
        return None, "⚠️ Escribe tu nombre en **Tu nombre (admin)** en la barra lateral antes de guardar cambios."
    return nombre, None


def horas_activacion_hoy(cambios: list) -> dict:
    """llegada = primera activación de hoy; activo_desde = última activación de hoy (cambios de IVR)."""
    hoy = hoy_colombia()
    horas = {}
    for c in cambios:
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
    En la PRIMERA carga de la app después de las 00:00 (hora Colombia) la rotación empieza otra vez por el
    primer coordinador. Los estados activo/inactivo los reinicia el turnero IVR.
    """
    hoy = hoy_colombia()
    if st.session_state.get("reset_diario_verificado") == hoy:
        return

    def operacion():
        data = obtener_turnero_fresco()
        if data.get("ultimo_reset_diario", "") >= hoy:
            return None
        data["puntero_coordinador"] = 0
        data["no_disponibles_ronda"] = {}
        data["ultimo_reset_diario"] = hoy
        return guardar_turnero(data, f"Auto: Reset diario 00:00 - rotación desde {COORDINADORES[0]} ({hoy})")

    resultado = ejecutar_con_reintentos(operacion)
    if resultado is True or resultado is None:  # None = ya estaba hecho hoy
        st.session_state.reset_diario_verificado = hoy  # si falló, se reintenta en la próxima carga


def clave_asignacion(h: dict) -> str:
    return "|".join(str(h.get(c, "")) for c in ("fecha_hora", "telefono", "agente_ventas_real", "agente_atc", "id"))


def eliminar_asignaciones(claves: list, motivo: str, registrado_por: str) -> tuple[bool, str]:
    """
    Quita asignaciones elegidas por el admin: dejan de contar en la fila y de verse en IVR.
    El registro queda marcado en el historial (quién, cuándo y por qué) en vez de borrarse.
    """
    nombre, error = _validar_registrado_por(registrado_por)
    if error:
        return False, error
    if not claves:
        return False, "ℹ️ No seleccionaste ninguna asignación."

    def operacion():
        data = obtener_turnero_fresco()
        ahora = obtener_hora_colombia_str()
        marcadas = 0
        for h in data["historial"]:
            if clave_asignacion(h) in claves and h.get("tipo") in TIPOS_ASIGNACION_VIGENTE:
                h.update(tipo_original=h["tipo"], tipo=TIPO_ELIMINADA, eliminada_por=nombre,
                         eliminada_en=ahora, motivo_eliminacion=motivo.strip())
                marcadas += 1
        if not marcadas:
            return False, "ℹ️ Esas asignaciones ya no están vigentes (quizá otro admin las eliminó)."
        if guardar_turnero(data, f"Admin {nombre}: elimina {marcadas} asignación(es) - {motivo.strip()[:60]}"):
            return True, f"✅ Se eliminaron {marcadas} asignación(es). Ya no cuentan en la fila ni se ven en IVR."
        return False, "❌ Hubo un fallo temporal de comunicación con GitHub. Intenta nuevamente."
    return ejecutar_con_reintentos(operacion)


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
opcion_vista = st.sidebar.radio("Navegación:", ["🎧 Asignar a Ventas", "🛡️ Vista Administrador"])


def _hora(fecha: str) -> str:
    return fecha[11:16] if fecha else "—"


@st.fragment(run_every=REFRESCO_SEGUNDOS)
def panel_turnos():
    """Turno disponible. Se actualiza solo para que nadie vea un turno desactualizado."""
    try:
        data = obtener_turnero_para_mostrar()
    except Exception:  # noqa: BLE001  (tropiezo de red o de GitHub: se reintenta en el próximo refresco)
        st.warning(f"⚠️ No se pudo actualizar el turno. Se reintenta en {REFRESCO_SEGUNDOS} s.")
        return
    siguientes = calcular_siguientes(data, cantidad=1)

    if siguientes:
        actual = siguientes[0]
        # Lo que el ATC tiene en pantalla: al registrar se valida que siga siendo el disponible.
        st.session_state["turno_visto"] = actual["real"]
        st.metric(label=f"🎯 TURNO DISPONIBLE · Coordinador {actual['coordinador']}", value=actual["alias"])
        st.caption(f"👤 {actual['real']}")
        activos = sum(t["activo"] for t in data["turnos"])
        st.caption(f"🟢 {activos} asesores activos (según el turnero IVR)")
    else:
        st.session_state["turno_visto"] = None
        if data.get("_estados_error"):
            st.error("⚠️ No se pudo leer el estado de los asesores en IVR. Se reintenta en unos segundos.")
        else:
            st.error("⚠️ No hay asesores activos disponibles en este momento (se activan en el turnero IVR).")

    hoy = hoy_colombia()
    ultimo = next((h for h in data["historial"] if str(h.get("fecha_hora", "")).startswith(hoy)
                   and h.get("tipo") == TIPO_TRANSFERIDO), None)
    if ultimo:
        st.caption(f"Última asignación: **{ultimo['agente_ventas_alias']}** · "
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
# VISTA 1: ASIGNAR A VENTAS (ATC)
# ------------------------------------------
if opcion_vista == "🎧 Asignar a Ventas":
    st.title("📞 Turnero de Asignaciones: ATC ➔ Ventas")
    st.caption(
        f"Hora Colombia: `{obtener_hora_colombia_str()}` · Rotación por coordinador: "
        f"{' → '.join(COORDINADORES)} → … y dentro de cada uno, el asesor con menos asignaciones hoy."
    )

    aviso = st.session_state.pop("aviso_atc", None)
    if aviso:
        st.success(aviso)

    # Turno que el ATC tenía en pantalla ANTES de pulsar (solo para avisarle si cambió)
    turno_visto = st.session_state.get("turno_visto")

    col_info, col_form = st.columns([2, 3])
    with col_info:
        panel_turnos()

    with col_form:
        if st.session_state.get("intentos_pin", 0) >= MAX_INTENTOS_PIN:
            st.error("🔒 Demasiados PIN incorrectos. Recarga la página para intentarlo de nuevo.")
        else:
            st.subheader("📋 Registrar asignación")
            st.caption("Asigna el número del cliente al **turno disponible** con tu PIN. "
                       "El asesor lo verá al instante en su vista de IVR.")
            telefono_input = st.text_input(
                "📱 Teléfono del Cliente:", key="input_telefono", placeholder="Ej: +573001234567, +14155552671..."
            )
            pin_input = st.text_input("🔑 Tu PIN de ATC:", type="password", max_chars=4, key="pin_atc")

            registro_previo = buscar_transferencia_previa(telefono_input) if telefono_input else None
            if registro_previo:
                st.warning(
                    f"⚠️ **¡Cliente recurrente!** El número `{telefono_input.strip()}` ya fue asignado a "
                    f"**{registro_previo['agente_ventas_alias']}** ({registro_previo['agente_ventas_real']}) "
                    f"el `{registro_previo['fecha_hora']}`."
                )
                if st.button(f"🔄 Reasignar a {registro_previo['agente_ventas_alias']} (no usa el turno)",
                             use_container_width=True):
                    _resultado_atc(*reasignar_al_mismo(pin_input, telefono_input))

            if st.button("✅ Registrar asignación al turno disponible", type="primary", use_container_width=True):
                _resultado_atc(*asignar_cliente(pin_input, telefono_input, turno_visto))

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
            help="Queda registrado al eliminar asignaciones o vaciar el historial.",
        )
        if st.sidebar.button("Cerrar Sesión Admin", use_container_width=True):
            st.session_state.admin_logged = False
            st.rerun()

        aviso = st.session_state.pop("aviso_admin", None)
        if aviso:
            st.success(aviso)

        tab_gestion, tab_historial, tab_eliminar, tab_estados, tab_log, tab_consulta = st.tabs([
            "⚙️ Gestión de la Fila",
            "📊 Historial de Asignaciones",
            "🗑️ Eliminar Asignaciones",
            "👥 Cambios Activo / Inactivo",
            "📜 Log de Asignaciones",
            "🔎 Consulta",
        ])

        # ------------------------------------------
        # TAB 1: GESTIÓN DE LA FILA
        # ------------------------------------------
        with tab_gestion:
            data_adm = obtener_turnero_fresco()
            estados_adm = estados_ivr(fresco=True)
            stats = estadisticas_hoy(data_adm)
            activaciones = horas_activacion_hoy(estados_adm["cambios"])

            # Validación: los activos que usa ATC son exactamente los activos de IVR
            activos_ivr = {n for n, v in estados_adm["activos"].items() if v}
            activos_atc = {t["real"] for t in data_adm["turnos"] if t["activo"]}
            nombres_atc = {t["real"] for t in data_adm["turnos"]}
            no_reconocidos = sorted(set(estados_adm["activos"]) - nombres_atc)
            if estados_adm.get("error"):
                st.error("⚠️ No se pudo leer el estado de los asesores en IVR (revisa el token de GitHub y "
                         "`repo_ivr` en los secrets). Mientras tanto ATC no asigna turnos.")
            elif activos_ivr == activos_atc and not no_reconocidos:
                st.success(f"✅ Activación sincronizada con IVR: **{len(activos_ivr)}** activos en IVR = "
                           f"**{len(activos_atc)}** activos en ATC (mismas personas).")
            else:
                st.error(
                    "⚠️ La activación NO coincide con IVR. "
                    + (f"Activos en IVR que ATC no usa: {', '.join(sorted(activos_ivr - activos_atc))}. " if activos_ivr - activos_atc else "")
                    + (f"Activos en ATC que no lo están en IVR: {', '.join(sorted(activos_atc - activos_ivr))}. " if activos_atc - activos_ivr else "")
                    + (f"Nombres de IVR que no existen en ATC: {', '.join(no_reconocidos)}." if no_reconocidos else "")
                )
            siguientes_adm = calcular_siguientes(data_adm, cantidad=len(data_adm["turnos"]))
            orden_turno = {s["real"]: i for i, s in enumerate(siguientes_adm, start=1)}

            st.subheader("📋 Fila actual")
            st.caption(
                f"**Rotación:** {' → '.join(COORDINADORES)} y, dentro de cada coordinador, el asesor con "
                "**menos asignaciones hoy**; a igualdad, a quien hace más tiempo no le toca y luego **quien se activó "
                "antes en IVR**. Solo participan los **activos en IVR**; si un coordinador no tiene activos, pasa al "
                "siguiente. Es el mismo orden que muestra el admin del turnero IVR."
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
                    "📞 Asignaciones hoy": s.get("transferencias", 0),
                    "Última asignación": _hora(s.get("ultima_transferencia", "")),
                    "🔄 Reasignaciones hoy": s.get("reasignaciones", 0),
                })
            st.dataframe(pd.DataFrame(filas).astype(str), use_container_width=True, hide_index=True)

            st.info("👥 **Activo / inactivo, llegadas y pausas se gestionan en el turnero IVR** (Vista Administrador). "
                    "Aquí se reflejan en segundos.")

            st.markdown("---")
            st.subheader("🗑️ Limpiar Historial")
            st.caption("Borra todos los registros de asignaciones (también reinicia los conteos del día).")
            confirm_del = st.checkbox("Confirmo vaciar historial.", key="chk_del")
            if st.button("Vaciar Historial", disabled=not confirm_del, use_container_width=True):
                nombre_ok, err = _validar_registrado_por(admin_nombre)
                if err:
                    st.error(err)
                elif vaciar_historial_atc(nombre_ok) is True:
                    st.session_state["aviso_admin"] = "✅ Historial de asignaciones vaciado."
                    st.rerun()
                else:
                    st.error("❌ No se pudo guardar. Intenta nuevamente.")

        # ------------------------------------------
        # TAB 2: HISTORIAL DE TRANSFERENCIAS
        # ------------------------------------------
        with tab_historial:
            st.subheader("📊 Historial de Asignaciones ATC ➔ Ventas")
            historial = obtener_turnero_para_mostrar()["historial"]
            if not historial:
                st.info("Aún no se han registrado asignaciones.")
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
                }).drop(columns=["siguientes_snapshot"], errors="ignore").astype(str)
                df_historial["Tipo"] = df_historial["Tipo"].map(lambda x: TIPO_VISIBLE.get(x, x))
                tipos = ["Todos"] + sorted(df_historial["Tipo"].unique())
                filtro = st.selectbox("Filtrar por tipo:", tipos, key="filtro_tipo_hist")
                vista = df_historial if filtro == "Todos" else df_historial[df_historial["Tipo"] == filtro]
                st.dataframe(vista, use_container_width=True, hide_index=True)
                st.download_button(
                    label="📥 Descargar Reporte CSV de Asignaciones",
                    data=df_historial.to_csv(index=False).encode("utf-8"),
                    file_name=f"reporte_transferencias_atc_{obtener_fecha_hora_colombia().strftime('%Y%m%d_%H%M')}.csv",
                    mime="text/csv",
                    use_container_width=True,
                )

        # ------------------------------------------
        # ELIMINAR ASIGNACIONES (REPETIDAS O MAL HECHAS)
        # ------------------------------------------
        with tab_eliminar:
            st.subheader("🗑️ Eliminar asignaciones repetidas o mal hechas")
            st.caption("La asignación deja de contar en la fila y desaparece de la vista del asesor en IVR. "
                       "Queda marcada en el historial con quién la eliminó y el motivo.")
            c_fecha, c_solo = st.columns([1, 2])
            hoy_elim = obtener_fecha_hora_colombia().date()
            fecha_elim = c_fecha.date_input("Día:", value=hoy_elim, max_value=hoy_elim,
                                            key="fecha_eliminar").strftime("%Y-%m-%d")
            solo_repetidos = c_solo.checkbox("Mostrar solo teléfonos repetidos ese día", value=True, key="solo_repetidos")

            vigentes = [h for h in obtener_turnero_para_mostrar()["historial"]
                        if str(h.get("fecha_hora", "")).startswith(fecha_elim)
                        and h.get("tipo") in TIPOS_ASIGNACION_VIGENTE]
            por_telefono = {}
            for h in vigentes:
                por_telefono[h.get("telefono")] = por_telefono.get(h.get("telefono"), 0) + 1
            candidatas = [h for h in vigentes if not solo_repetidos or por_telefono[h.get("telefono")] > 1]
            candidatas.sort(key=lambda h: (str(h.get("telefono")), str(h.get("fecha_hora"))))

            if not candidatas:
                st.info("No hay repetidos ese día." if solo_repetidos else "No hay asignaciones ese día.")
            else:
                textos = {}
                vistos = set()
                for h in candidatas:
                    tel = h.get("telefono")
                    nota = " · PRIMERA" if tel not in vistos and por_telefono[tel] > 1 else ""
                    vistos.add(tel)
                    textos[clave_asignacion(h)] = (f"{tel} · {str(h.get('fecha_hora'))[11:19]} · "
                                                   f"{h.get('agente_ventas_alias')} ({h.get('coordinador', '')}) · "
                                                   f"ATC {h.get('agente_atc', '')}{nota}")
                # La llave cambia con las opciones: una selección vieja nunca apunta a un registro que ya no está
                llave = "eliminar_sel_" + str(zlib.crc32("||".join(textos).encode()))
                seleccion = st.multiselect("Asignaciones a eliminar:", list(textos), format_func=textos.get, key=llave)
                motivo_elim = st.text_input("Motivo:", value="Asignación repetida", key="motivo_eliminar")
                confirmar_elim = st.checkbox(f"Confirmo eliminar {len(seleccion)} asignación(es).", key=f"conf_{llave}")
                if st.button("🗑️ Eliminar seleccionadas", type="primary", use_container_width=True,
                             disabled=not (seleccion and confirmar_elim)):
                    exito, msj = eliminar_asignaciones(seleccion, motivo_elim, admin_nombre)
                    if exito:
                        st.session_state["aviso_admin"] = msj
                        st.rerun()
                    elif msj.startswith("ℹ️"):
                        st.info(msj)
                    else:
                        st.error(msj)

        # ------------------------------------------
        # TAB 3: CAMBIOS DE ESTADO
        # ------------------------------------------
        with tab_estados:
            st.subheader("👥 Historial de Cambios Activo / Inactivo (turnero IVR)")
            st.caption("Solo lectura: los cambios se hacen en la Vista Administrador del turnero IVR.")
            cambios = (estados_ivr() or {}).get("cambios", [])
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
            st.subheader("📜 Log de Asignaciones")
            st.caption("Cada asignación, con la lista de siguientes en ese momento.")
            df_log = obtener_log_saltos_df(obtener_turnero_para_mostrar()["historial"])
            if df_log.empty:
                st.info("Aún no hay registros en el log.")
            else:
                st.dataframe(df_log, use_container_width=True, hide_index=True)
                st.download_button(
                    label="📥 Descargar Log de Asignaciones (CSV)",
                    data=df_log.to_csv(index=False).encode("utf-8"),
                    file_name=f"log_asignaciones_atc_{obtener_fecha_hora_colombia().strftime('%Y%m%d_%H%M')}.csv",
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
