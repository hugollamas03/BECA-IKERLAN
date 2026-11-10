"""Resumen por ciclo RECONSTRUIDO desde la hoja de canal (registro primario).

Las hojas StatisticsByCycle de Arbin se usan solo para comparar: tienen ciclos
ausentes, cerrados antes de tiempo (p. ej. C44 ciclo 35) y no incluyen el ultimo
ciclo de las celdas que murieron (C68, C69). Aqui todo sale del canal.
"""
import numpy as np
import pandas as pd

import config as cfg


# ----------------------------------------------------------------------------
# Resumen por ciclo desde el canal
# ----------------------------------------------------------------------------
def construir_resumen(canal):
    c = canal
    cic = c["Cycle_Index"]
    g = c.groupby("Cycle_Index", sort=True)

    # Las capacidades/energias del equipo son acumuladas DENTRO de cada ciclo,
    # asi que el valor del ciclo es el maximo alcanzado en el.
    r = pd.DataFrame({
        "Q_carga_Ah": g["Charge_Capacity(Ah)"].max(),
        "Q_desc_Ah": g["Discharge_Capacity(Ah)"].max(),
        "E_carga_Wh": g["Charge_Energy(Wh)"].max(),
        "E_desc_Wh": g["Discharge_Energy(Wh)"].max(),
        "T_amb_max": g["T_amb"].max(),
        "T_celda_max": g["T_celda"].max(),
        "fecha_fin": g["Date_Time"].max(),
    })
    r["CE_%"] = 100 * r["Q_desc_Ah"] / r["Q_carga_Ah"].where(r["Q_carga_Ah"] > 0)
    r["EE_%"] = 100 * r["E_desc_Wh"] / r["E_carga_Wh"].where(r["E_carga_Wh"] > 0)

    # ΔT por fase, fase definida por el signo de la corriente (no depende del numero de step)
    I = c["Current(A)"]
    for nombre, mask in (("carga", I > cfg.UMBRAL_CORRIENTE_A), ("desc", I < -cfg.UMBRAL_CORRIENTE_A)):
        sub = c[mask]
        gs = sub.groupby("Cycle_Index")
        r[f"dT_{nombre}_amb"] = (sub["T_celda"] - sub["T_amb"]).groupby(sub["Cycle_Index"]).max()
        r[f"dT_{nombre}_ini"] = gs["T_celda"].max() - gs["T_celda"].first()
    suf = {"ambiente": "amb", "inicio_fase": "ini"}[cfg.DELTA_T_REFERENCIA]
    r["dT_carga"] = r[f"dT_carga_{suf}"]
    r["dT_desc"] = r[f"dT_desc_{suf}"]

    # Incidencias dentro del ciclo
    retro = c["Test_Time(s)"].diff() < -cfg.SALTO_TIEMPO_S
    r["retroceso_tiempo"] = retro.groupby(cic).any()
    pausa = c["Date_Time"].diff() > pd.Timedelta(hours=cfg.PAUSA_FECHA_H)
    r["pausa_larga"] = pausa.groupby(cic).any()

    # Ciclo completo: tiene un ciclo posterior en el canal; el ultimo, solo si
    # termina en el step de cierre habitual (el que cierra el resto de ciclos).
    ultimo_step = g["Step_Index"].last()
    r["completo"] = True
    if len(r) > 1:
        step_cierre = ultimo_step.iloc[:-1].mode().iloc[0]
        r.loc[r.index[-1], "completo"] = bool(ultimo_step.iloc[-1] == step_cierre)
    return r


# ----------------------------------------------------------------------------
# Comparacion con la hoja de resumen de Arbin + informe de anomalias
# ----------------------------------------------------------------------------
def informe_anomalias(r, arbin):
    a = arbin.drop_duplicates("Cycle_Index", keep="last").set_index("Cycle_Index")
    comun = r.index.intersection(a.index)
    step_habitual = a["Step_Index"].mode().iloc[0]

    ultimo_arbin = a.index.max()
    sin_fila = r.index.difference(a.index)
    motivos = []                                   # (ciclo, motivo)
    motivos += [(k, "sin fila en resumen Arbin") for k in sin_fila[sin_fila <= ultimo_arbin]]
    motivos += [(k, "omitido de las graficas (posterior al ultimo ciclo con resumen de Arbin)")
                for k in sin_fila[sin_fila > ultimo_arbin]]
    motivos += [(k, "ciclo solo en resumen Arbin") for k in a.index.difference(r.index)]
    cerrado = a.loc[comun, "Step_Index"] != step_habitual
    motivos += [(k, "resumen Arbin cerrado antes del step de cierre") for k in comun[cerrado.values]]
    d_desc = (r.loc[comun, "Q_desc_Ah"] - a.loc[comun, "Discharge_Capacity(Ah)"]).abs()
    d_carga = (r.loc[comun, "Q_carga_Ah"] - a.loc[comun, "Charge_Capacity(Ah)"]).abs()
    dif = (d_desc > cfg.TOL_CAPACIDAD_AH) | (d_carga > cfg.TOL_CAPACIDAD_AH)
    motivos += [(k, "capacidad del canal distinta de la de Arbin") for k in comun[dif.values]]
    motivos += [(k, "ciclo incompleto (ultimo, sin step de cierre)") for k in r.index[~r["completo"]]]
    motivos += [(k, "retroceso de Test_Time") for k in r.index[r["retroceso_tiempo"]]]
    motivos += [(k, "pausa larga en Date_Time") for k in r.index[r["pausa_larga"]]]

    df = pd.DataFrame(motivos, columns=["Cycle_Index", "motivo"]).sort_values(["Cycle_Index", "motivo"])
    df["Cycle_Index"] = df["Cycle_Index"].astype(int)
    df["Q_desc_canal_Ah"] = r["Q_desc_Ah"].reindex(df["Cycle_Index"]).values
    df["Q_desc_Arbin_Ah"] = a["Discharge_Capacity(Ah)"].reindex(df["Cycle_Index"]).values
    df["Q_carga_canal_Ah"] = r["Q_carga_Ah"].reindex(df["Cycle_Index"]).values
    df["Q_carga_Arbin_Ah"] = a["Charge_Capacity(Ah)"].reindex(df["Cycle_Index"]).values
    df["step_cierre_Arbin"] = a["Step_Index"].reindex(df["Cycle_Index"]).values
    return df.reset_index(drop=True)


MOTIVOS_CORREGIDOS = ("sin fila en resumen Arbin", "resumen Arbin cerrado antes", "capacidad del canal distinta")


def ciclos_corregidos(anom):
    """Ciclos cuyo dato de Arbin faltaba/era erroneo y que ahora salen del canal."""
    m = anom["motivo"].str.startswith(MOTIVOS_CORREGIDOS)
    return [int(k) for k in sorted(anom.loc[m, "Cycle_Index"].unique())]


def recortar_resumen(r, arbin):
    """Como en la primera version: solo se muestran los ciclos hasta el ultimo que tiene fila en el
    resumen de Arbin. Los posteriores (el ciclo en el que se para el ensayo) se omiten.
    Dentro de ese rango TODOS los valores salen del canal."""
    ultimo = arbin["Cycle_Index"].max()
    omitidos = [int(k) for k in r.index[r.index > ultimo]]
    return r.loc[r.index <= ultimo].copy(), omitidos


# ----------------------------------------------------------------------------
# FEC (full equivalent cycles): FEC_n = (1 / C_nom) * sum_{i<=n} Q_desc,i
# C_nom de cada celda = media de la capacidad de descarga de sus primeros N ciclos
# ----------------------------------------------------------------------------
def capacidad_nominal(r, n=None):
    n = n or cfg.N_CICLOS_REF
    return float(r.loc[r.index <= n, "Q_desc_Ah"].mean())


def fec(r, c_nom):
    return r["Q_desc_Ah"].fillna(0).cumsum() / c_nom

# ----------------------------------------------------------------------------
# Energia: retencion de capacidad, energia acumulada y ratio E/Q
# E/Q = (E_i/Q_i) / (E_0/Q_0) = tension media normalizada a su valor inicial
# (Dubarry et al., Joule 2026, Ecs. 1-4). Solo AÑADE columnas: no modifica nada de lo anterior.
# ----------------------------------------------------------------------------
def referencias_capacidad(r):
    """Capacidad que vale 100 % en las dos versiones: nominal del fabricante y media de los
    primeros N ciclos de la propia celda."""
    n = getattr(cfg, "N_CICLOS_REF", 5)
    return {"nominal": getattr(cfg, "CAP_NOMINAL_AH", 1.5),
            "celda": float(r.loc[r.index <= n, "Q_desc_Ah"].mean())}
 
 
def agregar_energia(r):
    """Copia del resumen por ciclo con columnas nuevas: energia acumulada, tension media,
    retencion y perdida de capacidad (dos referencias) y E/Q normalizado (carga y descarga)."""
    out = r.copy()
    n = getattr(cfg, "N_CICLOS_REF", 5)
    ini = out.index <= n
    refs = referencias_capacidad(out)
 
    out["E_desc_acum_kWh"] = out["E_desc_Wh"].fillna(0).cumsum() / 1000
    out["V_med_desc"] = out["E_desc_Wh"] / out["Q_desc_Ah"].where(out["Q_desc_Ah"] > 0)
    out["V_med_carga"] = out["E_carga_Wh"] / out["Q_carga_Ah"].where(out["Q_carga_Ah"] > 0)
 
    for clave, ref in refs.items():
        out[f"ret_{clave}_%"] = 100 * out["Q_desc_Ah"] / ref
        out[f"perdida_{clave}_%"] = 100 - out[f"ret_{clave}_%"]       # = 100 * (1 - Q / Q_ref)
 
    # Tension media de referencia = media de E / media de Q en los primeros N ciclos
    v0_desc = out.loc[ini, "E_desc_Wh"].mean() / out.loc[ini, "Q_desc_Ah"].mean()
    v0_carga = out.loc[ini, "E_carga_Wh"].mean() / out.loc[ini, "Q_carga_Ah"].mean()
    out["EQ_desc"] = out["V_med_desc"] / v0_desc
    out["EQ_carga"] = out["V_med_carga"] / v0_carga
    out.attrs.update({"ref_Q": refs, "V0_desc": float(v0_desc), "V0_carga": float(v0_carga)})
    return out