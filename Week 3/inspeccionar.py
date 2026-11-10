"""Inspección de los Excel de ciclado continuo. Solo lectura.
Genera analisis/informe_inspeccion.txt"""
import re
import pandas as pd
from config import RAW, PATRON_CARPETA_CELDA, PREFIJO_CARPETA_CICLADO

lineas = []
def p(txt=""):
    print(txt)
    lineas.append(str(txt))

def buscar_excels():
    resultado = []
    for carpeta in sorted(RAW.iterdir()):
        m = re.match(PATRON_CARPETA_CELDA, carpeta.name)
        if not (carpeta.is_dir() and m):
            continue
        for sub in sorted(carpeta.iterdir()):
            if sub.is_dir() and sub.name.startswith(PREFIJO_CARPETA_CICLADO):
                for f in sorted(sub.glob("*.xlsx")):
                    if not f.name.startswith("~$"):
                        resultado.append((int(m.group(1)), m.group(2), f))
    return resultado

def resumen_hoja(nombre, df):
    p(f"  Hoja '{nombre}': {df.shape[0]} filas x {df.shape[1]} columnas")
    if "global" in nombre.lower():
        p(f"    Celda C5 (scheduler): {df.iloc[4, 2] if df.shape[0] > 4 and df.shape[1] > 2 else 'n/a'}")
        p(f"    Celda C4 (etiqueta): {df.iloc[3, 2] if df.shape[0] > 4 and df.shape[1] > 1 else 'n/a'}")
        return
    p("    Columnas y tipos:")
    for c, t in df.dtypes.items():
        p(f"      {c!r}: {t}")
    for col in ("Cycle_Index", "Test_Time(s)"):
        if col in df.columns:
            s = pd.to_numeric(df[col], errors="coerce")
            p(f"    {col}: min={s.min()}  max={s.max()}")
    p(f"    Primera fila: {df.iloc[0].to_dict()}" if len(df) else "    (vacía)")

archivos = buscar_excels()
p(f"Excel encontrados: {len(archivos)}")
for celda, v, f in archivos:
    p("\n" + "=" * 90)
    p(f"C{celda} | {v} V | {f.name} | {f.stat().st_size / 1e6:.1f} MB")
    try:
        hojas = pd.read_excel(f, sheet_name=None, engine="calamine",
                              header=None if False else 0)
    except Exception as e:
        p(f"  ERROR leyendo: {e}")
        continue
    p(f"  Hojas: {list(hojas)}")
    for nombre, df in hojas.items():
        if "global" in nombre.lower():
            df = pd.read_excel(f, sheet_name=nombre, engine="calamine", header=None)
        resumen_hoja(nombre, df)

(RAW.parent / "analisis" / "informe_inspeccion.txt").write_text(
    "\n".join(lineas), encoding="utf-8")