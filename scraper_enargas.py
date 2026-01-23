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

# ✅ Claves compatibles con tu pipeline (procesar_a_db.py + tabla practicas)
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
    + ✅ agrega name/value del botón presionado (clave para Excel)
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
        payload[name] = opt.get_attribute("value") or opt.text

    # textareas
    for ta in form.find_elements(By.XPATH, ".//textarea[@name]"):
        name = ta.get_attribute("name")
        payload[name] = ta.get_attribute("value") or ta.text or ""

    # ✅ IMPORTANTÍSIMO: incluir el submit del botón XLS (muchos backends lo usan)
    btn_name = (btn_elem.get_attribute("name") or "").strip()
    btn_value = (btn_elem.get_attribute("value") or "").strip()

    # Si el botón no trae name/value, igual forzamos los campos que el PHP pide
    # porque el error mostrado era: Undefined array key "Excel" y "action"
    if btn_name and (btn_value or btn_value == ""):
        payload[btn_name] = btn_value if btn_value != "" else "1"

    payload.setdefault("Excel", "Excel")
    payload.setdefault("action", "Excel")

    return action_url, payload


def requests_post_con_cookies(driver, url, payload, download_path):
    """
    Hace POST con requests usando cookies de Selenium.
    Guarda respuesta en download_path.
    Devuelve (status_code, content_type, size_bytes, first_bytes_text)
    """
    sess = requests.Session()

    ua = driver.execute_script("return navigator.userAgent;")
    headers = {
        "User-Agent": ua,
        "Referer": driver.current_url,
        "Origin": "https://www.enargas.gov.ar",
    }

    for c in driver.get_cookies():
        sess.cookies.set(c["name"], c["value"], domain=c.get("domain"), path=c.get("path", "/"))

    r = sess.post(url, data=payload, headers=headers, timeout=60)

    with open(download_path, "wb") as f:
        f.write(r.content)

    head_text = ""
    try:
        head_text = r.content[:300].decode("utf-8", errors="ignore")
    except Exception:
        head_text = ""

    return r.status_code, r.headers.get("Content-Type", ""), len(r.content), head_text


def respuesta_es_error(head_text: str) -> bool:
    ht = (head_text or "").lower()
    # errores típicos que ya viste en 2026
    return any(x in ht for x in [
        "undefined array key",
        "warning",
        "la solicitud no pudo ser procesada",
        "no pudo ser procesada correctamente",
        "fatal error",
        "deprecated:",
    ])


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

    cuadros = list(TIPO_POR_CUADRO.keys())

    try:
        periodo_real = configurar_formulario(driver, wait, periodo)
        print(f"✅ Período seleccionado: {periodo_real}")

        for cuadro in cuadros:
            print(f"\n▶ Intentando: {cuadro}")

            tipo_key = TIPO_POR_CUADRO[cuadro]

            # ✅ reintentos (porque ENARGAS a veces responde “intente nuevamente”)
            ok = False
            last_err = None

            for intento in range(1, 4):
                try:
                    configurar_formulario(driver, wait, periodo_real)

                    cuadro_elem = wait.until(EC.presence_of_element_located((By.ID, "cuadro")))
                    Select(cuadro_elem).select_by_visible_text(cuadro)

                    btn = wait.until(EC.presence_of_element_located((By.ID, "btn-ver-xls")))

                    action_url, payload = extraer_form_y_payload(driver, btn)

                    ts = datetime.now()
                    fname = f"{tipo_key}-{ts:%Y%m%d}-{ts:%H%M%S}.xls"
                    out_path = os.path.join(download_dir, fname)

                    status, ctype, size, head_text = requests_post_con_cookies(driver, action_url, payload, out_path)

                    if status != 200 or respuesta_es_error(head_text):
                        raise RuntimeError(
                            f"Respuesta inválida (intento {intento}/3): status={status}, type={ctype}, bytes={size}"
                        )

                    print(f"✅ Guardado OK: {fname} | status={status} | type={ctype} | bytes={size}")
                    ok = True
                    time.sleep(1.1)  # evita colisiones de HHMMSS
                    break

                except Exception as e:
                    last_err = e
                    # backoff
                    time.sleep(2 * intento)

            if not ok:
                os.makedirs("debug", exist_ok=True)
                driver.save_screenshot(f"debug/error_{slugify(cuadro)}.png")
                with open(f"debug/error_{slugify(cuadro)}.html", "w", encoding="utf-8") as f:
                    f.write(driver.page_source)

                print(f"❌ Error definitivo en: {cuadro}")
                print(repr(last_err))

    finally:
        driver.quit()
        print("\n✔️ Descargas finalizadas.")


if __name__ == "__main__":
    descargar_estadisticas()
