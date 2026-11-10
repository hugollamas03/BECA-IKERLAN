"""Curvas de carga (step 5) de cada ciclo: voltaje (continua, eje izq.) y ΔT (discontinua, eje dcha.)
frente al tiempo de paso, una linea por ciclo coloreada por numero de ciclo. Una figura por celda.

    python plot_curvas_carga.py                       -> las 8 celdas
    python plot_curvas_carga.py --celda 44 45         -> solo esas
    python plot_curvas_carga.py --atras 20            -> empezar 20 ciclos antes de la caida (defecto 30)
    python plot_curvas_carga.py --umbral 4            -> caida de CE de 4 pp (defecto 3)
    python plot_curvas_carga.py --despues 15          -> mantener 15 ciclos tras la caida (defecto 10)

Ventana: desde (ciclo de la caida de CE - ATRAS) hasta (ciclo de la caida + DESPUES), sin pasar del ultimo
ciclo mostrado de la celda (--despues 9999 = hasta el final). El ciclo de la caida sale de buscar_picos.ciclo_caida (mismo metodo y persistencia).
Solo LEE el canal: no modifica ciclos.py, data_loader.py ni los otros scripts.
Salida: figuras\\C##_curvas_carga.html
"""
import argparse

import plotly.colors as pc
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import config as cfg
from buscar_picos import ce_base, ciclo_caida
from data_loader import buscar_celdas, cargar_celda
from plot_reposo import _col_tiempo_paso

STEP_CARGA = 5          # carga CC C/2 en el scheduler (hipotesis: igual en los 4 schedulers)
ATRAS = 30              # ciclos antes de la caida con los que empieza la ventana
DESPUES = 30            # ciclos despues de la caida con los que termina la ventana (valor provisional, a ajustar)
UMBRAL_PP = 3.0         # caida de CE (puntos porcentuales) que define el ciclo critico
ESCALA = "Turbo"


def curvas_carga(canal, ciclos):
    """{ciclo: (tiempo de paso en min, voltaje V, ΔT °C)} de las filas del step de carga de esos ciclos.
    ΔT segun cfg.DELTA_T_REFERENCIA: T_celda - T_amb, o T_celda - T_celda al inicio del step."""
    col_t = _col_tiempo_paso(canal)
    cols = [col_t, "Voltage(V)", "T_celda", "T_amb", "Cycle_Index"]
    faltan = [c for c in cols if c not in canal.columns]
    if faltan:
        raise KeyError(f"Faltan columnas {faltan}. Columnas del canal: {list(canal.columns)}")
    sub = canal.loc[(canal["Step_Index"] == STEP_CARGA) & canal["Cycle_Index"].isin(list(ciclos)), cols]
    out = {}
    for c, g in sub.groupby("Cycle_Index", sort=True):
        dT = g["T_celda"] - (g["T_amb"] if cfg.DELTA_T_REFERENCIA == "ambiente" else g["T_celda"].iloc[0])
        out[int(c)] = (g[col_t].values / 60, g["Voltage(V)"].values, dT.values)
    return out


def ventana(d, atras=ATRAS, umbral=UMBRAL_PP, despues=DESPUES):
    """(ciclo_caida, primer ciclo, ultimo ciclo) o None si la celda no tiene caida con ese umbral."""
    r = d["resumen"]
    c = ciclo_caida(r["CE_%"], umbral, ce_base(r["CE_%"]))
    if c is None:
        return None
    return c, max(int(r.index.min()), c - atras), min(int(r.index.max()), c + despues)


def figura_curvas(d, curvas, c_caida, umbral):
    ciclos = sorted(curvas)
    c0, c1 = ciclos[0], ciclos[-1]
    cols = pc.sample_colorscale(ESCALA, [(c - c0) / max(c1 - c0, 1) for c in ciclos])
    ref = "T_celda - T_amb" if cfg.DELTA_T_REFERENCIA == "ambiente" else "T_celda - T_celda al inicio del step"
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    for c, col in zip(ciclos, cols):
        t, v, dt = curvas[c]
        kw = dict(x=t, legendgroup=f"c{c}", showlegend=False, hovertemplate=f"ciclo {c}<br>%{{x:.1f}} min, %{{y:.3f}}<extra></extra>")
        fig.add_trace(go.Scatter(y=v, mode="lines", line=dict(color=col, width=1), **kw), secondary_y=False)
        fig.add_trace(go.Scatter(y=dt, mode="lines", line=dict(color=col, width=1, dash="dash"), **kw), secondary_y=True)
    fig.add_trace(go.Scatter(x=[None], y=[None], mode="markers", showlegend=False, hoverinfo="skip",
                             marker=dict(colorscale=ESCALA, cmin=c0, cmax=c1, color=[c0], showscale=True,
                                         colorbar=dict(title="Ciclo", thickness=15))), secondary_y=False)
    fig.update_xaxes(title_text="Tiempo de paso (min)")
    fig.update_yaxes(title_text="Voltaje (V)", secondary_y=False)
    fig.update_yaxes(title_text=f"ΔT (°C) ({ref})", secondary_y=True, showgrid=False)
    fig.update_layout(title=f"C{d['num']} ({d['voltaje']} V) - carga (step {STEP_CARGA}), ciclos {c0}-{c1} "
                            f"(caida de CE de {umbral:g} pp en el ciclo {c_caida})",
                      height=700, template="plotly_white", hovermode="closest")
    return fig


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--celda", type=int, nargs="*")
    ap.add_argument("--atras", type=int, default=ATRAS)
    ap.add_argument("--umbral", type=float, default=UMBRAL_PP)
    ap.add_argument("--despues", type=int, default=DESPUES)
    a = ap.parse_args()
    for n in a.celda or sorted(buscar_celdas()):
        d = cargar_celda(n, verbose=False)
        w = ventana(d, a.atras, a.umbral, a.despues)
        if w is None:
            print(f"C{n}: sin caida de CE de {a.umbral:g} pp, se omite")
            continue
        c_caida, ini, fin = w
        curvas = curvas_carga(d["canal"], range(ini, fin + 1))
        r = d["resumen"]
        sin = [c for c in range(ini, fin + 1) if c not in curvas]
        avisos = {"retroceso de Test_Time": [c for c in curvas if bool(r.loc[c, "retroceso_tiempo"])],
                  "pausa larga en Date_Time": [c for c in curvas if bool(r.loc[c, "pausa_larga"])]}
        print(f"C{n} ({d['voltaje']} V): caida en ciclo {c_caida}; ventana {ini}-{fin} ({len(curvas)} curvas, "
              f"{sum(len(v[0]) for v in curvas.values())} puntos)")
        if sin:
            print(f"   ciclos sin filas de step {STEP_CARGA}: {sin}")
        for k, v in avisos.items():
            if v:
                print(f"   ciclos con {k} (la curva puede mostrar un salto): {v}")
        ruta = cfg.FIGURAS / cfg.FIG_CURVAS / f"C{n}_curvas_carga.html"
        figura_curvas(d, curvas, c_caida, a.umbral).write_html(ruta, include_plotlyjs=True)
        print("   guardada", ruta)
