# -*- coding: utf-8 -*-
"""
Scraper ENARGAS — descarga XLS por tipo de operación (GNC)
Robusto para GitHub Actions / Headless

- Selecciona: "Prácticas informadas por Tipo de Operación"
- Selecciona año (periodo): 2026 (podés parametrizarlo)
- Recorre los "cuadros" y descarga un XLS por cada uno
- Espera a que aparezca un archivo .xls nuevo para confirmar descarga
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


URL = "https://www.enargas.gov.ar/secciones/gas-natural-comprimido/estadisticas.php"


def listar_xls(download_dir: str):
    """Lista .xls ordenados por fecha de modificación (asc)."""
    files = glob(os.path.join(download_dir, "*.xls"))
    return sorted(files, key=os.path.getmtime)


def esperar_nuevo_xls(download_dir: str, prev_set: set, timeout: int = 90):
    """
    Espera hasta que aparezca un .xls nuevo en download_dir respecto a prev_set.
    También espera a que no haya .crdownload en curso.
    Devuelve el path del nuevo archivo o None si timeout.
    """
    t0 = time.time()
    while time.time() - t0 < timeout:
        # si hay descargas en curso, esperar
        if any(name.endswith(".crdownload") for name in os.listdir(download_dir)):
            time.sleep(0.5)
            continue

        actuales = set(listar_xls(download_dir))
        nuevos = list(actuales - prev_set)
        if nuevos:
            # devolver el más nuevo (por mtime)
            return max(nuevos, key=os.path.getmtime)

        time.sleep(0.5)

    return None


def descargar_estadisticas(periodo: str = "2026"):
    options = webdriver.ChromeOptions()

    # En Actions, esto suele ser más estable para descargas que --headless "viejo"
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

        # Tipo consulta
        Select(wait.until(EC.presence_of_element_located((By.ID, "tipo-consulta-gnc")))) \
            .select_by_visible_text("Prácticas informadas por Tipo de Operación")

        # Periodo/año
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

                # Re-obtener el select cada vez (evita StaleElement si el DOM cambia)
                cuadro_select = wait.until(EC.presence_of_element_located((By.ID, "cuadro")))

                # Esperar a que existan opciones cargadas
                wait.until(lambda d: len(cuadro_select.find_elements(By.TAG_NAME, "option")) > 1)

                # Seleccionar cuadro
                Select(cuadro_select).select_by_visible_text(cuadro)

                # Click en "ver xls"
                btn = wait.until(EC.element_to_be_clickable((By.ID, "btn-ver-xls")))
                btn.click()

                # Esperar que aparezca un XLS nuevo
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
    descargar_estadisticas("2026")
