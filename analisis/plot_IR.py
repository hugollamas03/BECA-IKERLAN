"""Resistencia aparente (IR = ΔV / I) tras el reposo, frente al ciclo, de todas las celdas en una figura.

    python plot_IR.py                         -> Δt = 2 s y 30 s, las 8 celdas
    python plot_IR.py --dt 2 30 60            -> otros Δt (un HTML y un CSV por cada uno, sin sobrescribir)
    python plot_IR.py --celda 23 44           -> solo esas celdas
    python plot_IR.py --cada 10               -> solo 1 de cada 10 ciclos ANTES de (ciclo de la caida de CE - 30)

Definicion (I = capacidad nominal / 2 = C/2; resultado en mΩ):
  descarga: IR = (V al final del reposo step 6 - V a Δt del inicio del step 7) / I
  carga:    IR = (V a Δt del inicio del step 5 - V al final del reposo step 8 previo) / I
V a Δt se INTERPOLA linealmente entre los dos puntos que rodean a Δt (el canal no tiene un punto en Δt exacto).
La transicion se detecta por filas consecutivas del canal: el step 8 de un ciclo y el step 5 del siguiente
pueden tener distinto Cycle_Index (entre ellos estan los steps 9 y 10). El ciclo 1 no tiene IR de carga (antes
del step 5 va el protocolo inicial, steps 1-4). Cada punto se asigna al ciclo del step de corriente.
Si el step no llega a Δt o su Step_Time retrocede, el punto queda vacio.

Solo LEE el canal. Salidas: figuras\\comparativas\\comparativa_IR_dt{Δt}s.html e informes\\IR_dt{Δt}s.csv
"""
import argparse

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import config as cfg
from buscar_picos import ce_base, ciclo_caida
from data_loader import buscar_celdas, cargar_celda
from plot_reposo import _col_tiempo_paso

COLOR_V = {3.8: "#2ca02c", 3.9: "#1f77b4", 4.0: "#ff7f0e", 4.1: "#d62728"}
STEP_CARGA, STEP_REPOSO_TRAS_CARGA, STEP_DESC, STEP_REPOSO_TRAS_DESC = 5, 6, 7, 8
STEPS_INTERMEDIOS = (9, 10)         # entre el reposo tras la descarga (8) y la carga siguiente (5)
I_A = cfg.CAP_NOMINAL_AH / 2        # C/2 nominal (la corriente medida es ~0,7499 A)
DT_DEFECTO = (2.0, 30.0)
ATRAS_SUBMUESTREO = 30              # con --cada, se muestran todos los ciclos desde (caida - 30)
UMBRAL_CAIDA_PP = 3.0               # misma caida de CE que plot_curvas_carga.py
CARPETA = getattr(cfg, "FIG_COMPARATIVAS", cfg.FIGURAS)


# ----------------------------------------------------------------------------
# Calculo
# ----------------------------------------------------------------------------
def _bloques(canal):
    """Bloques de filas consecutivas con el mismo (step, ciclo): arrays step, ciclo, inicio, fin (exclusivo)."""
    col_t = _col_tiempo_paso(canal)
    faltan = [c for c in ("Step_Index", "Cycle_Index", "Voltage(V)") if c not in canal.columns]
    if faltan:
        raise KeyError(f"Faltan columnas {faltan}. Columnas del canal: {list(canal.columns)}")
    step, cic = canal["Step_Index"].to_numpy(), canal["Cycle_Index"].to_numpy()
    cambio = np.flatnonzero((step[1:] != step[:-1]) | (cic[1:] != cic[:-1])) + 1
    ini, fin = np.r_[0, cambio], np.r_[cambio, len(step)]
    return step[ini], cic[ini], ini, fin, canal[col_t].to_numpy(float), canal["Voltage(V)"].to_numpy(float)


def _v_en(t, v, dt):
    """(V interpolada a Δt, hueco entre los dos puntos usados). (nan, nan) si el step no llega a Δt o t retrocede."""
    if len(t) < 2 or t[-1] < dt or np.any(np.diff(t) < 0):
        return np.nan, np.nan
    k = int(np.searchsorted(t, dt))                 # primer punto con t >= Δt
    if t[k] == dt or k == 0:
        return float(v[k]), 0.0
    return float(np.interp(dt, t, v)), float(t[k] - t[k - 1])


def calcular_IR(canal, dt):
    """DataFrame indexado por ciclo: IR_desc_mOhm, hueco_desc_s, IR_carga_mOhm, hueco_carga_s."""
    step, cic, ini, fin, t, v = _bloques(canal)
    desc, carga = {}, {}
    for k in range(len(step)):
        if step[k] == STEP_DESC and k > 0 and step[k - 1] == STEP_REPOSO_TRAS_CARGA:
            v_dt, hueco = _v_en(t[ini[k]:fin[k]], v[ini[k]:fin[k]], dt)
            desc[int(cic[k])] = ((v[fin[k - 1] - 1] - v_dt) / I_A * 1000, hueco)
        elif step[k] == STEP_CARGA:
            j = k - 1
            while j >= 0 and step[j] in STEPS_INTERMEDIOS:
                j -= 1
            if j >= 0 and step[j] == STEP_REPOSO_TRAS_DESC:
                v_dt, hueco = _v_en(t[ini[k]:fin[k]], v[ini[k]:fin[k]], dt)
                carga[int(cic[k])] = ((v_dt - v[fin[j] - 1]) / I_A * 1000, hueco)
    d = pd.DataFrame.from_dict(desc, orient="index", columns=["IR_desc_mOhm", "hueco_desc_s"])
    c = pd.DataFrame.from_dict(carga, orient="index", columns=["IR_carga_mOhm", "hueco_carga_s"])
    return d.join(c, how="outer").sort_index()


def mascara_submuestreo(r, cada):
    """True en los ciclos que se dibujan: todos si cada <= 1 o si no hay caida de CE detectada; si no, 1 de cada
    `cada` antes de (ciclo de la caida - 30) y todos desde ahi."""
    idx = r.index
    if cada <= 1:
        return pd.Series(True, index=idx)
    c = ciclo_caida(r["CE_%"], UMBRAL_CAIDA_PP, ce_base(r["CE_%"]))
    if c is None:
        return pd.Series(True, index=idx)
    return pd.Series((idx >= c - ATRAS_SUBMUESTREO) | ((idx - idx.min()) % cada == 0), index=idx)


# ----------------------------------------------------------------------------
# Figura
# ----------------------------------------------------------------------------
def figura_IR(datos, dt, cada):
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.08,
                        subplot_titles=(f"IR en descarga (reposo step {STEP_REPOSO_TRAS_CARGA} -> descarga step {STEP_DESC})",
                                        f"IR en carga (reposo step {STEP_REPOSO_TRAS_DESC} -> carga step {STEP_CARGA})"))
    for d in datos:
        ir, m = d["ir"], d["mask"]
        for fila, col in ((1, "IR_desc_mOhm"), (2, "IR_carga_mOhm")):
            s = ir.loc[m, col]
            fig.add_trace(go.Scatter(x=s.index, y=s, mode="lines+markers", marker=dict(size=4),
                                     line=dict(color=COLOR_V.get(d["voltaje"], "grey")),
                                     name=f"C{d['num']} ({d['voltaje']} V)", legendgroup=f"C{d['num']}",
                                     showlegend=(fila == 1)), row=fila, col=1)
    for fila in (1, 2):
        fig.update_yaxes(title_text="IR (mΩ)", row=fila, col=1)
    fig.update_xaxes(title_text="Ciclo", row=2, col=1)
    extra = f"; 1 de cada {cada} ciclos antes de (caida de CE - {ATRAS_SUBMUESTREO})" if cada > 1 else ""
    fig.update_layout(title=f"IR = ΔV / I a Δt = {dt:g} s (I = {I_A:g} A) - ciclado continuo{extra}",
                      height=900, template="plotly_white", hovermode="closest")
    return fig


def informar(d, dt):
    ir, r = d["ir"], d["resumen"]
    nd, nc = int(ir["IR_desc_mOhm"].notna().sum()), int(ir["IR_carga_mOhm"].notna().sum())
    c10 = ir.loc[10] if 10 in ir.index else None
    txt = f"   C{d['num']} ({d['voltaje']} V): {nd}/{len(ir)} ciclos con IR en descarga, {nc}/{len(ir)} en carga"
    if c10 is not None:
        txt += f" | ciclo 10: desc {c10['IR_desc_mOhm']:.1f} mΩ, carga {c10['IR_carga_mOhm']:.1f} mΩ"
    txt += (f" | hueco max. entre puntos interpolados: desc {ir['hueco_desc_s'].max():.1f} s, "
            f"carga {ir['hueco_carga_s'].max():.1f} s")
    print(txt)
    retro = [int(c) for c in r.index[r["retroceso_tiempo"]] if pd.notna(ir.loc[c, ["IR_desc_mOhm", "IR_carga_mOhm"]]).any()]
    if retro:
        print(f"      ciclos con retroceso de Test_Time que tienen IR (revisar): {retro}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--celda", type=int, nargs="*")
    ap.add_argument("--dt", type=float, nargs="*", default=list(DT_DEFECTO), help="Δt en segundos (defecto: 2 30)")
    ap.add_argument("--cada", type=int, default=1, help="1 de cada N ciclos en la fase previa a la caida (defecto 1 = todos)")
    a = ap.parse_args()
    datos = [cargar_celda(n, verbose=False) for n in (a.celda or sorted(buscar_celdas()))]
    for dt in a.dt:
        print(f"\nΔt = {dt:g} s, I = {I_A:g} A")
        filas = []
        for d in datos:
            d["ir"] = calcular_IR(d["canal"], dt).reindex(d["resumen"].index)
            d["mask"] = mascara_submuestreo(d["resumen"], a.cada)
            informar(d, dt)
            t = d["ir"].round(3).rename_axis("ciclo").reset_index()
            t.insert(0, "voltaje", d["voltaje"])
            t.insert(0, "celda", d["num"])
            filas.append(t)
        ruta_csv = cfg.INFORMES / f"IR_dt{dt:g}s.csv"
        pd.concat(filas).to_csv(ruta_csv, sep=";", decimal=",", index=False, encoding="utf-8-sig")
        ruta = CARPETA / f"comparativa_IR_dt{dt:g}s.html"
        figura_IR(datos, dt, a.cada).write_html(ruta, include_plotlyjs=True)
        print("   guardados", ruta_csv.name, "y", ruta)
