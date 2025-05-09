#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import pandas as pd
import psycopg2
from datetime import datetime, timedelta
from urllib.parse import urlparse

# — Función para detectar HTML “camuflado” en .xls de ENARGAS —
def es_html_camuflado(path):
    with open(path, "rb") as f:
        inicio = f.read(1024).lower()
    return any(tag in inicio for tag in (b'<html', b'<table', b'<!doctype html'))


def conectar_db():
    url = os.getenv("SUPABASE_URL")
    pwd = os.getenv("SUPABASE_KEY")
    
    print(f">>> conectar_db(): URL={url}  USER={urlparse(url).username}", flush=True)

    if not url or not pwd:
        raise RuntimeError("Falta SUPABASE_URL o SUPABASE_KEY")
        
     # parseamos la URL sin contraseña   
    parsed = urlparse(url)
    return psycopg2.connect(
        host     = parsed.hostname,
        port     = parsed.port,
        dbname   = parsed.path.lstrip("/"),
        user     = parsed.username,
        password = pwd,
        sslmode  = "require",
        connect_timeout = 20
    )

# esta funciono 2 veces y una no
#def conectar_db():
#    dsn = os.getenv("DATABASE_URL")
#    if not dsn:
#        raise RuntimeError("Falta la variable de entorno DATABASE_URL")
#    # Conecta directamente usando el DSN completo
#    #print(">>> conectar_db():" )
#    return psycopg2.connect(dsn, sslmode="require", connect_timeout=20)

# — Carga los catálogos de prácticas y provincias a dicts —
def cargar_catalogos(cur):
    cur.execute("SELECT id, nombre FROM practicas")
    practicas = {nombre: pid for pid, nombre in cur.fetchall()}
    cur.execute("SELECT id, nombre FROM provincias")
    provincias = {nombre: pid for pid, nombre in cur.fetchall()}
    return practicas, provincias

# — Main: procesa cada .xls y vuelca la última fila a la tabla estadisticas_diarias —
def procesar():
    #print(">>> Inicio procesar()", flush=True)
    carpeta = "descargas_enargas"
    conn = conectar_db()
    print("✅ Conectado a la DB OK", flush=True)
    cur  = conn.cursor()
    practicas, provincias = cargar_catalogos(cur)

    # mapeos de nombre de archivo → clave en practicas
    # (debe coincidir con la columna “nombre” en practicas)
    # Ej: 'conversiones' → practica 'conversiones'
    # Ya fue cargado al catálogo
    pattern = re.compile(r"^([a-z\-]+)-(\d{8})-\d{6}\.xls$", re.IGNORECASE)

    for archivo in os.listdir(carpeta):
        print(f">>> Procesando archivo: {archivo}", flush=True)
        if not archivo.lower().endswith(".xls"):
            continue
        m = pattern.match(archivo)
        if not m:
            continue

        tipo_raw, fecha_str = m.group(1), m.group(2)
        practica_id = practicas.get(tipo_raw.lower())
        if not practica_id:
            print(f"⚠ Práctica no encontrada: {tipo_raw}")
            continue

        # la fecha de datos es un día antes de la descarga
        fecha_desc = datetime.strptime(fecha_str, "%Y%m%d").date()
        fecha_datos = fecha_desc - timedelta(days=1)

        ruta = os.path.join(carpeta, archivo)
        # leer tabla 1 (índice 1)
        if es_html_camuflado(ruta):
            tablas = pd.read_html(ruta, header=0)
            df = tablas[1]
        else:
            df = pd.read_excel(ruta, header=0)

        # extraer última fila (drop Mes y Total)
        ultima = df.iloc[-1].drop(["Mes", "Total"], errors="ignore")

        # para cada columna/provincia
        for col, val in ultima.items():
            # normalizar algunos nombres
            if col == "Capital Federal":
                prov = "Ciudad Autónoma de Buenos Aires"
            elif col == "Sgo. del Estero":
                prov = "Santiago del Estero"
            elif col == "T. del Fuego":
                prov = "Tierra del Fuego"
            else:
                prov = col

            provincia_id = provincias.get(prov)
            if provincia_id is None:
                print(f"⚠ Provincia no mapeada: {prov}")
                continue

            acumulado = int(val) if pd.notna(val) else 0
             
            # === Aquí añadimos el print de depuración ===
            #print(f">>> UPSERT -> practica_id={practica_id}, provincia_id={provincia_id}, fecha={fecha_datos}, acumulado={acumulado}", flush=True)


            # insertar con upsert y si hay una fila con igual practica_id, provincia_id y fecha lo pisa con el nuevo dato
            cur.execute("""
                INSERT INTO estadisticas_diarias
                  (practica_id, provincia_id, fecha, acumulado)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT(practica_id, provincia_id, fecha)
                DO UPDATE SET acumulado = EXCLUDED.acumulado
            """, (practica_id, provincia_id, fecha_datos, acumulado))
            
            # insertar con upsert y si hay una fila con igual practica_id, provincia_id y fecha no hace nada
            #cur.execute("""
            #    INSERT INTO estadisticas_diarias
            #      (practica_id, provincia_id, fecha, acumulado)
            #    VALUES (%s, %s, %s, %s)
            #    ON CONFLICT(practica_id, provincia_id, fecha)
            #    DO NOTHING;
            #""", (practica_id, provincia_id, fecha_datos, acumulado))
            
            print(f"✅ Insertados datos de {archivo}", flush=True)
            
    print(">>> Commit y cierre", flush=True)        
    conn.commit()
    cur.close()
    conn.close()
    print(">>> Fin procesar()", flush=True)
    
if __name__ == "__main__":
    procesar()
