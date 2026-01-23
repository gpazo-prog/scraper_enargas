# -*- coding: utf-8 -*-
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select, WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

import os
import time
from datetime import datetime


URL = "https://www.enargas.gov.ar/secciones/gas-natural-comprimido/estadisticas.php"


CUADROS = [
    "Conversiones de vehículos",
    "Desmontajes de equipos en vehículos",
    "Revisiones periódicas de vehículos",
    "Modificaciones de equipos en vehículos",
    "Revisiones de Cilindros",
    "Cilindro de GNC revisiones CRPC",
]


def configurar_descargas(driver, download_dir: str):
    """
    En headless, Chrome a veces ignora prefs.
    Esto fuerza el comportamiento de descarga al directorio indicado.
    """
    params = {"behavior": "allow", "downloadPath": download_dir}
    # En algunos chromes funciona con Page.setDownloadBehavior
    driver.execute_cdp_cmd("Page.setDownloadBehavior", params)


def esperar_descarga_nueva(download_dir: str, antes: set[str], timeout: int = 180) -> str:
    """
    Espera a que aparezca un archivo nuevo (distinto de los que ya estaban),
    y que no termine en .crdownload.
    Devuelve el nombre del archivo.
    """
    t0 = time.time()
    last_print = -1

    while time.time() - t0 < timeout:
        # prints cada 10s aprox
        elapsed = int(time.time() - t0)
        if elapsed // 10 != last_print:
            last_print = elapsed // 10
            print(f"… esperando descarga ({elapsed}s)", flush=True)

        actuales = set(os.listdir(download_dir))
        nuevos = [f for f in (actuales - antes) if not f.endswith(".crdownload")]

        if nuevos:
            # si aparecieron varios, agarramos el más reciente por mtime
            nuevos_paths = [os.path.join(download_dir, f) for f in nuevos]
            newest = max(nuevos_paths, key=lambda p: os.path.getmtime(p))
            return os.path.basename(newest)

        time.sleep(1)

    raise TimeoutError("No apareció ninguna descarga (nueva o modificada) dentro del timeout.")


def setear_formulario(driver, wait, periodo_objetivo: str) -> str:
    """
    Abre la página y setea:
    - Tipo de estadística
    - Período (año)
    Devuelve el período realmente seteado (fallback al año anterior si no existe).
    """
    print("🌐 Abriendo URL ENARGAS...", flush=True)
    driver.get(URL)
    print("✅ Página cargada", flush=True)

    # Tipo de estadística
    Select(wait.until(EC.presence_of_element_located((By.ID, "tipo-consulta-gnc")))) \
        .select_by_visible_text("Prácticas informadas por Tipo de Operación")

    # Período
    periodo_select = Select(wait.until(EC.presence_of_element_located((By.ID, "periodo"))))
    opciones = [o.text.strip() for o in periodo_select.options]

    if periodo_objetivo in opciones:
        periodo_select.select_by_visible_text(periodo_objetivo)
        return periodo_objetivo

    prev = str(int(periodo_objetivo) - 1)
    if prev in opciones:
        periodo_select.select_by_visible_text(prev)
        print(f"⚠️ El año {periodo_objetivo} no está disponible. Fallback a {prev}.", flush=True)
        return prev

    raise ValueError(f"No encontré {periodo_objetivo} ni {prev} en 'periodo'. Opciones: {opciones}")


def aceptar_cookies_si_aparece(driver):
    """
    Por si aparece un banner que tapa el botón.
    No falla si no existe.
    """
    candidatos = [
        (By.ID, "onetrust-accept-btn-handler"),
        (By.CSS_SELECTOR, "button[aria-label*='Aceptar']"),
        (By.CSS_SELECTOR, "button.cookie-accept"),
    ]
    for by, sel in candidatos:
        try:
            elems = driver.find_elements(by, sel)
            if elems:
                try:
                    elems[0].click()
                    time.sleep(0.5)
                    return
                except Exception:
                    pass
        except Exception:
            pass


def esperar_grecaptcha(driver, timeout=20):
    """
    ENARGAS arma token con grecaptcha.execute (reCAPTCHA v3).
    Esperamos a que esté disponible para que el click haga lo mismo que a mano.
    """
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            ok = driver.execute_script(
                "return (typeof window.grecaptcha !== 'undefined') && "
                "(typeof window.grecaptcha.execute === 'function');"
            )
            if ok:
                return True
        except Exception:
            pass
        time.sleep(0.5)
    # No lo hacemos fatal, pero lo dejamos logueado
    print("⚠️ grecaptcha no apareció a tiempo. Igual intento click.", flush=True)
    return False


def descargar_estadisticas():
    periodo = str(datetime.now().year)
    print(f"📅 Período objetivo: {periodo}", flush=True)

    download_dir = os.path.abspath("descargas_enargas")
    os.makedirs(download_dir, exist_ok=True)

    options = webdriver.ChromeOptions()
    # headless “new” suele ser más estable para descargas hoy
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")

    # prefs (igual dejamos CDP también)
    prefs = {
        "download.default_directory": download_dir,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True,
    }
    options.add_experimental_option("prefs", prefs)

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)

    driver.set_page_load_timeout(60)
    print("✅ Chrome listo", flush=True)

    # fuerza descargas en headless
    configurar_descargas(driver, download_dir)

    wait = WebDriverWait(driver, 30)

    try:
        periodo_real = setear_formulario(driver, wait, periodo)
        print(f"✅ Período seleccionado: {periodo_real}", flush=True)

        for cuadro in CUADROS:
            print(f"\n▶ Descargando: {cuadro}", flush=True)

            # Estado limpio por cada cuadro
            periodo_real = setear_formulario(driver, wait, periodo_real)
            aceptar_cookies_si_aparece(driver)

            # set cuadro
            cuadro_elem = wait.until(EC.presence_of_element_located((By.ID, "cuadro")))
            Select(cuadro_elem).select_by_visible_text(cuadro)

            # esperar recaptcha listo (para que el click haga lo mismo que manual)
            esperar_grecaptcha(driver, timeout=20)

            # antes de click: listado de archivos
            antes = set(os.listdir(download_dir))

            # click real
            btn = wait.until(EC.element_to_be_clickable((By.ID, "btn-ver-xls")))
            print("🖱️ Click en Ver Excel...", flush=True)
            btn.click()

            # esperar descarga nueva (sin renombrar)
            print("⏳ Esperando descarga...", flush=True)
            try:
                fname = esperar_descarga_nueva(download_dir, antes, timeout=180)
                fpath = os.path.join(download_dir, fname)
                size = os.path.getsize(fpath)
                print(f"✅ Descarga detectada: {fname}", flush=True)
                print(f"✅ OK: {fname} | {size} bytes", flush=True)
            except Exception as e:
                # debug
                os.makedirs("debug", exist_ok=True)
                ts = datetime.now().strftime("%Y%m%d-%H%M%S")
                driver.save_screenshot(os.path.join("debug", f"error_{ts}.png"))
                with open(os.path.join("debug", f"error_{ts}.html"), "w", encoding="utf-8") as f:
                    f.write(driver.page_source)
                print(f"❌ Error al descargar: {cuadro}", flush=True)
                print(repr(e), flush=True)

            time.sleep(0.8)

        print("\n✔️ Descargas finalizadas.", flush=True)

    finally:
        driver.quit()


if __name__ == "__main__":
    descargar_estadisticas()
