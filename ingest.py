# scripts/ingest.py
import re
from datetime import datetime
from supabase import create_client
import pandas as pd

# Importamos tu scraper, que debe exponer una función
# que devuelve un dict { nombre_archivo: DataFrame }
import scraper_enargas

# Inicializamos Supabase con las variables de entorno (secrets de GitHub)
import os
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
supa = create_client(SUPABASE_URL, SUPABASE_KEY)


def parse_filename(fn: str):
    """
    De "conversiones-20250425-085057.xls" extrae
    -> practica="conversiones", fecha=date(2025,4,25)
    """
    m = re.match(r"(.+)-(\d{8})-\d{6}\.xls[x]?$", fn)
    if not m:
        raise ValueError(f"Nombre de archivo no cumple patrón: {fn}")
    practica = m.group(1)
    fecha = datetime.strptime(m.group(2), "%Y%m%d").date()
    return practica, fecha


def upsert_practica(nombre: str) -> int:
    """Inserta o busca la práctica y devuelve su id."""
    resp = supa.table("practicas") \
               .select("id").eq("nombre", nombre) \
               .maybe_single().execute()
    if resp.data:
        return resp.data["id"]
    ins = supa.table("practicas") \
              .insert({"nombre": nombre}) \
              .execute()
    return ins.data[0]["id"]


def upsert_provincia(nombre: str) -> int:
    """Lo mismo para provincias."""
    resp = supa.table("provincias") \
               .select("id").eq("nombre", nombre) \
               .maybe_single().execute()
    if resp.data:
        return resp.data["id"]
    ins = supa.table("provincias") \
              .insert({"nombre": nombre}) \
              .execute()
    return ins.data[0]["id"]


def run():
    # 1) Obtenemos los DataFrames desde el scraper
    #    scraper_enargas.fetch_excels() debe devolver:
    #      { "conversiones-20250425-085057.xls": pd.DataFrame, ... }
    archivos: dict[str, pd.DataFrame] = scraper_enargas.fetch_excels()

    # 2) Procesamos cada uno
    for fn, df in archivos.items():
        practica, fecha = parse_filename(fn)

        # Extraemos la última fila (acumulado hasta la fecha)
        serie_ult = df.iloc[-1]  # índice = provincia, valor = acumulado

        pid = upsert_practica(practica)

        registros = []
        for provincia, val in serie_ult.items():
            prov_id = upsert_provincia(provincia)
            registros.append({
                "practica_id":  pid,
                "provincia_id": prov_id,
                "fecha":        fecha,
                "acumulado":    int(val)
            })

        # 3) Hacemos upsert en bloque para evitar duplicados
        supa.table("estadisticas_diarias") \
            .upsert(registros,
                    on_conflict=["practica_id","provincia_id","fecha"]) \
            .execute()


if __name__ == "__main__":
    run()
