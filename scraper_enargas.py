# -*- coding: utf-8 -*-
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select, WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

import os
import re
import time
from datetime import datetime
from urllib.parse import urljoin

import requests


URL = "https://www.enargas.gov.ar/secciones/gas-natural-comprimido/estadisticas.php"


def slugify(txt: str) -> str:
    txt = txt.lower()
    txt = re.sub(r"[áàäâ]", "a", txt)
    txt = re.sub(r"[éèëê]", "e", txt)
    txt = re.sub(r"[íìïî]", "i", txt)
    txt = re.sub(r"[óòöô]", "o", txt)
    txt = re.sub(r"[úùüû]", "u", txt)
    txt = re.sub(r"[^a-z0-9]+", "-", txt).strip("-")
    return txt


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


def extraer_form_y_payload(driver, btn_elem):
    """
    Encuentra el <form> ancestro del botón y arma:
    - action_url absoluto
    - payload (dict) con todos los name/value reales del form
    """
    form = btn_elem.find_element(By.XPATH, "ancestor::form")
    action = form.get_attribute("action") or ""
    action_url = urljoin(driver.current_url, action)

    payload = {}

    # inputs (incluye hidden/text/etc)
    for inp in form.find_elements(By.XPATH, ".//input[@name]"):
        name = inp.get_attribute("name")
        itype = (inp.get_attribute("type") or "").lower()
        if itype in ("checkbox", "radio"):
            if inp.is_selected():
                payload[name] = inp.get_attribute("value") or "on"
        else:
            payload[name] = inp.get_attribute("value") or ""

    # selects
    for sel in form.find_elements(By.XPATH, ".//select[@name]"):
        name = sel.get_attribute("name")
        s = Select(sel)
        opt = s.first_selected_option
        # lo más robusto es mandar el value (si no hay, manda el texto)
        payload[name] = opt.get_attribute("value") or opt.text

    # textareas
    for ta in form.find_elements(By.XPATH, ".//textarea[@name]"):
        name = ta.get_attribute("name")
        payload[name] = ta.get_attribute("value") or ta.text or ""

    return action_url, payload


def requests_post_con_cookies(driver, url, payload, download_path):
    """
    Hace POST con requests usando cookies de Selenium.
    Guarda respuesta en download_path.
    Devuelve (status_code, content_type, size_bytes)
    """
    sess = requests.Session()

    # user-agent real del browser
    ua = driver.execute_script("return navigator.userAgent;")
    headers = {
        "User-Agent": ua,
        "Referer": driver.current_url,
        "Origin": "https://www.enargas.gov.ar",
    }

    # cookies del browser -> requests
    for c in driver.get_cookies():
        sess.cookies.set(c["name"], c["value"], domain=c.get("domain"), path=c.get("path", "/"))

    r = sess.post(url, data=payload, headers=headers, timeout=60)

    with open(download_path, "wb") as f:
        f.write(r.content)

    return r.status_code, r.headers.get("Content-Type", ""), len(r.content)


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

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
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
                # Recargar y setear formulario (estado limpio)
                configurar_formulario(driver, wait, periodo_real)

                # seleccionar cuadro
                cuadro_elem = wait.until(EC.presence_of_element_located((By.ID, "cuadro")))
                Select(cuadro_elem).select_by_visible_text(cuadro)

                # ubicar botón
                btn = wait.until(EC.presence_of_element_located((By.ID, "btn-ver-xls")))

                # extraer action + payload real del form
                action_url, payload = extraer_form_y_payload(driver, btn)

                # nombre de archivo
                ts = datetime.now().strftime("%Y%m%d-%H%M%S")
                fname = f"{slugify(cuadro)}-{periodo_real}-{ts}.xls"
                out_path = os.path.join(download_dir, fname)

                # POST vía requests (con cookies de selenium)
                status, ctype, size = requests_post_con_cookies(driver, action_url, payload, out_path)

                print(f"✅ Guardado: {fname} | status={status} | type={ctype} | bytes={size}")

                # Si ENARGAS devuelve HTML de error, lo vas a ver por content-type o tamaño.
                # Igual lo guardamos porque tus otros scripts ya manejan HTML->tabla.
                time.sleep(0.5)

            except Exception as e:
                os.makedirs("debug", exist_ok=True)
                driver.save_screenshot(f"debug/error_{slugify(cuadro)}.png")
                with open(f"debug/error_{slugify(cuadro)}.html", "w", encoding="utf-8") as f:
                    f.write(driver.page_source)

                print(f"❌ Error en: {cuadro}")
                print(repr(e))

    finally:
        driver.quit()
        print("\n✔️ Descargas finalizadas.")


if __name__ == "__main__":
    descargar_estadisticas()

