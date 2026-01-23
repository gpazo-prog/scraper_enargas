# -*- coding: utf-8 -*-
import os
import re
import time
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select, WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager


URL = "https://www.enargas.gov.ar/secciones/gas-natural-comprimido/estadisticas.php"

CUADROS = [
    "Conversiones de vehículos",
    "Desmontajes de equipos en vehículos",
    "Revisiones periódicas de vehículos",
    "Modificaciones de equipos en vehículos",
    "Revisiones de Cilindros",
    "Cilindro de GNC revisiones CRPC",
]

# ✅ Nombres “viejos” compatibles con tu pipeline y con Drive
TIPO_POR_CUADRO = {
    "Conversiones de vehículos": "conversiones",
    "Desmontajes de equipos en vehículos": "desmontajes",
    "Revisiones periódicas de vehículos": "revisiones",
    "Modificaciones de equipos en vehículos": "modificaciones",
    "Revisiones de Cilindros": "revisiones-cilindros-crpc",
    "Cilindro de GNC revisiones CRPC": "revisiones-crpc",
}


def slugify(txt: str) -> str:
    txt = txt.lower()
    txt = re.sub(r"[áàäâ]", "a", txt)
    txt = re.sub(r"[éèëê]", "e", txt)
    txt = re.sub(r"[íìïî]", "i", txt)
    txt = re.sub(r"[óòöô]", "o", txt)
    txt = re.sub(r"[úùüû]", "u", txt)
    txt = re.sub(r"[^a-z0-9]+", "-", txt).strip("-")
    return txt


def configurar_descargas(driver, download_dir: str):
    """
    En headless, Chrome a veces no descarga si no habilitás el comportamiento vía CDP.
    """
    os.makedirs(download_dir, exist_ok=True)
    try:
        driver.execute_cdp_cmd(
            "Page.setDownloadBehavior",
            {"behavior": "allow", "downloadPath": download_dir},
        )
    except Exception:
        # En algunas versiones puede variar, pero normalmente funciona así.
        pass


def listar_archivos(download_dir: str):
    return {f for f in os.listdir(download_dir) if os.path.isfile(os.path.join(download_dir, f))}


def esperar_descarga_nueva(download_dir: str, antes: set, timeout=120):
    """
    Espera a que aparezca un archivo nuevo (y que no tenga .crdownload).
    Devuelve el nombre del archivo nuevo.
    """
    t0 = time.time()
    while time.time() - t0 < timeout:
        ahora = listar_archivos(download_dir)

        # ignorar temporales
        tmp = {f for f in ahora if f.endswith(".crdownload")}
        if tmp:
            time.sleep(0.5)
            continue

        nuevos = list(ahora - antes)
        if nuevos:
            # si aparecen varios, tomar el más reciente
            nuevos_paths = [os.path.join(download_dir, n) for n in nuevos]
            nuevos_paths.sort(key=lambda p: os.path.getmtime(p), reverse=True)
            return os.path.basename(nuevos_paths[0])

        time.sleep(0.5)

    raise TimeoutError("No apareció ningún archivo descargado nuevo (posible bloqueo o demora del sitio).")


def configurar_formulario(driver, wait, periodo: str):
    print("🌐 Abriendo URL ENARGAS...", flush=True)
    driver.get(URL)
    print("✅ Página cargada", flush=True)
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
        print(f"⚠️ El año {periodo} no está disponible. Fallback a {prev}.", flush=True)
        return prev

    raise ValueError(f"No encontré {periodo} ni {prev} en 'periodo'. Opciones: {opciones}")


def descargar_estadisticas():
    periodo = str(datetime.now().year)
    print(f"📅 Período objetivo: {periodo}", flush=True)

    download_dir = os.path.abspath("descargas_enargas")
    os.makedirs(download_dir, exist_ok=True)

    options = webdriver.ChromeOptions()

    # Headless + estabilidad en GitHub Actions
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")

    # ✅ Evitar prompts de descarga
    prefs = {
        "download.default_directory": download_dir,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True,
        # a veces ayuda con sitios “quisquillosos”
        "profile.default_content_settings.popups": 0,
    }
    options.add_experimental_option("prefs", prefs)

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    
    driver.set_page_load_timeout(60)
    print("✅ Chrome listo", flush=True)
    
    configurar_descargas(driver, download_dir)
    wait = WebDriverWait(driver, 30)

    try:
        periodo_real = configurar_formulario(driver, wait, periodo)
        print(f"✅ Período seleccionado: {periodo_real}", flush=True)

        for cuadro in CUADROS:
            tipo = TIPO_POR_CUADRO.get(cuadro, slugify(cuadro))
            print(f"\n▶ Descargando: {cuadro}", flush=True)

            ok = False
            last_err = None

            # ✅ reintentos (ENARGAS a veces responde “intente nuevamente”)
            for intento in range(1, 4):
                try:
                    # Estado limpio
                    configurar_formulario(driver, wait, periodo_real)

                    cuadro_elem = wait.until(EC.presence_of_element_located((By.ID, "cuadro")))
                    Select(cuadro_elem).select_by_visible_text(cuadro)

                    # Snapshot antes de click
                    antes = listar_archivos(download_dir)

                    # Click real (ejecuta reCAPTCHA + submit como humano)
                    btn = wait.until(EC.element_to_be_clickable((By.ID, "btn-ver-xls")))
                    print("🖱️ Click en Ver Excel...", flush=True)
                    btn.click()
                    
                    # Esperar descarga
                    print("⏳ Esperando descarga...", flush=True)
                    descargado = esperar_descarga_nueva(download_dir, antes, timeout=120)
                    print(f"✅ Descarga detectada: {descargado}", flush=True)

                    # Renombrar a formato viejo: tipo-YYYYMMDD-HHMMSS.xls
                    ts = datetime.now()
                    nuevo_nombre = f"{tipo}-{ts:%Y%m%d}-{ts:%H%M%S}.xls"

                    src = os.path.join(download_dir, descargado)
                    dst = os.path.join(download_dir, nuevo_nombre)

                    # Si por casualidad existe, agregar sufijo
                    if os.path.exists(dst):
                        dst = os.path.join(download_dir, f"{tipo}-{ts:%Y%m%d}-{ts:%H%M%S}-{int(time.time())}.xls")

                    os.replace(src, dst)

                    # Validación rápida: si pesa ~400 bytes es error HTML
                    size = os.path.getsize(dst)
                    if size < 1500:
                        # guardo contenido para debug y reintento
                        os.makedirs("debug", exist_ok=True)
                        with open(dst, "rb") as f:
                            content = f.read(3000)
                        with open(os.path.join("debug", f"error_{tipo}.html"), "wb") as f:
                            f.write(content)
                        raise RuntimeError(f"Archivo demasiado chico ({size} bytes). Probable error del servidor.")

                    print(f"✅ OK: {os.path.basename(dst)} | {size} bytes", flush=True)
                    ok = True
                    time.sleep(1.2)
                    break

                except Exception as e:
                    last_err = e
                    time.sleep(2 * intento)

            if not ok:
                os.makedirs("debug", exist_ok=True)
                driver.save_screenshot(f"debug/error_{tipo}.png")
                with open(f"debug/error_{tipo}_page.html", "w", encoding="utf-8") as f:
                    f.write(driver.page_source)

                print(f"❌ Error definitivo en: {cuadro}", flush=True)
                print(repr(last_err))

        print("\n✔️ Descargas finalizadas.")

    finally:
        driver.quit()


if __name__ == "__main__":
    descargar_estadisticas()
