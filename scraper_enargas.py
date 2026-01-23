#Edito el repository para mantenimiento
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
# Viejos PREFS
#    prefs = {"download.default_directory": download_dir}

# Nueva propuesta:

    prefs = {
    "download.default_directory": download_dir,
    "download.prompt_for_download": False,
    "download.directory_upgrade": True,
    "safebrowsing.enabled": True
    }
    
    options.add_experimental_option("prefs", prefs)


    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    wait = WebDriverWait(driver, 5)

    driver.get("https://www.enargas.gov.ar/secciones/gas-natural-comprimido/estadisticas.php")

    Select(wait.until(EC.presence_of_element_located((By.ID, "tipo-consulta-gnc"))))\
        .select_by_visible_text("Prácticas informadas por Tipo de Operación")
    Select(wait.until(EC.presence_of_element_located((By.ID, "periodo"))))\
        .select_by_visible_text("2026")

    cuadros = [
        "Conversiones de vehículos",
        "Desmontajes de equipos en vehículos",
        "Revisiones periódicas de vehículos",
        "Modificaciones de equipos en vehículos",
        "Revisiones de Cilindros",
        "Cilindro de GNC revisiones CRPC"
    ]
# VIEJO FOR SE ROMPIO EL 13/1/2026
#    for cuadro in cuadros:
#        try:
#            wait.until(EC.text_to_be_present_in_element((By.ID, "cuadro"), cuadro))
#            Select(wait.until(EC.presence_of_element_located((By.ID, "cuadro"))))\
#                .select_by_visible_text(cuadro)
#            wait.until(EC.element_to_be_clickable((By.ID, "btn-ver-xls")))
#            driver.find_element(By.ID, "btn-ver-xls").click()
#            print(f"✅ Descargando: {cuadro}")
#            time.sleep(2)
#        except Exception as e:
#            print(f"❌ Error al descargar: {cuadro}")
#            print(e)

#Nueva propuesta
    
    wait = WebDriverWait(driver, 20)
    
    def esperar_descarga_completa(download_dir, timeout=60):
        import time, os
        t0 = time.time()
        while time.time() - t0 < timeout:
            # Chrome deja archivos temporales .crdownload
            tmp = [f for f in os.listdir(download_dir) if f.endswith(".crdownload")]
            if not tmp:
                return True
            time.sleep(0.5)
        return False
    
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
            # Re-obtener el select cada vez (evita StaleElement si el DOM cambia)
            cuadro_select = wait.until(EC.presence_of_element_located((By.ID, "cuadro")))
    
            # Esperar que tenga options cargadas
            wait.until(lambda d: len(cuadro_select.find_elements(By.TAG_NAME, "option")) > 1)
    
            Select(cuadro_select).select_by_visible_text(cuadro)
    
            btn = wait.until(EC.element_to_be_clickable((By.ID, "btn-ver-xls")))
            btn.click()
    
            ok = esperar_descarga_completa(download_dir, timeout=60)
            if not ok:
                raise TimeoutError("La descarga no terminó (sigue .crdownload)")
    
            print(f"✅ Descargando: {cuadro}")
    
        except Exception as e:
            print(f"❌ Error al descargar: {cuadro}")
            print(repr(e))
    
    driver.quit()
    print("✔️ Descargas finalizadas.")

if __name__ == "__main__":
    descargar_estadisticas()
