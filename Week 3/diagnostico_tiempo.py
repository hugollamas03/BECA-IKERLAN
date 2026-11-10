import pandas as pd
from config import CACHE
from data_loader import buscar_celdas

pd.set_option("display.width", 250)
cols = ["Date_Time", "Test_Time(s)", "Step_Time(s)", "Cycle_Index", "Step_Index"]
for num in sorted(buscar_celdas()):
    c = pd.read_parquet(CACHE / f"C{num}_canal.parquet", columns=cols)
    saltos = c.index[c["Test_Time(s)"].diff() < 0]
    dup = c.index[c["Test_Time(s)"].duplicated(keep=False)]
    print(f"\n=== C{num}: {len(saltos)} saltos hacia atras, {len(dup)} filas con tiempo duplicado")
    for i in saltos[:5]:
        print(f"-- salto en fila {i}")
        print(c.iloc[max(i - 2, 0):i + 2].to_string())
    if len(dup):
        print("-- duplicados (primeros 10)")
        print(c.loc[dup[:10]].to_string())