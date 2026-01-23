# -*- coding: utf-8 -*-
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


def esperar_nuevo_xls(download_dir: str, prev_set: set, timeout: int = 60):
    t0 = time.time()
    while time.time() - t0 < timeout:
        actuales = set(glob(os.path.join(download_dir, "*.xls")))
        nuevos = list(actuales - prev_set)
        if nuevos:
            return max(nuevos, key=os.path.getmtime)
        time.sleep(1)
    return None


def configurar_formulario(driver, wait, periodo: str):
    driver.get(URL)

    Select(wait.until(EC.presence_of_element_located((By.ID, "tipo-consulta-gnc")))) \
        .select_by_visible_text("Prácticas informadas por Tipo de Operación")

    periodo_select = Select(wait.until(EC.presence_of_element_located((By.ID, "periodo"))))
    opciones = [o.text.strip() for o in periodo_select.options]

    if periodo in opciones:
        periodo_select.select_by_visible_text(periodo)
        return periodo

    prev = str(int(periodo) - 1)
    if prev in opciones:
        periodo_select.select_by_visible_text(prev)
        print(f"⚠️ El año {periodo} no está disponible. Fallback a {prev}.")
        return prev

    raise ValueError(f"No encontré {periodo} ni {prev} en 'periodo'. Opciones: {opciones}")


def descargar_estadisticas():
    periodo = str(datetime.now().year)
    print(f"📅 Período objetivo: {periodo}")

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

    # ✅ CLAVE: habilitar descargas explícitamente en headless (Actions)
    driver.execute_cdp_cmd("Page.setDownloadBehavior", {
        "behavior": "allow",
        "downloadPath": download_dir
    })

    wait = WebDriverWait(driver, 25)

    cuadros = [
        "Conversiones de vehículos",
        "Desmontajes de equipos en vehículos",
        "Revisiones periódicas de vehículos",
        "Modificaciones de equipos en vehículos",
        "Revisiones de Cilindros",
        "Cilindro de GNC revisiones CRPC",
    ]

    try:
        periodo_real = configurar_formulario(driver, wait, periodo)
        print(f"✅ Período seleccionado: {periodo_real}")

        for cuadro in cuadros:
            print(f"\n▶ Intentando: {cuadro}")

            try:
                # Recargar y configurar SIEMPRE evita “estado roto”
                configurar_formulario(driver, wait, periodo_real)

                prev = set(listar_xls(download_dir))

                cuadro_elem = wait.until(EC.presence_of_element_located((By.ID, "cuadro")))
                Select(cuadro_elem).select_by_visible_text(cuadro)

                btn = wait.until(EC.element_to_be_clickable((By.ID, "btn-ver-xls")))
                btn.click()

                nuevo = esperar_nuevo_xls(download_dir, prev, timeout=60)
                if not nuevo:
                    raise TimeoutError("No apareció un XLS nuevo (descarga no iniciada o bloqueada)")

                print(f"✅ Descarga OK -> {os.path.basename(nuevo)}")

            except Exception as e:
                os.makedirs("debug", exist_ok=True)
                driver.save_screenshot(f"debug/error_{cuadro.replace(' ', '_')}.png")
                with open(f"debug/error_{cuadro.replace(' ', '_')}.html", "w", encoding="utf-8") as f:
                    f.write(driver.page_source)

                print(f"❌ Error al descargar: {cuadro}")
                print(repr(e))

    finally:
        driver.quit()
        print("\n✔️ Descargas finalizadas.")


if __name__ == "__main__":
    descargar_estadisticas()
