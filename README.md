# Análisis del ciclado continuo de celdas Na-ion (Hakadi 18650)

Código de la beca de cátedra Ikerlan: *Diagnóstico no invasivo de electrodepósito de sodio en celdas comerciales de ion-sodio mediante análisis de capacidad incremental (IC) y espectroscopía de impedancia (EIS)*.

De momento se hace el análisis **macro (por ciclo)** del ciclado continuo a C/2 de 8 celdas (cortes de carga 3,8 / 3,9 / 4,0 / 4,1 V). IC y EIS quedan para más adelante.

## Datos

Los Excel de Arbin (equipos v7 y v8) **no se incluyen** en el repositorio. Se espera esta estructura, de solo lectura:

```
DOCUMENTOS/
├── 00 - Raw data/C## - X.X V standard cycling - continuous/04_.../*.xlsx
└── analisis/            <- este repositorio
```

## Instalación

Se debe crear un entorno virtual con el archivo adjunto de requirements.txt
que incluye paquetes utilizados como: pandas numpy matplotlib openpyxl pyarrow plotly python-calamine

Comandos:

```
python -m venv .venv
pip install -r requirements.txt
```

## Scripts

Todo se calcula desde la hoja de canal (registro primario); las hojas de resumen de Arbin solo se usan para comparar.

| Script | Qué hace |
|---|---|
| `config.py` | Rutas y constantes (umbrales, capacidad nominal, referencia de ΔT) |
| `data_loader.py` | Lee los Excel (calamine), normaliza columnas, cachea en Parquet y escribe `informes/C##_anomalias.csv` |
| `ciclos.py` | Resumen por ciclo desde el canal (capacidad, energía, CE, EE, temperaturas, ΔT), FEC, retención y E/Q |
| `plot_continuous.py` | Degradación por celda y comparativas de capacidad y ΔT en carga |
| `plot_energia.py` | Retención de capacidad, energía de descarga y ratio E/Q |
| `plot_reposo.py` | Tiempo de reposo tras carga (step 6) y descarga (step 8) por ciclo |
| `buscar_picos.py` | Ciclo en que cae la CE respecto a su valor estable (umbrales 3, 4 y 5 %) |
| `plot_curvas_carga.py` | Curvas de voltaje y ΔT de la carga (step 5) por ciclo, en torno a la caída de CE |

## Uso

Desde la carpeta `analisis`, con el entorno virtual activo:

```
python data_loader.py          # carga y cachea (--forzar regenera la caché, --celda 23 una sola)
python plot_continuous.py
python plot_energia.py
python plot_reposo.py
python buscar_picos.py
python plot_curvas_carga.py --celda 44 --atras 30 --despues 10
```

Si cambia la lectura o normalización del loader, subir `CACHE_VERSION` en `config.py`.

## Resultados

HTML interactivos (Plotly) en `figuras/`:

- `degradacion/`: una figura por celda con 7 paneles (capacidad, CE, energía, EE, temperatura, ΔT).
- `comparativas/`: todas las celdas juntas (capacidad, ΔT, retención, energía, E/Q, reposo, picos).
- `curvas_carga/`: voltaje y ΔT de la carga por ciclo, una figura por celda.

Informes CSV (anomalías de datos y ciclos detectados) en `informes/`.

