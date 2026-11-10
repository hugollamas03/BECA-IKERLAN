from pathlib import Path

ANALISIS = Path(__file__).resolve().parent
BASE = ANALISIS.parent                    # ...\DOCUMENTOS
RAW = BASE / "00 - Raw data"
SCHEDULERS = BASE / "schedulers"
CACHE = ANALISIS / "cache"
FIGURAS = ANALISIS / "figuras"
INFORMES = ANALISIS / "informes"
FIG_CURVAS = FIGURAS / "curvas_carga"
FIG_COMPARATIVAS = FIGURAS / "comparativas"
FIG_DEGRADACION = FIGURAS / "degradacion"

for _d in (CACHE, FIGURAS, INFORMES, FIG_CURVAS, FIG_COMPARATIVAS, FIG_DEGRADACION):
    _d.mkdir(exist_ok=True)

PATRON_CARPETA_CELDA = r"^C(\d+) - (\d\.\d) V standard cycling - continuous$"
PREFIJO_CARPETA_CICLADO = "04_"

# Si cambia la lectura/normalizacion del loader, subir este numero: invalida la cache vieja.
CACHE_VERSION = 2

# --- Temperaturas (Aux 1 = ambiente, Aux 2 = celda) ---
# ΔT de cada fase (carga / descarga):
#   "ambiente"    -> max(T_celda - T_amb) dentro de la fase
#   "inicio_fase" -> max(T_celda) - T_celda en el primer punto de la fase
DELTA_T_REFERENCIA = "ambiente"
UMBRAL_CORRIENTE_A = 0.05      # |I| > umbral => carga (I>0) o descarga (I<0)

# --- Deteccion de incidencias en el canal ---
SALTO_TIEMPO_S = 1.0           # retroceso de Test_Time mayor que esto => 'retroceso'
PAUSA_FECHA_H = 1.0            # hueco de Date_Time mayor que esto => 'pausa larga'
TOL_CAPACIDAD_AH = 0.005       # diferencia canal vs Arbin que se considera discrepancia

# --- FEC ---
N_CICLOS_REF = 5               # C_nom de cada celda = media de Q_descarga de sus primeros N ciclos
CAP_NOMINAL_AH = 1.5           # capacidad nominal del fabricante

for _d in (CACHE, FIGURAS, INFORMES):
    _d.mkdir(exist_ok=True)
