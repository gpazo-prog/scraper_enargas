# -*- coding: utf-8 -*-
import os
import time
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select, WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager


URL = "https://www.enargas.gov.ar/secciones/gas-natural-comprimido/estadisticas.php"


def configurar_descargas(driver, download_dir):
    """
    En headless, esto es CLAVE para que Chrome permita descargas.
    """
    driver.execute_cdp_cmd("Page.setDownloadBehavior", {
        "behavior": "allow",
        "downloadPath": download_dir
    })


def listar_archivos(download_dir):
    try:
        return set(os.listdir(download_dir))
    except FileNotFoundError:
        return set()


def esperar_descarga(download_dir, antes, timeout=180):
    """
    Espera a que aparezca un archivo nuevo en download_dir.
    - Ignora temporales .crdownload
    - Ignora basura .html (ej: downloads.html)
    - NO renombra, NO valida contenido
    Devuelve el nombre del archivo nuevo.
    """
    inicio = time.time()

    while time.time() - inicio < timeout:
        archivos = listar_archivos(download_dir)

        # si hay descargas en curso, esperar
        if any(a.endswith(".crdownload") for a in archivos):
            time.sleep(0.5)
            continue

        nuevos = list(archivos - antes)
        if nuevos:
            # ignorar html basura
            nuevos = [n for n in nuevos if not n.lower().endswith(".html")]

            if nuevos:
                # devolver el más reciente por mtime
                paths = [os.path.join(download_dir, n) for n in nuevos]
                paths.sort(key=lambda p: os.path.getmtime(p), reverse=True)
                return os.path.basename(paths[0])

        time.sleep(0.5)

    raise TimeoutError("No apareció ninguna descarga nueva (posible demora/bloqueo).")


def seleccionar_periodo(driver, wait, periodo_objetivo: str) -> str:
    """
    Selecciona el año. Si no existe, cae al anterior.
    Devuelve el año realmente seleccionado.
    """
    periodo_select = Select(wait.until(EC.presence_of_element_located((By.ID, "periodo"))))
    opciones = [o.text.strip() for o in periodo_select.options if o.text]

    if periodo_objetivo in opciones:
        periodo_select.select_by_visible_text(periodo_objetivo)
        return periodo_objetivo

    prev = str(int(periodo_objetivo) - 1)
    if prev in opciones:
        periodo_select.select_by_visible_text(prev)
        print(f"⚠️ El año {periodo_objetivo} no está disponible. Fallback a {prev}.", flush=True)
        return prev

    raise ValueError(f"No encontré {periodo_objetivo} ni {prev} en 'periodo'. Opciones: {opciones}")


def configurar_formulario(driver, wait, periodo_objetivo: str) -> str:
    """
    Abre ENARGAS y configura:
    - Tipo: Prácticas informadas por Tipo de Operación
    - Período: año (con fallback)
    Devuelve el año realmente seleccionado.
    """
    print("🌐 Abriendo URL ENARGAS...", flush=True)
    driver.get(URL)
    print("✅ Página cargada", flush=True)

    Select(wait.until(EC.presence_of_element_located((By.ID, "tipo-consulta-gnc")))) \
        .select_by_visible_text("Prácticas informadas por Tipo de Operación")

    periodo_real = seleccionar_periodo(driver, wait, periodo_objetivo)
    return periodo_real


def descargar_estadisticas():
    periodo_objetivo = str(datetime.now().year)
    print(f"📅 Período objetivo: {periodo_objetivo}", flush=True)

    download_dir = os.path.abspath("descargas_enargas")
    os.makedirs(download_dir, exist_ok=True)

    options = webdriver.ChromeOptions()
    # headless nuevo (recomendado)
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920x1080")

    # Preferencias de descarga (mejor que Chrome no pregunte nada)
    prefs = {
        "download.default_directory": download_dir,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True
    }
    options.add_experimental_option("prefs", prefs)

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)

    driver.set_page_load_timeout(60)
    configurar_descargas(driver, download_dir)
    print("✅ Chrome listo", flush=True)

    wait = WebDriverWait(driver, 30)

    cuadros = [
        "Conversiones de vehículos",
        "Desmontajes de equipos en vehículos",
        "Revisiones periódicas de vehículos",
        "Modificaciones de equipos en vehículos",
        "Revisiones de Cilindros",
        "Cilindro de GNC revisiones CRPC",
    ]

    try:
        # Config inicial (tipo + periodo)
        periodo_real = configurar_formulario(driver, wait, periodo_objetivo)
        print(f"✅ Período seleccionado: {periodo_real}", flush=True)

        for cuadro in cuadros:
            try:
                print(f"\n▶ Descargando: {cuadro}", flush=True)

                # Recargar para estado limpio en cada cuadro
                periodo_real = configurar_formulario(driver, wait, periodo_real)

                # Seleccionar cuadro
                cuadro_elem = wait.until(EC.presence_of_element_located((By.ID, "cuadro")))
                Select(cuadro_elem).select_by_visible_text(cuadro)

                # Snapshot de archivos antes del click
                antes = listar_archivos(download_dir)

                # Click real
                btn = wait.until(EC.element_to_be_clickable((By.ID, "btn-ver-xls")))
                print("🖱️ Click en Ver Excel...", flush=True)
                btn.click()

                print("⏳ Esperando descarga...", flush=True)
                archivo = esperar_descarga(download_dir, antes, timeout=180)

                path = os.path.join(download_dir, archivo)
                size = os.path.getsize(path) if os.path.exists(path) else -1
                print(f"✅ Descarga completada: {archivo} | {size} bytes", flush=True)

                # NO renombramos, NO tocamos el archivo

                # pequeña pausa entre descargas
                time.sleep(0.5)

            except Exception as e:
                # Debug mínimo (solo si querés)
                os.makedirs("debug", exist_ok=True)
                driver.save_screenshot(os.path.join("debug", f"error_{cuadro}.png".replace(" ", "_")))
                with open(os.path.join("debug", f"error_{cuadro}.html".replace(" ", "_")),
                          "w", encoding="utf-8") as f:
                    f.write(driver.page_source)

                print(f"❌ Error al descargar: {cuadro}", flush=True)
                print(repr(e), flush=True)

    finally:
        driver.quit()
        print("\n✔️ Descargas finalizadas.", flush=True)


if __name__ == "__main__":
    descargar_estadisticas()
