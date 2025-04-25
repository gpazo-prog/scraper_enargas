import os
import time
import threading
import tkinter as tk
from tkinter import scrolledtext
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select, WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
# Cambio mínimo para activar GitHub Actions
def descargar_estadisticas():
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")  # Necesario en GitHub Actions
    options.add_argument("--disable-dev-shm-usage")  # Necesario en GitHub Actions
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920x1080")

    prefs = {"download.default_directory": os.path.abspath("descargas_enargas")}
    options.add_experimental_option("prefs", prefs)

    os.makedirs("descargas_enargas", exist_ok=True)

    driver = webdriver.Chrome(options=options)
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
            wait.until(EC.presence_of_element_located((By.ID, "btn-ver-xls")))
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
