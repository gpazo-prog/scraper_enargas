import os
import base64
import json
from pydrive2.auth import GoogleAuth
from pydrive2.drive import GoogleDrive

# Leer y decodificar el secreto GDRIVE_CREDENTIALS
cred_b64 = os.environ.get("GDRIVE_CREDENTIALS")
if not cred_b64:
    raise Exception("No se encontró la variable de entorno GDRIVE_CREDENTIALS")

cred_json = base64.b64decode(cred_b64).decode("utf-8")

# Guardar temporalmente las credenciales
os.makedirs("gdrive_auth", exist_ok=True)
cred_path = "gdrive_auth/credentials.json"
with open(cred_path, "w") as f:
    f.write(cred_json)

# Configurar PyDrive2 con la cuenta de servicio
gauth = GoogleAuth()
gauth.LoadSettings()
gauth.credentials = gauth.LoadServiceConfigFile(cred_path)
drive = GoogleDrive(gauth)

# ID de la carpeta de destino en Drive (compartida con la cuenta de servicio)
# ⚠️ Lo ideal es obtenerlo automáticamente. Por ahora lo buscamos por nombre:
CARPETA_DESTINO = "ENARGAS_Automatico"

# Buscar la carpeta por nombre
folder_list = drive.ListFile({
    'q': f"title='{CARPETA_DESTINO}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
}).GetList()

if not folder_list:
    raise Exception(f"No se encontró la carpeta '{CARPETA_DESTINO}' en tu Google Drive")

folder_id = folder_list[0]['id']

# Subir todos los .xls desde la carpeta local
carpeta_local = "descargas_enargas"
for archivo in os.listdir(carpeta_local):
    if archivo.endswith(".xls"):
        ruta = os.path.join(carpeta_local, archivo)
        file_drive = drive.CreateFile({'title': archivo, 'parents': [{'id': folder_id}]})
        file_drive.SetContentFile(ruta)
        file_drive.Upload()
        print(f"✅ Subido a Drive: {archivo}")
