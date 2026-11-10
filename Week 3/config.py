from pathlib import Path

ANALISIS = Path(__file__).resolve().parent
BASE = ANALISIS.parent                    # ...\DOCUMENTOS
RAW = BASE / "00 - Raw data"
SCHEDULERS = BASE / "schedulers"
CACHE = ANALISIS / "cache"
FIGURAS = ANALISIS / "figuras"

PATRON_CARPETA_CELDA = r"^C(\d+) - (\d\.\d) V standard cycling - continuous$"
PREFIJO_CARPETA_CICLADO = "04_"

CACHE.mkdir(exist_ok=True)
FIGURAS.mkdir(exist_ok=True)
