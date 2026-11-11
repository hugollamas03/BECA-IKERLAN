"""Tabla de eventos por celda: en que ciclo empieza a cambiar cada señal, y cuanto se adelanta o retrasa
respecto a la caida de la eficiencia coulombica (CE). Guarda 3 CSV en conclusiones/.

    python tabla_eventos.py                 -> las 8 celdas
    python tabla_eventos.py --celda 23 44   -> solo esas

Definicion de "empieza a cambiar" (la misma que buscar_picos.py para la CE, extendida a las demas señales):
  - base = mediana de la señal en los primeros N_BASE ciclos (la etapa estable)
  - evento = primer ciclo de una racha de PERSISTENCIA ciclos seguidos que cumplen la regla (SENALES, abajo)
  - un ciclo sin dato (p. ej. sin IR de carga) rompe la racha; si la regla nunca se cumple, la celda queda vacia
Todas las señales salen de funciones que ya existen (ciclos.py, plot_IR.py, plot_reposo.py): aqui no se recalcula nada.

Salidas (conclusiones/):
  eventos_ciclo.csv      ciclo del evento de cada señal, por celda
  eventos_vs_CE.csv      lo mismo menos el ciclo de la caida de CE (negativo = la señal cambia ANTES que la CE)
  resumen_por_senal.csv  por señal: en cuantas celdas ocurre y estadisticos de esa diferencia
"""
import argparse

import numpy as np
import pandas as pd

import config as cfg
from buscar_picos import N_BASE, PERSISTENCIA
from ciclos import agregar_energia
from data_loader import buscar_celdas, cargar_celda
from plot_IR import calcular_IR
from plot_reposo import tiempo_reposo

CARPETA = getattr(cfg, "CONCLUSIONES", cfg.INFORMES.parent / "conclusiones")
CARPETA.mkdir(exist_ok=True)

REF = "CE_caida3pp"            # señal de referencia para las diferencias
# (clave, descripcion de la regla, serie, tipo de regla, umbral)
SENALES = [
    ("CE_caida3pp",     "CE por debajo de su base en 3 pp",                     "CE_%",            "caida_abs",  3.0),
    ("Q_perd10",        "perdida de capacidad >= 10 % (100 % = media de los 5 primeros ciclos)", "perdida_celda_%", "mayor_igual", 10.0),
    ("Q_perd20",        "perdida de capacidad >= 20 % (idem)",                  "perdida_celda_%", "mayor_igual", 20.0),
    ("EQdesc_3pct",     "|E/Q descarga - 1| > 0,03",                            "EQ_desc",         "desvio_de_1", 0.03),
    ("EQcarga_3pct",    "|E/Q carga - 1| > 0,03",                               "EQ_carga",        "desvio_de_1", 0.03),
    ("IRdesc2s_+25",    "IR descarga (2 s) > base + 25 %",                      "IR_desc_2s",      "sube_rel",   0.25),
    ("IRdesc2s_x2",     "IR descarga (2 s) > 2 x base",                         "IR_desc_2s",      "sube_rel",   1.0),
    ("IRdesc30s_+25",   "IR descarga (30 s) > base + 25 %",                     "IR_desc_30s",     "sube_rel",   0.25),
    ("IRcarga2s_+25",   "IR carga (2 s) > base + 25 %",                         "IR_carga_2s",     "sube_rel",   0.25),
    ("dTcarga_+3C",     "ΔT en carga > base + 3 °C",                            "dT_carga",        "sube_abs",   3.0),
    ("repcarga_+60s",   "reposo tras la carga (step 6) > base + 60 s",          "reposo_carga",    "sube_abs",   60.0),
    ("repdesc_+60s",    "reposo tras la descarga (step 8) > base + 60 s",       "reposo_desc",     "sube_abs",   60.0),
]


# ----------------------------------------------------------------------------
# Detector
# ----------------------------------------------------------------------------
def condicion(s, regla, u):
    """Serie booleana por ciclo: True donde la señal cumple la regla (NaN -> False)."""
    base = float(s.loc[s.index <= N_BASE].median())
    if regla == "caida_abs":
        return s < base - u
    if regla == "sube_rel":
        return s > base * (1 + u)
    if regla == "sube_abs":
        return s > base + u
    if regla == "mayor_igual":
        return s >= u
    if regla == "desvio_de_1":
        return (s - 1).abs() > u
    raise ValueError(regla)


def primer_ciclo(cond, persistencia=PERSISTENCIA):
    """Primer ciclo de una racha de `persistencia` ciclos seguidos con cond True. None si no ocurre."""
    racha = cond.astype(int).rolling(persistencia).sum() == persistencia
    pos = np.flatnonzero(racha.values)
    return None if len(pos) == 0 else int(cond.index[pos[0] - persistencia + 1])


def series_celda(d):
    """Las señales por ciclo de una celda (todas indexadas por el ciclo del resumen)."""
    r, canal = d["resumen"], d["canal"]
    e = agregar_energia(r)
    ir2, ir30 = calcular_IR(canal, 2.0).reindex(r.index), calcular_IR(canal, 30.0).reindex(r.index)
    rp = tiempo_reposo(canal, r.index)
    return {"CE_%": r["CE_%"], "perdida_celda_%": e["perdida_celda_%"], "EQ_desc": e["EQ_desc"], "EQ_carga": e["EQ_carga"],
            "IR_desc_2s": ir2["IR_desc_mOhm"], "IR_carga_2s": ir2["IR_carga_mOhm"], "IR_desc_30s": ir30["IR_desc_mOhm"],
            "dT_carga": r["dT_carga"], "reposo_carga": rp["reposo_carga_s"], "reposo_desc": rp["reposo_desc_s"]}


def eventos(series):
    return {clave: primer_ciclo(condicion(series[col], regla, u)) for clave, _, col, regla, u in SENALES}


# ----------------------------------------------------------------------------
# Tablas
# ----------------------------------------------------------------------------
def tablas(datos):
    claves = [s[0] for s in SENALES]
    filas = [{"celda": d["num"], "voltaje": d["voltaje"], "n_ciclos": len(d["resumen"]), **eventos(series_celda(d))}
             for d in datos]
    ev = pd.DataFrame(filas).sort_values(["voltaje", "celda"], ascending=[False, True]).reset_index(drop=True)
    ev[claves] = ev[claves].astype("Int64")
    otras = [c for c in claves if c != REF]
    dif = ev[["celda", "voltaje"]].copy()
    dif[REF] = ev[REF]                                    # ciclo de referencia, para tenerlo a la vista
    for c in otras:
        dif[c] = ev[c] - ev[REF]
    res = []
    for clave, regla, _, _, _ in SENALES:
        if clave == REF:
            continue
        x = dif[clave].dropna().astype(float)
        res.append({"señal": clave, "regla": regla, "celdas_con_evento": f"{len(x)}/{int(dif[REF].notna().sum())}",
                    "dif_mediana": x.median() if len(x) else np.nan, "dif_min": x.min() if len(x) else np.nan,
                    "dif_max": x.max() if len(x) else np.nan, "celdas_antes_de_CE": int((x < 0).sum()),
                    "celdas_igual_que_CE": int((x == 0).sum()), "celdas_despues_de_CE": int((x > 0).sum())})
    return ev, dif, pd.DataFrame(res)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--celda", type=int, nargs="*")
    a = ap.parse_args()
    datos = [cargar_celda(n, verbose=False) for n in (a.celda or sorted(buscar_celdas()))]
    ev, dif, res = tablas(datos)
    print(f"\nBase = mediana de los {N_BASE} primeros ciclos; {PERSISTENCIA} ciclos seguidos para dar el evento. Vacio = no ocurre.")
    print("\nCiclo en que empieza cada cambio:\n")
    print(ev.to_string(index=False))
    print(f"\nDiferencia respecto a la caida de CE ({REF}); negativo = la señal cambia ANTES:\n")
    print(dif.to_string(index=False))
    print("\nResumen por señal:\n")
    print(res.to_string(index=False))
    for nombre, t in (("eventos_ciclo", ev), ("eventos_vs_CE", dif), ("resumen_por_senal", res)):
        t.to_csv(CARPETA / f"{nombre}.csv", sep=";", decimal=",", index=False, encoding="utf-8-sig")
    print(f"\nguardado en {CARPETA}")
