"""Tiempo de reposo por ciclo tras la carga (step 6) y tras la descarga (step 8).

    python plot_reposo.py                 -> comparativa_reposo.html con todas las celdas
    python plot_reposo.py --celda 23 44   -> solo esas celdas

El reposo del scheduler dura >= 5 min Y hasta T_celda <= 22 °C (AV_T[2]). Si la celda se calienta
(degradacion subita), el reposo se alarga. Para cada ciclo se toma el ULTIMO valor del tiempo de
paso (Step_Time) dentro del step de reposo = duracion total de ese reposo.

Solo LEE el canal (no modifica ciclos.py ni data_loader.py). Se muestran los mismos ciclos que
en el resto de graficas (los del resumen recortado).
HIPOTESIS: steps 6 y 8 iguales en los 4 schedulers (solo comparado el de C23/C24).
"""
import argparse
import re

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import config as cfg
from data_loader import buscar_celdas, cargar_celda

COLOR_V = {3.8: "#2ca02c", 3.9: "#1f77b4", 4.0: "#ff7f0e", 4.1: "#d62728"}
STEP_REPOSO = {"carga": 6, "desc": 8}      # step de reposo tras la carga / tras la descarga
MIN_REPOSO_S = 300                          # minimo del scheduler (5 min)


def _col_tiempo_paso(canal):
    """Columna del tiempo de paso (se reinicia a 0 en cada step). No la he visto en los archivos:
    se busca por nombre y, si no esta, se para con un mensaje claro en vez de suponer otra."""
    for c in canal.columns:
        if re.match(r"^step_time", str(c), re.I):
            return c
    raise KeyError(f"No hay columna de tiempo de paso (Step_Time...). Columnas del canal: {list(canal.columns)}")


def tiempo_reposo(canal, indice):
    """DataFrame (indice = ciclos de `indice`) con reposo_carga_s y reposo_desc_s: maximo del
    tiempo de paso en las filas del step de reposo de cada ciclo."""
    col = _col_tiempo_paso(canal)
    out = {}
    for nombre, step in STEP_REPOSO.items():
        sub = canal.loc[canal["Step_Index"] == step]
        out[f"reposo_{nombre}_s"] = sub.groupby("Cycle_Index")[col].max()
    return pd.DataFrame(out).reindex(indice)


def figura_reposo(celdas):
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.08,
                        subplot_titles=("Tiempo de reposo tras la carga (step 6)",
                                        "Tiempo de reposo tras la descarga (step 8)"))
    for d in celdas:
        rp, v, n = d["reposo"], d["voltaje"], d["num"]
        for fila, col in ((1, "reposo_carga_s"), (2, "reposo_desc_s")):
            fig.add_trace(go.Scatter(x=rp.index, y=rp[col] / 60, name=f"C{n} ({v} V)", legendgroup=f"C{n}",
                                     mode="lines+markers", marker=dict(size=4),
                                     line=dict(color=COLOR_V.get(v, "grey")), showlegend=(fila == 1)),
                          row=fila, col=1)
    for fila in (1, 2):
        fig.add_hline(y=MIN_REPOSO_S / 60, line_dash="dot", line_color="grey", row=fila, col=1)
        fig.update_yaxes(title_text="Tiempo de reposo (min)", row=fila, col=1)
    fig.update_xaxes(title_text="Ciclo", row=2, col=1)
    fig.update_layout(title="Tiempo de reposo por ciclo (maximo del step) - ciclado continuo "
                            "(punteada: minimo del scheduler, 5 min)",
                      height=900, template="plotly_white", hovermode="closest")
    return fig


def imprimir_resumen(celdas):
    print("\nTiempo de reposo (min): mediana de los 5 primeros ciclos | maximo (ciclo) | ciclos sin dato")
    for d in celdas:
        rp = d["reposo"]
        txt = []
        for col in ("reposo_carga_s", "reposo_desc_s"):
            s = rp[col]
            txt.append(f"{col[7:-2]}: {s.iloc[:5].median() / 60:.1f} | {s.max() / 60:.1f} ({s.idxmax()}) | {int(s.isna().sum())}")
        print(f"   C{d['num']} ({d['voltaje']} V)  " + "   ".join(txt))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--celda", type=int, nargs="*")
    a = ap.parse_args()
    nums = a.celda or sorted(buscar_celdas())
    celdas = []
    for n in nums:
        d = cargar_celda(n, verbose=False)
        d["reposo"] = tiempo_reposo(d["canal"], d["resumen"].index)
        celdas.append(d)
    imprimir_resumen(celdas)
    ruta = cfg.FIGURAS / cfg.FIG_COMPARATIVAS / "comparativa_reposo.html"
    figura_reposo(celdas).write_html(ruta, include_plotlyjs=True)
    print("guardada", ruta)
