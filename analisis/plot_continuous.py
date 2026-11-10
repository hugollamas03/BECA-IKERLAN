"""Graficas de degradacion del ciclado continuo (HTML interactivo en figuras/).

    python plot_continuous.py                 -> una figura por celda + comparativa
    python plot_continuous.py --celda 23 44   -> solo esas celdas

Todos los valores salen de la hoja de canal (ciclos.py). Se muestran los ciclos hasta el
ultimo que tiene fila en el resumen de Arbin; el ciclo en el que se para el ensayo se omite.
"""
import argparse

import plotly.graph_objects as go
from plotly.subplots import make_subplots

import config as cfg
from ciclos import fec
from data_loader import buscar_celdas, cargar_celda

COLOR_V = {3.8: "#2ca02c", 3.9: "#1f77b4", 4.0: "#ff7f0e", 4.1: "#d62728"}


# ----------------------------------------------------------------------------
# Figura individual
# ----------------------------------------------------------------------------
def _serie(fig, r, col, nombre, color, fila):
    fig.add_trace(go.Scatter(x=r.index, y=r[col], name=nombre, mode="lines+markers",
                             marker=dict(size=4), line=dict(color=color), legendgroup=nombre),
                  row=fila, col=1)


def figura_celda(d):
    r, num, v = d["resumen"], d["num"], d["voltaje"]
    ref = "T_celda - T_amb" if cfg.DELTA_T_REFERENCIA == "ambiente" else "T_celda max - T_celda al inicio de la fase"
    fig = make_subplots(
        rows=7, cols=1, shared_xaxes=True, vertical_spacing=0.025,
        row_heights=[0.17, 0.12, 0.15, 0.12, 0.15, 0.145, 0.145],
        subplot_titles=("Capacidad de descarga", "Eficiencia coulombica (Qdesc / Qcarga)",
                        "Energia de carga y descarga", "Eficiencia energetica (Edesc / Ecarga)",
                        "Temperatura maxima por ciclo",
                        f"ΔT en carga ({ref})", f"ΔT en descarga ({ref})"))
    _serie(fig, r, "Q_desc_Ah", "Q descarga", "black", 1)
    _serie(fig, r, "CE_%", "CE", "purple", 2)
    _serie(fig, r, "E_carga_Wh", "E carga", "#d62728", 3)
    _serie(fig, r, "E_desc_Wh", "E descarga", "#1f77b4", 3)
    _serie(fig, r, "EE_%", "EE", "teal", 4)
    _serie(fig, r, "T_amb_max", "T_amb max", "#1f77b4", 5)
    _serie(fig, r, "T_celda_max", "T_celda max", "#d62728", 5)
    _serie(fig, r, "dT_carga", "ΔT carga", "#d62728", 6)
    _serie(fig, r, "dT_desc", "ΔT descarga", "#1f77b4", 7)
    for fila, t in enumerate(("Ah", "%", "Wh", "%", "°C", "°C", "°C"), start=1):
        fig.update_yaxes(title_text=t, row=fila, col=1)
    fig.update_xaxes(title_text="Ciclo", row=7, col=1)
    fig.update_layout(title=f"C{num} - {v} V - ciclado continuo", height=1700, hovermode="x unified",
                      template="plotly_white")
    return fig


# ----------------------------------------------------------------------------
# Figura comparativa (todas las celdas)
# ----------------------------------------------------------------------------
def figura_comparativa(datos):
    fig = make_subplots(rows=2, cols=1, shared_xaxes=False, vertical_spacing=0.10,
                        subplot_titles=("Capacidad de descarga vs ciclo",
                                        "Capacidad de descarga vs ciclos equivalentes completos (FEC)"))
    print(f"\nC_nom usada para el FEC (capacidad nominal del fabricante): {cfg.CAP_NOMINAL_AH} Ah")
    for d in datos:
        r, v, n = d["resumen"], d["voltaje"], d["num"]
        c_nom = cfg.CAP_NOMINAL_AH
        kw = dict(name=f"C{n} ({v} V)", legendgroup=f"C{n}", mode="lines", line=dict(color=COLOR_V.get(v, "grey")))
        fig.add_trace(go.Scatter(x=r.index, y=r["Q_desc_Ah"], **kw), row=1, col=1)
        kw["showlegend"] = False
        fig.add_trace(go.Scatter(x=fec(r, c_nom), y=r["Q_desc_Ah"], **kw), row=2, col=1)
    fig.update_xaxes(title_text="Ciclo", row=1, col=1)
    fig.update_xaxes(title_text="FEC", row=2, col=1)
    fig.update_yaxes(title_text="Ah", row=1, col=1)
    fig.update_yaxes(title_text="Ah", row=2, col=1)
    fig.update_layout(title="Ciclado continuo - todas las celdas", height=900, template="plotly_white",
                      hovermode="closest")
    return fig

# ----------------------------------------------------------------------------
# Figura comparativa temperatura (todas las celdas)
# ----------------------------------------------------------------------------

def figura_dT_carga(datos):
    """ΔT en carga de todas las celdas en un solo grafico."""
    ref = "T_celda - T_amb" if cfg.DELTA_T_REFERENCIA == "ambiente" else "T_celda max - T_celda al inicio de la fase"
    fig = go.Figure()
    for d in datos:
        r, v, n = d["resumen"], d["voltaje"], d["num"]
        fig.add_trace(go.Scatter(x=r.index, y=r["dT_carga"], name=f"C{n} ({v} V)", mode="lines",
                                 line=dict(color=COLOR_V.get(v, "grey"))))
    fig.update_layout(title=f"ΔT en carga ({ref}) - ciclado continuo", xaxis_title="Ciclo", yaxis_title="ΔT (°C)",
                      height=600, template="plotly_white", hovermode="closest")
    return fig

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--celda", type=int, nargs="*")
    a = ap.parse_args()
    nums = a.celda or sorted(buscar_celdas())
    datos = [cargar_celda(n) for n in nums]
    for d in datos:
        ruta = cfg.FIGURAS / cfg.FIG_DEGRADACION / f"C{d['num']}_degradacion.html"
        figura_celda(d).write_html(ruta, include_plotlyjs=True)
        print("guardada", ruta)
    if len(datos) > 1:
        ruta = cfg.FIGURAS / cfg.FIG_COMPARATIVAS / "comparativa_capacidad.html"
        figura_comparativa(datos).write_html(ruta, include_plotlyjs=True)
        print("guardada", ruta)
        ruta = cfg.FIGURAS / cfg.FIG_COMPARATIVAS / "comparativa_dT_carga.html"
        figura_dT_carga(datos).write_html(ruta, include_plotlyjs=True)
        print("guardada", ruta)
