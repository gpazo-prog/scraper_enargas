# -*- coding: utf-8 -*-
import os
import time
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select, WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.action_chains import ActionChains
from webdriver_manager.chrome import ChromeDriverManager

URL = "https://www.enargas.gov.ar/secciones/gas-natural-comprimido/estadisticas.php"


def configurar_descargas(driver, download_dir):
    # Permitir descargas en headless
    driver.execute_cdp_cmd("Page.setDownloadBehavior", {
        "behavior": "allow",
        "downloadPath": download_dir
    })


def snapshot_descargas(download_dir):
    snap = {}
    if not os.path.isdir(download_dir):
        return snap

    for fn in os.listdir(download_dir):
        low = fn.lower()
        # NO contamos temporales ni html “internos”
        if low.endswith(".crdownload") or low.endswith(".html"):
            continue
        path = os.path.join(download_dir, fn)
        if os.path.isfile(path):
            snap[fn] = (os.path.getmtime(path), os.path.getsize(path))
    return snap


def esperar_descarga(download_dir, snap_antes, timeout=180):
    t0 = time.time()
    ultimo_log = -1

    while time.time() - t0 < timeout:
        # Esperar que no queden .crdownload activos
        if os.path.isdir(download_dir):
            if any(f.endswith(".crdownload") for f in os.listdir(download_dir)):
                time.sleep(0.4)
                continue

        snap_despues = snapshot_descargas(download_dir)

        # Nuevo archivo
        nuevos = set(snap_despues.keys()) - set(snap_antes.keys())
        if nuevos:
            cand = sorted(nuevos, key=lambda fn: snap_despues[fn][0], reverse=True)
            return cand[0]

        # Archivo existente modificado (por overwrite)
        comunes = set(snap_despues.keys()) & set(snap_antes.keys())
        cambiados = [fn for fn in comunes if snap_despues[fn] != snap_antes[fn]]
        if cambiados:
            cand = sorted(cambiados, key=lambda fn: snap_despues[fn][0], reverse=True)
            return cand[0]

        sec = int(time.time() - t0)
        if sec // 10 != ultimo_log:
            ultimo_log = sec // 10
            print(f"… esperando descarga ({sec}s)", flush=True)

        time.sleep(0.5)

    raise TimeoutError("No apareció ninguna descarga (nueva o modificada) dentro del timeout.")


def seleccionar_periodo(driver, wait, periodo_objetivo: str) -> str:
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
    print("🌐 Abriendo URL ENARGAS...", flush=True)
    driver.get(URL)
    print("✅ Página cargada", flush=True)

    Select(wait.until(EC.presence_of_element_located((By.ID, "tipo-consulta-gnc")))) \
        .select_by_visible_text("Prácticas informadas por Tipo de Operación")

    periodo_real = seleccionar_periodo(driver, wait, periodo_objetivo)
    return periodo_real


def click_ver_excel(driver, wait):
    """
    Hace click de forma robusta:
    1) scroll + ActionChains click
    2) JS click
    3) ejecutar la función real del onClick (igual que humano)
    """
    btn = wait.until(EC.presence_of_element_located((By.ID, "btn-ver-xls")))

    # Asegurar que esté en pantalla
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
    time.sleep(0.2)

    # 1) Click “humano”
    try:
        wait.until(EC.element_to_be_clickable((By.ID, "btn-ver-xls")))
        ActionChains(driver).move_to_element(btn).pause(0.1).click(btn).perform()
        return
    except Exception:
        pass

    # 2) JS click
    try:
        driver.execute_script("arguments[0].click();", btn)
        return
    except Exception:
        pass

    # 3) Ejecutar exactamente la función del onClick del HTML
    # (según tu inspección: GenerarConsultaEstadisticasGNC_N('Excel'))
    driver.execute_script("return GenerarConsultaEstadisticasGNC_N('Excel');")


def descargar_estadisticas():
    periodo_objetivo = str(datetime.now().year)
    print(f"📅 Período objetivo: {periodo_objetivo}", flush=True)

    download_dir = os.path.abspath("descargas_enargas")
    os.makedirs(download_dir, exist_ok=True)

    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920x1080")
    options.add_argument("--disable-popup-blocking")

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
        periodo_real = configurar_formulario(driver, wait, periodo_objetivo)
        print(f"✅ Período seleccionado: {periodo_real}", flush=True)

        for cuadro in cuadros:
            print(f"\n▶ Descargando: {cuadro}", flush=True)

            try:
                # Estado limpio
                periodo_real = configurar_formulario(driver, wait, periodo_real)

                # Seleccionar cuadro
                cuadro_elem = wait.until(EC.presence_of_element_located((By.ID, "cuadro")))
                Select(cuadro_elem).select_by_visible_text(cuadro)

                # Pequeña pausa para que el DOM/JS asiente valores (token, etc)
                time.sleep(0.3)

                # Snapshot antes de descargar
                snap_antes = snapshot_descargas(download_dir)

                print("🖱️ Click en Ver Excel...", flush=True)
                click_ver_excel(driver, wait)

                print("⏳ Esperando descarga...", flush=True)
                archivo = esperar_descarga(download_dir, snap_antes, timeout=180)

                path = os.path.join(download_dir, archivo)
                size = os.path.getsize(path) if os.path.exists(path) else -1
                print(f"✅ Descarga completada: {archivo} | {size} bytes", flush=True)

                time.sleep(0.5)

            except Exception as e:
                os.makedirs("debug", exist_ok=True)
                try:
                    driver.save_screenshot(os.path.join("debug", f"error_{cuadro}".replace(" ", "_") + ".png"))
                except Exception:
                    pass
                try:
                    with open(os.path.join("debug", f"error_{cuadro}".replace(" ", "_") + ".html"),
                              "w", encoding="utf-8") as f:
                        f.write(driver.page_source)
                except Exception:
                    pass

                print(f"❌ Error al descargar: {cuadro}", flush=True)
                print(repr(e), flush=True)

    finally:
        try:
            driver.quit()
        except Exception:
            pass
        print("\n✔️ Descargas finalizadas.", flush=True)


if __name__ == "__main__":
    descargar_estadisticas()
