"""Lectura de los Excel de ciclado continuo + cache en Parquet.

Uso:
    python data_loader.py              -> procesa las 8 celdas (usa cache si esta al dia)
    python data_loader.py --forzar     -> regenera la cache
    python data_loader.py --celda 23   -> solo una celda

Desde otros scripts:
    from data_loader import cargar_celda
    d = cargar_celda(23)      # dict con 'canal', 'ciclo', 'step', 'voltaje'
"""
import argparse
import re
import time

import numpy as np
import pandas as pd

from config import CACHE, PATRON_CARPETA_CELDA, PREFIJO_CARPETA_CICLADO, RAW


# ----------------------------------------------------------------------------
# Localizacion de archivos
# ----------------------------------------------------------------------------
def _clave_natural(path):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", path.name)]


def buscar_celdas():
    """{num_celda: {'voltaje': float, 'canal': [xlsx...], 'stats': xlsx|None}}"""
    celdas = {}
    for carpeta in sorted(RAW.iterdir()):
        m = re.match(PATRON_CARPETA_CELDA, carpeta.name)
        if not (carpeta.is_dir() and m):
            continue
        subs = [s for s in carpeta.iterdir()
                if s.is_dir() and s.name.startswith(PREFIJO_CARPETA_CICLADO)]
        if len(subs) != 1:
            print(f"AVISO: {carpeta.name}: {len(subs)} carpetas '{PREFIJO_CARPETA_CICLADO}*', se omite")
            continue
        xlsx = [f for f in subs[0].glob("*.xlsx") if not f.name.startswith("~$")]
        stats = [f for f in xlsx if "statistic" in f.name.lower()]
        canal = sorted([f for f in xlsx if f not in stats], key=_clave_natural)
        celdas[int(m.group(1))] = {
            "voltaje": float(m.group(2)),
            "canal": canal,
            "stats": stats[0] if stats else None,
        }
    return celdas


# ----------------------------------------------------------------------------
# Normalizacion
# ----------------------------------------------------------------------------
def _renombrar(c):
    c = str(c).strip()
    m = re.match(r"^Aux_Temperature\D*(\d)\D*$", c)     # equipo v7 y v8
    if m:
        return f"T{m.group(1)}_C"
    m = re.match(r"^Aux_dT/dt\D*(\d)\D*$", c)
    if m:
        return f"dT{m.group(1)}_dt"
    if c.lower() == "discharge_time(s)":                # 'DisCharge_Time(s)' en v7
        return "Discharge_Time(s)"
    return c


def _normalizar(df):
    df = df.copy()
    df.columns = [_renombrar(c) for c in df.columns]
    if "Date_Time" in df.columns and not pd.api.types.is_datetime64_any_dtype(df["Date_Time"]):
        txt = df["Date_Time"].astype(str).str.replace(",", ".", regex=False).str.strip()
        df["Date_Time"] = pd.to_datetime(txt, format="%m/%d/%Y %H:%M:%S.%f", errors="coerce")
    return df.drop(columns=["Voltage(mV)", "Current(mA)", "Data_Point"], errors="ignore")


def _hojas(xl):
    n = xl.sheet_names
    canal = next((s for s in n if re.match(r"^channel[-_]\d+_\d+$", s, re.I)), None)  # el 'Statistices' no la tiene
    ciclo = next(s for s in n if s.lower().startswith("statisticsbycycle"))
    step = next(s for s in n if s.lower().startswith("statisticsbystep"))
    return canal, ciclo, step


# ----------------------------------------------------------------------------
# Procesado de una celda
# ----------------------------------------------------------------------------
def _procesar(num, info):
    avisos = []
    canales, ciclos_por_archivo, steps_por_archivo = [], [], []
    for f in info["canal"]:
        t0 = time.time()
        xl = pd.ExcelFile(f, engine="calamine")
        h_canal, h_ciclo, h_step = _hojas(xl)
        canales.append(_normalizar(xl.parse(h_canal)))
        ciclos_por_archivo.append(_normalizar(xl.parse(h_ciclo)))
        steps_por_archivo.append(_normalizar(xl.parse(h_step)))
        print(f"   leido {f.name} ({time.time() - t0:.0f} s)")

    if info["stats"] is not None:
        xl = pd.ExcelFile(info["stats"], engine="calamine")
        _, h_ciclo, h_step = _hojas(xl)
        ciclo_ref, step_ref = _normalizar(xl.parse(h_ciclo)), _normalizar(xl.parse(h_step))
        origen = info["stats"].name
    else:
        ciclo_ref, step_ref = ciclos_por_archivo[0], steps_por_archivo[0]
        origen = info["canal"][0].name

    # Comprobacion: las hojas de estadisticas de todos los archivos coinciden con la de referencia
    for f, c in zip(info["canal"], ciclos_por_archivo):
        comunes = [k for k in ("Cycle_Index", "Charge_Capacity(Ah)", "Discharge_Capacity(Ah)")
                   if k in c and k in ciclo_ref]
        if c.shape[0] != ciclo_ref.shape[0] or not all(
                np.allclose(c[k], ciclo_ref[k], equal_nan=True) for k in comunes):
            avisos.append(f"StatisticsByCycle de {f.name} NO coincide con la de referencia ({origen})")

    canal = pd.concat(canales, ignore_index=True)

    # Comprobaciones del merge
    tt = canal["Test_Time(s)"]
    if (tt.diff().dropna() < 0).any():
        avisos.append("Test_Time(s) no es monotono creciente tras concatenar")
    if tt.duplicated().any():
        avisos.append(f"{int(tt.duplicated().sum())} filas con Test_Time(s) duplicado tras concatenar")
    if "Date_Time" in canal and canal["Date_Time"].isna().any():
        avisos.append(f"{int(canal['Date_Time'].isna().sum())} fechas no interpretadas (NaT)")

    # Resumen por ciclo + CE calculada + temperaturas por ciclo (desde el canal)
    ciclo = ciclo_ref.copy()
    ch, dh = ciclo["Charge_Capacity(Ah)"], ciclo["Discharge_Capacity(Ah)"]
    ciclo["CE_%"] = np.where(ch > 0, 100 * dh / ch, np.nan)

    g = canal.groupby("Cycle_Index")
    temp = pd.DataFrame({
        "T1_max": g["T1_C"].max(), "T1_min": g["T1_C"].min(),
        "T2_max": g["T2_C"].max(), "T2_min": g["T2_C"].min(),
    })
    temp["T1_rango"] = temp["T1_max"] - temp["T1_min"]
    temp["T2_rango"] = temp["T2_max"] - temp["T2_min"]
    ciclo = ciclo.merge(temp.reset_index(), on="Cycle_Index", how="left")

    idx = set(ciclo["Cycle_Index"])
    faltan = sorted(set(range(1, int(max(idx)) + 1)) - idx)
    if faltan:
        avisos.append(f"Ciclos ausentes en StatisticsByCycle: {faltan}")
    extra = sorted(int(c) for c in set(canal["Cycle_Index"].unique()) - idx)
    if extra:
        avisos.append(f"Ciclos en el canal sin fila en StatisticsByCycle (¿incompletos?): {extra}")

    return canal, ciclo, step_ref, avisos


def cargar_celda(num, forzar=False, verbose=True):
    celdas = buscar_celdas()
    if num not in celdas:
        raise KeyError(f"Celda {num} no encontrada. Disponibles: {sorted(celdas)}")
    info = celdas[num]
    rutas = {k: CACHE / f"C{num}_{k}.parquet" for k in ("canal", "ciclo", "step")}
    fuentes = info["canal"] + ([info["stats"]] if info["stats"] else [])
    mtime_src = max(f.stat().st_mtime for f in fuentes)

    al_dia = all(r.exists() and r.stat().st_mtime >= mtime_src for r in rutas.values())
    if al_dia and not forzar:
        if verbose:
            print(f"C{num}: cache al dia")
        out = {k: pd.read_parquet(r) for k, r in rutas.items()}
    else:
        print(f"C{num}: leyendo {len(info['canal'])} Excel de canal ...")
        canal, ciclo, step, avisos = _procesar(num, info)
        for k, df in (("canal", canal), ("ciclo", ciclo), ("step", step)):
            df.to_parquet(rutas[k], index=False)
        for a in avisos:
            print(f"   AVISO C{num}: {a}")
        if not avisos:
            print(f"   C{num}: comprobaciones OK")
        out = {"canal": canal, "ciclo": ciclo, "step": step}
    out["voltaje"] = info["voltaje"]
    out["num"] = num
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--celda", type=int, nargs="*", help="numeros de celda (por defecto todas)")
    ap.add_argument("--forzar", action="store_true", help="regenerar la cache")
    a = ap.parse_args()
    todas = buscar_celdas()
    print(f"Celdas encontradas: {sorted(todas)}")
    for n in (a.celda or sorted(todas)):
        d = cargar_celda(n, forzar=a.forzar)
        print(f"   C{n} ({d['voltaje']} V): canal {d['canal'].shape}, ciclo {d['ciclo'].shape}, "
              f"step {d['step'].shape}")
