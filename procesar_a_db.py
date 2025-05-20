#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import pandas as pd
import psycopg2
from datetime import datetime, timedelta
from urllib.parse import urlparse

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

def cargar_catalogos(cur):
    cur.execute("SELECT id, nombre FROM practicas")
    practicas = {nombre: pid for pid, nombre in cur.fetchall()}
    cur.execute("SELECT id, nombre FROM provincias")
    provincias = {nombre: pid for pid, nombre in cur.fetchall()}
    return practicas, provincias

def procesar():
    carpeta = "descargas_enargas"
    conn = conectar_db()
    print("✅ Conectado a la DB OK", flush=True)
    cur  = conn.cursor()
    practicas, provincias = cargar_catalogos(cur)

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

        fecha_desc = datetime.strptime(fecha_str, "%Y%m%d").date()
        fecha_datos = fecha_desc - timedelta(days=1)

        ruta = os.path.join(carpeta, archivo)
        if es_html_camuflado(ruta):
            tablas = pd.read_html(ruta, header=0)
            df = tablas[1]
        else:
            df = pd.read_excel(ruta, header=0)

        ultima = df.iloc[-1].drop(["Mes", "Total"], errors="ignore")

        # --- Inicializar acumuladores por práctica ---
        acumulado_total = 0
        diaria_total = 0

        for col, val in ultima.items():
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

            acumulado_actual = int(val) if pd.notna(val) else 0

            cur.execute("""
                SELECT fecha, acumulado
                FROM estadisticas_diarias
                WHERE practica_id = %s AND provincia_id = %s AND fecha < %s
                ORDER BY fecha DESC
                LIMIT 1
            """, (practica_id, provincia_id, fecha_datos))
            resultado = cur.fetchone()

            if resultado:
                fecha_anterior, acumulado_anterior = resultado
                if fecha_anterior.month == fecha_datos.month and fecha_anterior.year == fecha_datos.year:
                    diaria = acumulado_actual - acumulado_anterior
                else:
                    diaria = acumulado_actual
            else:
                diaria = acumulado_actual

            cur.execute("""
                INSERT INTO estadisticas_diarias
                  (practica_id, provincia_id, fecha, acumulado, diaria)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT(practica_id, provincia_id, fecha)
                DO UPDATE SET acumulado = EXCLUDED.acumulado, diaria = EXCLUDED.diaria
            """, (practica_id, provincia_id, fecha_datos, acumulado_actual, diaria))

            # === Sumar para TOTAL si es provincia válida (1 a 24) ===
            if provincia_id <= 24:
                acumulado_total += acumulado_actual
                diaria_total += diaria

        # Al finalizar la práctica, insertar TOTAL (provincia 25)
        provincia_total = 25
        cur.execute("""
            INSERT INTO estadisticas_diarias
              (practica_id, provincia_id, fecha, acumulado, diaria)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT(practica_id, provincia_id, fecha)
            DO UPDATE SET acumulado = EXCLUDED.acumulado, diaria = EXCLUDED.diaria
        """, (practica_id, provincia_total, fecha_datos, acumulado_total, diaria_total))
        print(f"✅ Insertado TOTAL para práctica {practica_id} fecha {fecha_datos}", flush=True)

        print(f"✅ Insertados datos de {archivo}", flush=True)

    print(">>> Commit y cierre", flush=True)        
    conn.commit()
    cur.close()
    conn.close()
    print(">>> Fin procesar()", flush=True)

if __name__ == "__main__":
    procesar()
