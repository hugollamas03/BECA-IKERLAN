"""Lectura de los Excel de ciclado continuo + cache en Parquet.

La cache guarda SOLO lo lento y determinista: hojas leidas, columnas normalizadas
y canales concatenados. Todo lo derivado (resumen por ciclo, FEC...) se calcula al
cargar (ciclos.py), asi que cambiar esos calculos no obliga a regenerar la cache.
Si cambia la lectura/normalizacion de aqui, subir CACHE_VERSION en config.py.

Uso:
    python data_loader.py              -> procesa las 8 celdas (usa cache si esta al dia)
    python data_loader.py --forzar     -> regenera la cache
    python data_loader.py --celda 23   -> solo una celda
"""
import argparse
import re
import time

import numpy as np
import pandas as pd

import config as cfg
from ciclos import ciclos_corregidos, construir_resumen, informe_anomalias, recortar_resumen


# ----------------------------------------------------------------------------
# Localizacion de archivos
# ----------------------------------------------------------------------------
def _clave_natural(path):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", path.name)]


def buscar_celdas():
    """{num_celda: {'voltaje': float, 'canal': [xlsx...], 'stats': xlsx|None}}"""
    celdas = {}
    for carpeta in sorted(cfg.RAW.iterdir()):
        m = re.match(cfg.PATRON_CARPETA_CELDA, carpeta.name)
        if not (carpeta.is_dir() and m):
            continue
        subs = [s for s in carpeta.iterdir()
                if s.is_dir() and s.name.startswith(cfg.PREFIJO_CARPETA_CICLADO)]
        if len(subs) != 1:
            print(f"AVISO: {carpeta.name}: {len(subs)} carpetas '{cfg.PREFIJO_CARPETA_CICLADO}*', se omite")
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
NOMBRE_TEMP = {"1": "T_amb", "2": "T_celda"}     # Aux 1 = ambiente, Aux 2 = celda


def _renombrar(c):
    c = str(c).strip()
    m = re.match(r"^Aux_Temperature\D*(\d)\D*$", c)     # equipo v7 y v8
    if m:
        return NOMBRE_TEMP[m.group(1)]
    m = re.match(r"^Aux_dT/dt\D*(\d)\D*$", c)
    if m:
        return f"d{NOMBRE_TEMP[m.group(1)]}_dt"
    if c.lower() == "discharge_time(s)":                # 'DisCharge_Time(s)' en v7
        return "Discharge_Time(s)"
    return c


def _normalizar(df):
    df = df.copy()
    df.columns = [_renombrar(c) for c in df.columns]
    if "Date_Time" in df.columns and not pd.api.types.is_datetime64_any_dtype(df["Date_Time"]):
        txt = df["Date_Time"].astype(str).str.replace(",", ".", regex=False).str.strip()
        df["Date_Time"] = pd.to_datetime(txt, format="%m/%d/%Y %H:%M:%S.%f", errors="coerce")
    return df.drop(columns=["Voltage(mV)", "Current(mA)"], errors="ignore")


def _hojas(xl):
    n = xl.sheet_names
    canal = next((s for s in n if re.match(r"^channel[-_]\d+_\d+$", s, re.I)), None)  # el 'Statistices' no la tiene
    ciclo = next(s for s in n if s.lower().startswith("statisticsbycycle"))
    step = next(s for s in n if s.lower().startswith("statisticsbystep"))
    return canal, ciclo, step


# ----------------------------------------------------------------------------
# Lectura de una celda (lento) -> canal, resumen Arbin por ciclo, resumen Arbin por step
# ----------------------------------------------------------------------------
def _leer_excels(info):
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

    # Las hojas de estadisticas de todos los archivos deben coincidir con la de referencia
    for f, c in zip(info["canal"], ciclos_por_archivo):
        comunes = [k for k in ("Cycle_Index", "Charge_Capacity(Ah)", "Discharge_Capacity(Ah)")
                   if k in c and k in ciclo_ref]
        if c.shape[0] != ciclo_ref.shape[0] or not all(
                np.allclose(c[k], ciclo_ref[k], equal_nan=True) for k in comunes):
            avisos.append(f"StatisticsByCycle de {f.name} NO coincide con la de referencia ({origen})")

    canal = pd.concat(canales, ignore_index=True)
    if "Date_Time" in canal and canal["Date_Time"].isna().any():
        avisos.append(f"{int(canal['Date_Time'].isna().sum())} fechas no interpretadas (NaT)")
    return canal, ciclo_ref, step_ref, avisos


def cargar_celda(num, forzar=False, verbose=True):
    celdas = buscar_celdas()
    if num not in celdas:
        raise KeyError(f"Celda {num} no encontrada. Disponibles: {sorted(celdas)}")
    info = celdas[num]
    v = cfg.CACHE_VERSION
    rutas = {k: cfg.CACHE / f"C{num}_{k}_v{v}.parquet" for k in ("canal", "arbin_ciclo", "arbin_step")}
    fuentes = info["canal"] + ([info["stats"]] if info["stats"] else [])
    mtime_src = max(f.stat().st_mtime for f in fuentes)

    if not forzar and all(r.exists() and r.stat().st_mtime >= mtime_src for r in rutas.values()):
        if verbose:
            print(f"C{num}: cache al dia")
        tablas = {k: pd.read_parquet(r) for k, r in rutas.items()}
    else:
        print(f"C{num}: leyendo {len(info['canal'])} Excel de canal ...")
        canal, ciclo, step, avisos = _leer_excels(info)
        tablas = {"canal": canal, "arbin_ciclo": ciclo, "arbin_step": step}
        for k, df in tablas.items():
            df.to_parquet(rutas[k], index=False)
        for a in avisos:
            print(f"   AVISO C{num}: {a}")

    # --- Derivados (rapidos, no se cachean) ---
    completo = construir_resumen(tablas["canal"])
    anom = informe_anomalias(completo, tablas["arbin_ciclo"])
    anom.to_csv(cfg.INFORMES / f"C{num}_anomalias.csv", sep=";", decimal=",", index=False, encoding="utf-8-sig")
    resumen, omitidos = recortar_resumen(completo, tablas["arbin_ciclo"])
    return {**tablas, "resumen": resumen, "omitidos": omitidos, "anomalias": anom,
            "voltaje": info["voltaje"], "num": num}


def imprimir_resumen(d):
    r, a = d["resumen"], d["anomalias"]
    print(f"   C{d['num']} ({d['voltaje']} V): {len(r)} ciclos mostrados, filas de canal {d['canal'].shape[0]}")
    if d["omitidos"]:
        print(f"   ciclos finales omitidos (sin resumen de Arbin, fin del ensayo): {d['omitidos']}")
    fix = ciclos_corregidos(a)
    if fix:
        print(f"   ciclos cuyo dato Arbin faltaba o era erroneo (ahora desde canal): {fix}")
    for motivo, n in a["motivo"].value_counts().items():
        print(f"      - {motivo}: {n}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--celda", type=int, nargs="*", help="numeros de celda (por defecto todas)")
    ap.add_argument("--forzar", action="store_true", help="regenerar la cache")
    a = ap.parse_args()
    todas = buscar_celdas()
    print(f"Celdas encontradas: {sorted(todas)}")
    for n in (a.celda or sorted(todas)):
        imprimir_resumen(cargar_celda(n, forzar=a.forzar))
    print(f"\nInformes de anomalias en: {cfg.INFORMES}")
