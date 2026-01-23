# -*- coding: utf-8 -*-
"""
Scraper ENARGAS — descarga XLS por tipo de operación (GNC)
Robusto para GitHub Actions / Headless

- Selecciona: "Prácticas informadas por Tipo de Operación"
- Selecciona año automáticamente (año actual)
- Recorre los "cuadros" y descarga un XLS por cada uno
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select, WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

import os
import time
from glob import glob
from datetime import datetime


URL = "https://www.enargas.gov.ar/secciones/gas-natural-comprimido/estadisticas.php"


def listar_xls(download_dir: str):
    files = glob(os.path.join(download_dir, "*.xls"))
    return sorted(files, key=os.path.getmtime)


def esperar_nuevo_xls(download_dir: str, prev_set: set, timeout: int = 90):
    t0 = time.time()
    while time.time() - t0 < timeout:
        # si hay descargas en curso, esperar
        if any(name.endswith(".crdownload") for name in os.listdir(download_dir)):
            time.sleep(0.5)
            continue

        actuales = set(listar_xls(download_dir))
        nuevos = list(actuales - prev_set)
        if nuevos:
            return max(nuevos, key=os.path.getmtime)

        time.sleep(0.5)

    return None


def descargar_estadisticas():
    # Año automático
    periodo = str(datetime.now().year)
    print(f"📅 Período seleccionado automáticamente: {periodo}")

    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920x1080")

    download_dir = os.path.abspath("descargas_enargas")
    os.makedirs(download_dir, exist_ok=True)

    prefs = {
        "download.default_directory": download_dir,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True,
    }
    options.add_experimental_option("prefs", prefs)

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    wait = WebDriverWait(driver, 20)

    try:
        driver.get(URL)

        Select(wait.until(EC.presence_of_element_located((By.ID, "tipo-consulta-gnc")))) \
            .select_by_visible_text("Prácticas informadas por Tipo de Operación")

        Select(wait.until(EC.presence_of_element_located((By.ID, "periodo")))) \
            .select_by_visible_text(periodo)

        cuadros = [
            "Conversiones de vehículos",
            "Desmontajes de equipos en vehículos",
            "Revisiones periódicas de vehículos",
            "Modificaciones de equipos en vehículos",
            "Revisiones de Cilindros",
            "Cilindro de GNC revisiones CRPC",
        ]

        for cuadro in cuadros:
            try:
                prev = set(listar_xls(download_dir))

                cuadro_select = wait.until(EC.presence_of_element_located((By.ID, "cuadro")))
                wait.until(lambda d: len(cuadro_select.find_elements(By.TAG_NAME, "option")) > 1)

                Select(cuadro_select).select_by_visible_text(cuadro)

                btn = wait.until(EC.element_to_be_clickable((By.ID, "btn-ver-xls")))
                btn.click()

                nuevo = esperar_nuevo_xls(download_dir, prev, timeout=90)
                if not nuevo:
                    raise TimeoutError("No apareció un XLS nuevo (descarga no iniciada o bloqueada)")

                print(f"✅ Descargando OK: {cuadro} -> {os.path.basename(nuevo)}")

            except Exception as e:
                print(f"❌ Error al descargar: {cuadro}")
                print(repr(e))

    finally:
        driver.quit()
        print("✔️ Descargas finalizadas.")


if __name__ == "__main__":
    descargar_estadisticas()

