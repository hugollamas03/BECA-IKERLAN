"""Graficas de degradacion del ciclado continuo (HTML interactivo en figuras/).

    python plot_continuous.py                 -> una figura por celda + comparativa
    python plot_continuous.py --celda 23 44   -> solo esas celdas
"""
import argparse

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from config import FIGURAS
from data_loader import buscar_celdas, cargar_celda

COLOR_V = {3.8: "#2ca02c", 3.9: "#1f77b4", 4.0: "#ff7f0e", 4.1: "#d62728"}


def figura_celda(d):
    c, num, v = d["ciclo"], d["num"], d["voltaje"]
    x = c["Cycle_Index"]
    fig = make_subplots(
        rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.035,
        row_heights=[0.34, 0.2, 0.23, 0.23],
        subplot_titles=("Capacidad de descarga", "Eficiencia coulombica (Qdesc/Qcarga)",
                        "Temperatura maxima por ciclo", "Rango de temperatura dentro del ciclo (max - min)"))
    kw = dict(mode="lines+markers", marker=dict(size=4))
    fig.add_trace(go.Scatter(x=x, y=c["Discharge_Capacity(Ah)"], name="Q descarga", **kw,
                             line=dict(color="black")), row=1, col=1)
    fig.add_trace(go.Scatter(x=x, y=c["CE_%"], name="CE", **kw, line=dict(color="purple")), row=2, col=1)
    for t, col in (("T1", "#1f77b4"), ("T2", "#d62728")):
        fig.add_trace(go.Scatter(x=x, y=c[f"{t}_max"], name=f"{t} max", **kw, line=dict(color=col)), row=3, col=1)
        fig.add_trace(go.Scatter(x=x, y=c[f"{t}_rango"], name=f"{t} rango", **kw, line=dict(color=col),
                                 showlegend=False), row=4, col=1)
    fig.update_yaxes(title_text="Ah", row=1, col=1)
    fig.update_yaxes(title_text="%", row=2, col=1)
    fig.update_yaxes(title_text="C", row=3, col=1)
    fig.update_yaxes(title_text="C", row=4, col=1)
    fig.update_xaxes(title_text="Ciclo", row=4, col=1)
    fig.update_layout(title=f"C{num} - {v} V - ciclado continuo", height=950, hovermode="x unified",
                      template="plotly_white")
    return fig


def figura_comparativa(datos):
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.06,
                        subplot_titles=("Capacidad de descarga (Ah)",
                                        "Capacidad de descarga relativa al ciclo 1 (%)"))
    for d in datos:
        c, v, n = d["ciclo"], d["voltaje"], d["num"]
        q = c["Discharge_Capacity(Ah)"]
        kw = dict(x=c["Cycle_Index"], name=f"C{n} ({v} V)", legendgroup=f"C{n}", mode="lines",
                  line=dict(color=COLOR_V.get(v, "grey")))
        fig.add_trace(go.Scatter(y=q, **kw), row=1, col=1)
        fig.add_trace(go.Scatter(y=100 * q / q.iloc[0], showlegend=False, **kw), row=2, col=1)
    fig.update_xaxes(title_text="Ciclo", row=2, col=1)
    fig.update_layout(title="Ciclado continuo - todas las celdas", height=800, template="plotly_white",
                      hovermode="x")
    return fig


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--celda", type=int, nargs="*")
    a = ap.parse_args()
    nums = a.celda or sorted(buscar_celdas())
    datos = [cargar_celda(n) for n in nums]
    for d in datos:
        ruta = FIGURAS / f"C{d['num']}_degradacion.html"
        figura_celda(d).write_html(ruta, include_plotlyjs=True)
        print("guardada", ruta)
    if len(datos) > 1:
        ruta = FIGURAS / "comparativa_capacidad.html"
        figura_comparativa(datos).write_html(ruta, include_plotlyjs=True)
        print("guardada", ruta)
