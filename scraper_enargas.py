# scraper_enargas.py

import os
import time
import glob
import pandas as pd

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select, WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager


def fetch_excels() -> dict[str, pd.DataFrame]:
    """
    Ejecuta el scraping de ENARGAS:
      1) Descarga via Selenium los 6 archivos .xls* a descargas_enargas/
      2) Lee cada Excel con pandas en un DataFrame
      3) Devuelve un dict { nombre_archivo: DataFrame }
    """
    # 1) Preparar carpeta de descargas
    download_dir = os.path.abspath("descargas_enargas")
    os.makedirs(download_dir, exist_ok=True)

    # 2) Configurar Chrome en modo headless y con carpeta de descarga
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920x1080")
    prefs = {"download.default_directory": download_dir}
    options.add_experimental_option("prefs", prefs)

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    wait = WebDriverWait(driver, 10)

    # 3) Navegar a la página y seleccionar parámetros
    driver.get("https://www.enargas.gov.ar/secciones/gas-natural-comprimido/estadisticas.php")

    Select(wait.until(EC.presence_of_element_located((By.ID, "tipo-consulta-gnc")))) \
        .select_by_visible_text("Prácticas informadas por Tipo de Operación")
    Select(wait.until(EC.presence_of_element_located((By.ID, "periodo")))) \
        .select_by_visible_text("2025")

    cuadros = [
        "Conversiones de vehículos",
        "Desmontajes de equipos en vehículos",
        "Revisiones periódicas de vehículos",
        "Modificaciones de equipos en vehículos",
        "Revisiones de Cilindros",
        "Cilindro de GNC revisiones CRPC"
    ]

    # 4) Descargar cada Excel
    for cuadro in cuadros:
        try:
            wait.until(EC.text_to_be_present_in_element((By.ID, "cuadro"), cuadro))
            Select(wait.until(EC.presence_of_element_located((By.ID, "cuadro")))) \
                .select_by_visible_text(cuadro)
            btn = wait.until(EC.element_to_be_clickable((By.ID, "btn-ver-xls")))
            btn.click()
            print(f"✅ Descargando: {cuadro}")
            time.sleep(2)  # tiempo para que termine la descarga
        except Exception as e:
            print(f"❌ Error al descargar: {cuadro}", e)

    driver.quit()
    print("✔️ Descargas finalizadas.")

    # 5) Leer los archivos descargados en memoria
    dfs: dict[str, pd.DataFrame] = {}
    for filepath in glob.glob(os.path.join(download_dir, "*.xls*")):
        nombre = os.path.basename(filepath)
        try:
            df = pd.read_excel(filepath, header=0, index_col=0)
            dfs[nombre] = df
        except Exception as e:
            print(f"❌ Error al leer {nombre}: {e}")

    # 6) (Opcional) limpiar la carpeta de descargas
    # for filepath in glob.glob(os.path.join(download_dir, "*.xls*")):
    #     os.remove(filepath)

    return dfs


if __name__ == "__main__":
    # Prueba local
    archivos = fetch_excels()
    print(f"Se descargaron y cargaron {len(archivos)} archivos en memoria.")
