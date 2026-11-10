"""Graficas de energia y ratio E/Q del ciclado continuo (HTML interactivo en figuras/).

    python plot_energia.py                 -> las 3 figuras con todas las celdas
    python plot_energia.py --celda 23 44   -> solo esas celdas

Figuras:
  comparativa_retencion.html  retencion de capacidad vs ciclo / FEC / energia acumulada,
                              con 100 % = 1,5 Ah (izq.) y 100 % = media de los 5 primeros ciclos (dcha.)
  comparativa_energia.html    energia de descarga por ciclo vs ciclo y vs FEC, y energia total por celda
  comparativa_EQ.html         E/Q normalizado (descarga continua, carga discontinua) vs ciclo y vs
                              perdida de capacidad (con las dos referencias)

Todos los datos que hay (sin cortar al 80 %); la linea punteada al 80 % es solo una referencia.
Todo sale del resumen por ciclo reconstruido desde el canal (ciclos.py).
"""
import argparse

import plotly.graph_objects as go
from plotly.subplots import make_subplots

import config as cfg
from ciclos import agregar_energia, fec
from data_loader import buscar_celdas, cargar_celda

COLOR_V = {3.8: "#2ca02c", 3.9: "#1f77b4", 4.0: "#ff7f0e", 4.1: "#d62728"}
CAP_NOM = getattr(cfg, "CAP_NOMINAL_AH", 1.5)
N_REF = getattr(cfg, "N_CICLOS_REF", 5)
# Leyenda de las graficas de E/Q: doble clic en "Descarga"/"Carga" aisla las lineas continuas/discontinuas
JS_LEYENDA = """
var gd = document.getElementById('{plot_id}');
function visible(t) { return t.visible !== false && t.visible !== 'legendonly'; }
function fijar(f) {
  Plotly.restyle(gd, {visible: gd.data.map(function (t) { return f(t) ? true : 'legendonly'; })});
}
gd.on('plotly_legendclick', function (ev) {
  var est = (gd.data[ev.curveNumber].meta || {}).leyenda;
  if (!est) return true;
  var hay = gd.data.some(function (t) { return (t.meta || {}).estilo === est && visible(t); });
  fijar(function (t) { return (t.meta || {}).estilo === est ? !hay : visible(t); });
  return false;
});
gd.on('plotly_legenddoubleclick', function (ev) {
  var est = (gd.data[ev.curveNumber].meta || {}).leyenda;
  if (!est) return true;
  var aislado = gd.data.every(function (t) { var e = (t.meta || {}).estilo; return !e || ((e === est) === visible(t)); });
  fijar(function (t) { var e = (t.meta || {}).estilo; return !e || aislado || e === est; });
  return false;
});
"""


def _color(d):
    return COLOR_V.get(d["voltaje"], "grey")


def _nombre(d):
    return f"C{d['num']} ({d['voltaje']} V)"


# ----------------------------------------------------------------------------
# 1) Retencion de capacidad
# ----------------------------------------------------------------------------
def fig_retencion(celdas):
    titulos = {"nominal": f"100 % = {CAP_NOM} Ah (nominal)", "celda": f"100 % = media de los {N_REF} primeros ciclos de cada celda"}
    filas = (("Ciclo", "ciclo"), (f"FEC (C_nom = {CAP_NOM} Ah)", "fec"), ("Energia de descarga acumulada (kWh)", "energia"))
    fig = make_subplots(rows=3, cols=2, vertical_spacing=0.09, horizontal_spacing=0.07,
                        subplot_titles=[f"Retencion vs {f[0].split(' (')[0].lower()} - {titulos[c]}"
                                        for f in filas for c in ("nominal", "celda")])
    for d in celdas:
        e = d["e"]
        for col, clave in ((1, "nominal"), (2, "celda")):
            y = e[f"ret_{clave}_%"]
            xs = {"ciclo": e.index, "fec": fec(e, CAP_NOM), "energia": e["E_desc_acum_kWh"]}
            for fila, (_, k) in enumerate(filas, start=1):
                fig.add_trace(go.Scatter(x=xs[k], y=y, name=_nombre(d), legendgroup=f"C{d['num']}", mode="lines",
                                         line=dict(color=_color(d)), showlegend=(fila == 1 and col == 1)),
                              row=fila, col=col)
    for fila, (xt, _) in enumerate(filas, start=1):
        for col in (1, 2):
            fig.add_hline(y=80, line_dash="dot", line_color="grey", row=fila, col=col)
            fig.update_xaxes(title_text=xt, row=fila, col=col)
            fig.update_yaxes(title_text="Retencion de capacidad (%)", row=fila, col=col)
    fig.update_layout(title="Retencion de capacidad de descarga - ciclado continuo", height=1250,
                      template="plotly_white", hovermode="closest")
    return fig


# ----------------------------------------------------------------------------
# 2) Energia de descarga
# ----------------------------------------------------------------------------
def energia_hasta_umbral(e, frac=0.5):
    """(ciclo, kWh acumulados hasta ese ciclo incluido) del primer ciclo en que la energia de descarga por ciclo
    cae a `frac` de su primer valor. (None, None) si la celda nunca llega."""
    umbral = frac * e["E_desc_Wh"].iloc[0]          # alternativa: e["E_desc_Wh"].iloc[:N_REF].mean()
    bajo = e.index[(e["E_desc_Wh"] <= umbral).values]
    if len(bajo) == 0:
        return None, None
    return bajo[0], e.loc[bajo[0], "E_desc_acum_kWh"]


def fig_energia(celdas):
    fig = make_subplots(rows=3, cols=1, vertical_spacing=0.10,
                        subplot_titles=("Energia de descarga por ciclo vs ciclo", "Energia de descarga por ciclo vs FEC",
                                        "Energia de descarga acumulada hasta el final del ensayo (raya punteada: hasta el 50 % de la energia por ciclo inicial)"))
    for d in celdas:
        e = d["e"]
        kw = dict(name=_nombre(d), legendgroup=f"C{d['num']}", mode="lines", line=dict(color=_color(d)))
        fig.add_trace(go.Scatter(x=e.index, y=e["E_desc_Wh"], **kw), row=1, col=1)
        kw["showlegend"] = False
        fig.add_trace(go.Scatter(x=fec(e, CAP_NOM), y=e["E_desc_Wh"], **kw), row=2, col=1)
    orden = sorted(celdas, key=lambda d: (d["voltaje"], d["num"]))      # barras agrupadas por tension
    total = [d["e"]["E_desc_acum_kWh"].iloc[-1] for d in orden]
    fig.add_trace(go.Bar(x=[_nombre(d) for d in orden], y=total, marker_color=[_color(d) for d in orden],
                         text=[f"{t:.3f} kWh<br>{len(d['e'])} ciclos" for t, d in zip(total, orden)],
                         textposition="outside", showlegend=False), row=3, col=1)
    x50, y50, t50 = [], [], []                      # raya punteada + valor: energia hasta el 50 % de la energia por ciclo inicial
    print("\nEnergia de descarga hasta el 50 % de la energia por ciclo inicial:")
    for i, d in enumerate(orden):
        c50, e50 = energia_hasta_umbral(d["e"])
        if c50 is None:
            print(f"   {_nombre(d)}: no llega al 50 %")
            continue
        fig.add_shape(type="line", x0=i - 0.4, x1=i + 0.4, y0=e50, y1=e50,
                      line=dict(color="black", dash="dot", width=2), row=3, col=1)
        x50.append(_nombre(d)); y50.append(e50); t50.append(f"50 %: {e50:.3f} kWh<br>ciclo {int(c50)}")
        print(f"   {_nombre(d)}: E ciclo 1 = {d['e']['E_desc_Wh'].iloc[0]:.3f} Wh -> 50 % en el ciclo {int(c50)}; "
              f"{e50:.3f} kWh ({100 * e50 / d['e']['E_desc_acum_kWh'].iloc[-1]:.0f} % del total)")
    fig.add_trace(go.Scatter(x=x50, y=[v - 0.03 * max(total) for v in y50], mode="text", text=t50, textposition="bottom center",
                             textfont=dict(color="white", size=11), showlegend=False, hoverinfo="skip"), row=3, col=1)
    fig.update_yaxes(title_text="Wh por ciclo", row=1, col=1)
    fig.update_yaxes(title_text="Wh por ciclo", row=2, col=1)
    fig.update_yaxes(title_text="kWh", range=[0, 1.25 * max(total)], row=3, col=1)
    fig.update_xaxes(title_text="Ciclo", row=1, col=1)
    fig.update_xaxes(title_text=f"FEC (C_nom = {CAP_NOM} Ah)", row=2, col=1)
    fig.update_layout(title="Energia de descarga - ciclado continuo", height=1250, template="plotly_white",
                      hovermode="closest")
    return fig


# ----------------------------------------------------------------------------
# 3) Ratio E/Q (equivalente a la Fig. 4D del paper: ciclado a C/2)
# ----------------------------------------------------------------------------
def fig_EQ(celdas):
    fig = make_subplots(rows=3, cols=1, vertical_spacing=0.08,
                        subplot_titles=("E/Q vs ciclo",
                                        f"E/Q vs perdida de capacidad (100 % = {CAP_NOM} Ah)",
                                        f"E/Q vs perdida de capacidad (100 % = media de los {N_REF} primeros ciclos)"))
    for d in celdas:
        e = d["e"]
        for fila, xcol in ((1, None), (2, "perdida_nominal_%"), (3, "perdida_celda_%")):
            x = e.index if xcol is None else e[xcol]
            kw = dict(x=x, mode="lines", legendgroup=f"C{d['num']}", line=dict(color=_color(d)), meta={"estilo": "desc"})
            fig.add_trace(go.Scatter(y=e["EQ_desc"], name=_nombre(d), showlegend=(fila == 1), **kw), row=fila, col=1)
            kw["line"] = dict(color=_color(d), dash="dash")
            kw["meta"] = {"estilo": "carga"}
            fig.add_trace(go.Scatter(y=e["EQ_carga"], name=_nombre(d) + " carga", showlegend=False, **kw),
                          row=fila, col=1)
    for nombre, dash, est in (("Descarga (continua)", "solid", "desc"), ("Carga (discontinua)", "dash", "carga")):
        fig.add_trace(go.Scatter(x=[None], y=[None], mode="lines", name=nombre, meta={"leyenda": est},
                                 line=dict(color="black", dash=dash)), row=1, col=1)
    for fila in (1, 2, 3):
        fig.add_hline(y=1, line_dash="dot", line_color="grey", row=fila, col=1)
        fig.update_yaxes(title_text="E/Q (normalizado)", row=fila, col=1)
    fig.update_xaxes(title_text="Ciclo", row=1, col=1)
    fig.update_xaxes(title_text="Perdida de capacidad (%)", row=2, col=1)
    fig.update_xaxes(title_text="Perdida de capacidad (%)", row=3, col=1)
    fig.update_layout(title=f"Ratio E/Q (normalizado a la media de los {N_REF} primeros ciclos) - ciclado continuo a C/2",
                      height=1300, template="plotly_white", hovermode="closest")
    return fig


def imprimir_resumen(celdas):
    print(f"\nReferencias y comprobaciones por celda (ref. = media de los {N_REF} primeros ciclos):")
    for d in celdas:
        e = d["e"]
        print(f"   {_nombre(d)}: Q_ref = {e.attrs['ref_Q']['celda']:.4f} Ah | "
              f"V med. ciclo 1: desc {e['V_med_desc'].iloc[0]:.3f} V, carga {e['V_med_carga'].iloc[0]:.3f} V | "
              f"V0 (ref.): desc {e.attrs['V0_desc']:.3f} V, carga {e.attrs['V0_carga']:.3f} V | "
              f"E/Q medio de los {N_REF} primeros: desc {e['EQ_desc'].iloc[:N_REF].mean():.4f}, "
              f"carga {e['EQ_carga'].iloc[:N_REF].mean():.4f} | "
              f"E desc total {e['E_desc_acum_kWh'].iloc[-1]:.3f} kWh en {len(e)} ciclos")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--celda", type=int, nargs="*")
    a = ap.parse_args()
    nums = a.celda or sorted(buscar_celdas())
    celdas = []
    for n in nums:
        d = cargar_celda(n, verbose=False)
        d["e"] = agregar_energia(d["resumen"])
        celdas.append(d)
    imprimir_resumen(celdas)
    for nombre, fig in (("comparativa_retencion", fig_retencion(celdas)),
                        ("comparativa_energia", fig_energia(celdas)),
                        ("comparativa_EQ", fig_EQ(celdas))):
        ruta = cfg.FIGURAS / cfg.FIG_COMPARATIVAS / f"{nombre}.html"
        fig.write_html(ruta, include_plotlyjs=True, post_script=JS_LEYENDA if nombre == "comparativa_EQ" else None)
        print("guardada", ruta)
