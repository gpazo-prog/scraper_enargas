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


def _wait_for_download(download_dir: str, timeout: int = 30):
    """
    Espera hasta que aparezca un nuevo archivo *.xls* sin extensión .crdownload.
    """
    patrón = os.path.join(download_dir, "*.xls*")
    end_time = time.time() + timeout
    while time.time() < end_time:
        archivos = glob.glob(patrón)
        # descartamos temporales de Chrome (crdownload)
        completos = [f for f in archivos if not f.endswith(".crdownload")]
        if completos:
            # devolvemos el path del archivo más reciente
            return max(completos, key=os.path.getmtime)
        time.sleep(1)
    raise TimeoutError(f"Timeout: no se terminó de descargar en {timeout}s")


def fetch_excels() -> dict[str, pd.DataFrame]:
    """
    1) Descarga con Selenium los 6 .xls* a descargas_enargas/
    2) Espera a que termine cada descarga
    3) Lee cada archivo en memoria, detectando si es Excel o HTML
    4) Devuelve { nombre_archivo: DataFrame }
    """
    download_dir = os.path.abspath("descargas_enargas")
    os.makedirs(download_dir, exist_ok=True)

    # Limpiar previos
    for f in glob.glob(os.path.join(download_dir, "*.xls*")):
        os.remove(f)

    # Configuración de Chrome
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    prefs = {"download.default_directory": download_dir}
    options.add_experimental_option("prefs", prefs)

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    wait = WebDriverWait(driver, 15)

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

    descargados = []
    for cuadro in cuadros:
        wait.until(EC.text_to_be_present_in_element((By.ID, "cuadro"), cuadro))
        Select(wait.until(EC.presence_of_element_located((By.ID, "cuadro")))) \
            .select_by_visible_text(cuadro)
        btn = wait.until(EC.element_to_be_clickable((By.ID, "btn-ver-xls")))
        btn.click()
        # Esperamos a que termine la descarga y devolvemos el path
        path = _wait_for_download(download_dir)
        descargados.append(path)
        print(f"✅ Descargado: {os.path.basename(path)}")

    driver.quit()
    print("✔️ Todas las descargas terminadas.")

    # Leer en memoria
    dfs: dict[str, pd.DataFrame] = {}
    for filepath in descargados:
        nombre = os.path.basename(filepath)
        ext = os.path.splitext(nombre)[1].lower()

        # Intento de lectura Excel
        df = None
        for engine in ({"xlrd"} if ext == ".xls" else {"openpyxl"}):
            try:
                df = pd.read_excel(filepath, header=0, index_col=0, engine=engine)
                print(f"📥 Leído (Excel, engine={engine}): {nombre}")
                break
            except Exception:
                df = None

        # Si no es un Excel válido, lo parseo como HTML
        if df is None:
            try:
                tables = pd.read_html(filepath, header=0, index_col=0)
                df = tables[0]
                print(f"📥 Leído (HTML fallback): {nombre}")
            except Exception as e:
                print(f"❌ No pude leer {nombre} ni como Excel ni como HTML: {e}")
                continue

        dfs[nombre] = df

    return dfs


if __name__ == "__main__":
    archivos = fetch_excels()
    print(f"Se cargaron {len(archivos)} DataFrames en memoria.")
