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
    # Permitir descargas en headless
    driver.execute_cdp_cmd("Page.setDownloadBehavior", {
        "behavior": "allow",
        "downloadPath": download_dir
    })


def snapshot_descargas(download_dir):
    """
    Snapshot de archivos descargados: {filename: (mtime, size)}
    Ignora .crdownload y .html (downloads.html, etc).
    """
    snap = {}
    for fn in os.listdir(download_dir):
        low = fn.lower()
        if low.endswith(".crdownload") or low.endswith(".html"):
            continue
        path = os.path.join(download_dir, fn)
        if os.path.isfile(path):
            snap[fn] = (os.path.getmtime(path), os.path.getsize(path))
    return snap


def esperar_descarga(download_dir, snap_antes, timeout=180):
    """
    Espera archivo nuevo o modificado (por overwrite) en download_dir.
    NO renombra, NO valida contenido.
    """
    t0 = time.time()
    ultimo_log = -1

    while time.time() - t0 < timeout:
        # Si hay descargas activas
        try:
            if any(f.endswith(".crdownload") for f in os.listdir(download_dir)):
                time.sleep(0.5)
                continue
        except FileNotFoundError:
            os.makedirs(download_dir, exist_ok=True)

        snap_despues = snapshot_descargas(download_dir)

        # 1) nuevo
        nuevos = set(snap_despues.keys()) - set(snap_antes.keys())
        if nuevos:
            cand = sorted(nuevos, key=lambda fn: snap_despues[fn][0], reverse=True)
            return cand[0]

        # 2) modificado (overwrite)
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


def esperar_nueva_ventana(driver, handles_antes, timeout=10):
    """
    Espera que aparezca un nuevo window handle.
    Devuelve el handle nuevo o None si no aparece.
    """
    t0 = time.time()
    while time.time() - t0 < timeout:
        handles = driver.window_handles
        nuevos = [h for h in handles if h not in handles_antes]
        if nuevos:
            return nuevos[0]
        time.sleep(0.2)
    return None


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
    # OJO: si el sitio abre popup/tab, no lo bloqueamos
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

                # Snapshot antes de descargar
                snap_antes = snapshot_descargas(download_dir)

                # Guardar handles actuales (para detectar nueva ventana/tab)
                handles_antes = driver.window_handles[:]
                original = driver.current_window_handle

                # Click real
                btn = wait.until(EC.element_to_be_clickable((By.ID, "btn-ver-xls")))
                print("🖱️ Click en Ver Excel...", flush=True)
                btn.click()

                # Si abre nueva ventana/tab, cambiar a esa ventana
                nuevo_handle = esperar_nueva_ventana(driver, handles_antes, timeout=10)
                if nuevo_handle:
                    print("🪟 Se abrió una nueva ventana/tab, cambiando...", flush=True)
                    driver.switch_to.window(nuevo_handle)
                    # En algunas webs, la descarga se dispara al cargar esa página:
                    time.sleep(0.5)
                else:
                    print("ℹ️ No se detectó nueva ventana/tab.", flush=True)

                # Esperar descarga
                print("⏳ Esperando descarga...", flush=True)
                archivo = esperar_descarga(download_dir, snap_antes, timeout=180)
                path = os.path.join(download_dir, archivo)
                size = os.path.getsize(path) if os.path.exists(path) else -1
                print(f"✅ Descarga completada: {archivo} | {size} bytes", flush=True)

                # Cerrar la ventana nueva si existe y volver a la original
                if nuevo_handle:
                    try:
                        driver.close()
                    except Exception:
                        pass
                    try:
                        driver.switch_to.window(original)
                    except Exception:
                        # si por alguna razón no existe, al menos seguimos
                        pass

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
