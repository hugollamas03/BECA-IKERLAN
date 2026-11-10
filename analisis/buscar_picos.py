"""Busca el ciclo en el que la eficiencia coulombica (CE) cae un X % respecto a su valor estable.

    python buscar_picos.py                       -> umbrales 3, 4 y 5 % en las 8 celdas
    python buscar_picos.py --umbrales 2 3 6      -> otros umbrales (se aplican a todas las celdas)
    python buscar_picos.py --auto                -> anade ademas un umbral automatico por celda
    python buscar_picos.py --celda 44 45         -> solo esas celdas

Metodo (todo desde el resumen por ciclo reconstruido del canal, ciclos.py):
  1. CE base = mediana de la CE de los primeros N_BASE ciclos (la etapa estable).
  2. Para cada umbral X (en puntos porcentuales de CE): primer ciclo a partir del cual la CE queda por debajo de
     (base - X) durante PERSISTENCIA ciclos seguidos. Asi un ciclo suelto raro no cuenta como caida.
  3. Ciclo de inicio de las graficas = ciclo de la caida - 20 y - 30 (lo que quieres "tirar para atras").
  4. Umbral automatico (--auto): FRACCION_AUTO de la profundidad total de la caida de esa celda (heuristica mia,
     a validar a ojo con la grafica).

Salidas: informes\\picos_CE.csv y figuras\\picos_CE.html (CE de cada celda con un rombo en cada ciclo detectado).
Desde otro script:  from buscar_picos import ciclo_caida, ce_base
"""
import argparse
import math

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import config as cfg
from data_loader import buscar_celdas, cargar_celda

UMBRALES_DEFECTO = (3, 4, 5)       # puntos porcentuales de CE por debajo de la base
UMBRALES_POR_CELDA = {}            # umbrales propios de una celda, p. ej. {44: (4, 5, 6)}
N_BASE = 30                        # ciclos iniciales que definen la CE estable
PERSISTENCIA = 2                   # ciclos seguidos por debajo del umbral para dar la caida por buena
ATRAS = (20, 30)                   # ciclos a retroceder desde el punto detectado
FRACCION_AUTO = 0.10               # umbral automatico = 10 % de la profundidad de la caida...
LIMITES_AUTO = (2.0, 10.0)         # ...limitado a este rango (pp)
COLORES = ["#ff7f0e", "#d62728", "#2ca02c", "#9467bd", "#8c564b", "#17becf", "#e377c2"]


# ----------------------------------------------------------------------------
# Deteccion
# ----------------------------------------------------------------------------
def ce_base(ce, n=N_BASE):
    """CE estable de la celda: mediana de los primeros n ciclos."""
    return float(ce.loc[ce.index <= n].median())


def ciclo_caida(ce, umbral, base=None, persistencia=PERSISTENCIA):
    """Primer ciclo en el que empieza una racha de `persistencia` ciclos con CE < base - umbral.
    None si no ocurre. `ce` es una Serie indexada por ciclo."""
    base = ce_base(ce) if base is None else base
    debajo = (ce < base - umbral).astype(int)                   # NaN < x es False
    racha = debajo.rolling(persistencia).sum() == persistencia  # True en el ultimo ciclo de una racha completa
    pos = np.flatnonzero(racha.values)
    return None if len(pos) == 0 else int(ce.index[pos[0] - persistencia + 1])


def umbral_auto(ce, base=None):
    """Umbral adaptado a la celda: FRACCION_AUTO de la profundidad de su caida (base - minimo de la CE suavizada)."""
    base = ce_base(ce) if base is None else base
    profundidad = base - float(ce.rolling(5, center=True, min_periods=1).median().min())
    return float(np.clip(FRACCION_AUTO * profundidad, *LIMITES_AUTO))


# ----------------------------------------------------------------------------
# Tabla
# ----------------------------------------------------------------------------
def construir_tabla(celdas, umbrales=None, auto=False):
    filas = []
    for d in celdas:
        ce = d["resumen"]["CE_%"]
        base = ce_base(ce)
        criterios = [(f"{u:g} %", float(u)) for u in (umbrales or UMBRALES_POR_CELDA.get(d["num"], UMBRALES_DEFECTO))]
        if auto:
            criterios.append(("auto", umbral_auto(ce, base)))
        for nombre, u in criterios:
            c = ciclo_caida(ce, u, base)
            fila = {"celda": d["num"], "voltaje": d["voltaje"], "criterio": nombre, "umbral_pp": round(u, 2),
                    "CE_base_%": round(base, 2), "ciclo_caida": c,
                    "CE_en_ciclo_%": round(float(ce.loc[c]), 2) if c is not None else None}
            for a in ATRAS:
                fila[f"ciclo_inicio_-{a}"] = max(int(ce.index.min()), c - a) if c is not None else None
            filas.append(fila)
    return pd.DataFrame(filas)


# ----------------------------------------------------------------------------
# Figura de comprobacion
# ----------------------------------------------------------------------------
def fig_picos(celdas, tabla):
    filas = math.ceil(len(celdas) / 2)
    fig = make_subplots(rows=filas, cols=2, vertical_spacing=0.08, horizontal_spacing=0.06,
                        subplot_titles=[f"C{d['num']} ({d['voltaje']} V) - CE base {ce_base(d['resumen']['CE_%']):.2f} %"
                                        for d in celdas])
    color, vistos = {}, set()
    for k, d in enumerate(celdas):
        fila, col = k // 2 + 1, k % 2 + 1
        ce = d["resumen"]["CE_%"]
        fig.add_trace(go.Scatter(x=ce.index, y=ce, mode="lines", line=dict(color="black", width=1),
                                 showlegend=False, hoverinfo="x+y"), row=fila, col=col)
        fig.add_hline(y=ce_base(ce), line_dash="dot", line_color="grey", row=fila, col=col)
        for _, t in tabla[tabla["celda"] == d["num"]].iterrows():
            if pd.isna(t["ciclo_caida"]):
                continue
            c = int(t["ciclo_caida"])
            nombre = t["criterio"]
            color.setdefault(nombre, COLORES[len(color) % len(COLORES)])
            fig.add_trace(go.Scatter(x=[c], y=[ce.loc[c]], mode="markers", name=nombre, legendgroup=nombre,
                                     showlegend=nombre not in vistos,
                                     marker=dict(symbol="diamond", size=11, color=color[nombre],
                                                 line=dict(color="black", width=1)),
                                     hovertemplate=f"umbral {t['umbral_pp']:g} pp<br>ciclo {c}<extra></extra>"),
                          row=fila, col=col)
            vistos.add(nombre)
        fig.update_yaxes(title_text="CE (%)", row=fila, col=col)
        fig.update_xaxes(title_text="Ciclo", row=fila, col=col)
    fig.update_layout(title="Eficiencia coulombica y ciclo detectado para cada umbral", template="plotly_white",
                      height=330 * filas + 120, hovermode="closest")
    return fig


# ----------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--celda", type=int, nargs="*")
    ap.add_argument("--umbrales", type=float, nargs="*", help="umbrales en puntos porcentuales (defecto: 3 4 5)")
    ap.add_argument("--auto", action="store_true", help="anade el umbral automatico de cada celda")
    a = ap.parse_args(argv)
    nums = a.celda or sorted(buscar_celdas())
    celdas = [cargar_celda(n, verbose=False) for n in nums]
    tabla = construir_tabla(celdas, a.umbrales, a.auto)

    print(f"\nCaida de la CE respecto a su base (mediana de los {N_BASE} primeros ciclos); "
          f"{PERSISTENCIA} ciclos seguidos por debajo del umbral:\n")
    print(tabla.to_string(index=False))
    ruta_csv = cfg.INFORMES / "picos_CE.csv"
    tabla.to_csv(ruta_csv, sep=";", decimal=",", index=False, encoding="utf-8-sig")
    ruta_html = cfg.FIGURAS / cfg.FIG_COMPARATIVAS / "picos_CE.html"
    fig_picos(celdas, tabla).write_html(ruta_html, include_plotlyjs=True)
    print("\nguardado", ruta_csv)
    print("guardado", ruta_html)
    return tabla


if __name__ == "__main__":
    main()