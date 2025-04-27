# Este es el script de scraping original (sin Drive)
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select, WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import os
import time

def descargar_estadisticas():
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920x1080")

    download_dir = os.path.abspath("descargas_enargas")
    os.makedirs(download_dir, exist_ok=True)

    prefs = {"download.default_directory": download_dir}
    options.add_experimental_option("prefs", prefs)

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    wait = WebDriverWait(driver, 5)

    driver.get("https://www.enargas.gov.ar/secciones/gas-natural-comprimido/estadisticas.php")

    Select(wait.until(EC.presence_of_element_located((By.ID, "tipo-consulta-gnc"))))\
        .select_by_visible_text("Prácticas informadas por Tipo de Operación")
    Select(wait.until(EC.presence_of_element_located((By.ID, "periodo"))))\
        .select_by_visible_text("2025")

    cuadros = [
        "Conversiones de vehículos",
        "Desmontajes de equipos en vehículos",
        "Revisiones periódicas de vehículos",
        "Modificaciones de equipos en vehículos",
        "Revisiones de Cilindros",
        "Cilindro de GNC revisiones CRPC"
    ]

    for cuadro in cuadros:
        try:
            wait.until(EC.text_to_be_present_in_element((By.ID, "cuadro"), cuadro))
            Select(wait.until(EC.presence_of_element_located((By.ID, "cuadro"))))\
                .select_by_visible_text(cuadro)
            wait.until(EC.element_to_be_clickable((By.ID, "btn-ver-xls")))
            driver.find_element(By.ID, "btn-ver-xls").click()
            print(f"✅ Descargando: {cuadro}")
            time.sleep(2)
        except Exception as e:
            print(f"❌ Error al descargar: {cuadro}")
            print(e)

    driver.quit()
    print("✔️ Descargas finalizadas.")

if __name__ == "__main__":
    descargar_estadisticas()
