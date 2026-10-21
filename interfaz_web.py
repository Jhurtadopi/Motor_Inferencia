# -*- coding: utf-8 -*-
"""Interfaz grafica (web local) del sistema experto.

Solo usa la biblioteca estandar de Python: no hay que instalar nada.

    python3 interfaz_web.py            (abre http://127.0.0.1:8000 en el navegador)
    python3 interfaz_web.py --puerto 9000 --sin-navegador

El servidor escucha unicamente en 127.0.0.1 (solo este equipo).
"""

import argparse
import glob
import json
import os
import re
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DIRECTORIO = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, DIRECTORIO)

import motor_inferencia_taller as motor  # noqa: E402

RUTA_PAGINA = os.path.join(DIRECTORIO, "interfaz", "index.html")
TAMANO_MAXIMO = 2 * 1024 * 1024  # 2 MB por solicitud


def descripcion_reglas(reglas):
    return {
        "reglas": reglas,
        "sintomas": motor.obtener_hechos_entrada(reglas),
    }


def listar_casos():
    casos = []
    for ruta in sorted(glob.glob(os.path.join(motor.DIRECTORIO_CASOS, "*.json"))):
        try:
            with open(ruta, "r", encoding="utf-8") as f:
                datos = json.load(f)
            casos.append({
                "nombre": os.path.splitext(os.path.basename(ruta))[0],
                "descripcion": datos.get("_descripcion", "") if isinstance(datos, dict) else "",
                "hechos": motor.hechos_desde_datos(datos),
            })
        except (OSError, ValueError):
            continue  # un caso mal formado no debe tumbar la interfaz
    return casos


def ejecutar_inferencia(cuerpo):
    reglas = motor.reglas_desde_datos(cuerpo.get("reglas"))
    hechos = cuerpo.get("hechos", [])
    if not isinstance(hechos, list) or not all(isinstance(h, str) for h in hechos):
        raise ValueError("'hechos' debe ser una lista de texto")

    validos, desconocidos = motor.validar_hechos(hechos, reglas)
    hechos_finales, pasos = motor.inferir(validos, reglas)
    return {
        "hechos_iniciales": validos,
        "desconocidos": desconocidos,
        "hechos_finales": sorted(hechos_finales),
        "pasos": pasos,
        "recomendaciones": motor.obtener_recomendaciones(pasos),
        "reporte": motor.texto_reporte(validos, hechos_finales, pasos, desconocidos),
    }


PATRON_NOMBRE = re.compile(r"^[A-Za-z0-9_-]{1,60}$")
PATRON_HECHO = re.compile(r"^[a-z0-9_]{1,80}$")


def guardar_caso(cuerpo):
    """Guarda los hechos marcados como casos/<nombre>.json (mismo formato que los casos de ejemplo)."""
    nombre = cuerpo.get("nombre")
    if not isinstance(nombre, str) or not PATRON_NOMBRE.match(nombre):
        raise ValueError("El nombre solo puede tener letras, números, guion y guion bajo (máximo 60)")
    hechos = cuerpo.get("hechos")
    if (not isinstance(hechos, list) or not hechos
            or not all(isinstance(h, str) and PATRON_HECHO.match(h) for h in hechos)):
        raise ValueError("Marque al menos un síntoma válido para guardar el caso")
    descripcion = cuerpo.get("descripcion", "")
    if not isinstance(descripcion, str) or len(descripcion) > 200:
        raise ValueError("La descripción debe ser texto de hasta 200 caracteres")

    contenido = {}
    if descripcion.strip():
        contenido["_descripcion"] = descripcion.strip()
    for hecho in sorted(set(hechos)):
        contenido[hecho] = True

    os.makedirs(motor.DIRECTORIO_CASOS, exist_ok=True)
    ruta = os.path.join(motor.DIRECTORIO_CASOS, nombre + ".json")
    try:
        with open(ruta, "x", encoding="utf-8") as archivo:  # "x": nunca sobrescribe un caso existente
            json.dump(contenido, archivo, ensure_ascii=False, indent=2)
            archivo.write("\n")
    except FileExistsError:
        raise FileExistsError("Ya existe el caso «%s». Elija otro nombre." % nombre)
    return {"nombre": nombre, "ruta": "casos/%s.json" % nombre}


class Manejador(BaseHTTPRequestHandler):
    server_version = "SistemaExperto/1.0"

    def log_message(self, formato, *args):  # consola limpia
        pass

    def _responder(self, codigo, contenido, tipo="application/json; charset=utf-8"):
        cuerpo = contenido if isinstance(contenido, bytes) else json.dumps(contenido).encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(cuerpo)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(cuerpo)

    def _error(self, codigo, mensaje):
        self._responder(codigo, {"error": mensaje})

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            try:
                with open(RUTA_PAGINA, "rb") as f:
                    self._responder(200, f.read(), "text/html; charset=utf-8")
            except OSError:
                self._error(500, "No se encontro interfaz/index.html")
        elif self.path == "/api/kb/defecto":
            try:
                reglas = motor.cargar_base_conocimiento(motor.RUTA_BASE_CONOCIMIENTO)
            except (OSError, ValueError) as error:
                self._error(400, "No se pudo cargar la base por defecto: %s" % error)
                return
            respuesta = descripcion_reglas(reglas)
            respuesta["nombre"] = os.path.basename(motor.RUTA_BASE_CONOCIMIENTO)
            self._responder(200, respuesta)
        elif self.path == "/api/casos":
            self._responder(200, {"casos": listar_casos()})
        else:
            self._error(404, "Ruta no encontrada")

    def do_POST(self):
        try:
            longitud = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            longitud = 0
        if longitud <= 0 or longitud > TAMANO_MAXIMO:
            self._error(413, "Solicitud vacia o demasiado grande")
            return
        try:
            cuerpo = json.loads(self.rfile.read(longitud).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._error(400, "El cuerpo no es un JSON valido")
            return
        if not isinstance(cuerpo, dict):
            self._error(400, "El cuerpo debe ser un objeto JSON")
            return

        try:
            if self.path == "/api/kb":
                reglas = motor.reglas_desde_datos(cuerpo.get("datos"))
                self._responder(200, descripcion_reglas(reglas))
            elif self.path == "/api/inferir":
                self._responder(200, ejecutar_inferencia(cuerpo))
            elif self.path == "/api/casos":
                self._responder(200, guardar_caso(cuerpo))
            else:
                self._error(404, "Ruta no encontrada")
        except FileExistsError as error:
            self._error(409, str(error))
        except OSError as error:
            self._error(500, "No se pudo escribir el archivo: %s" % error)
        except ValueError as error:
            self._error(400, str(error))


def main():
    parser = argparse.ArgumentParser(description="Interfaz web del sistema experto.")
    parser.add_argument("--puerto", type=int, default=8000)
    parser.add_argument("--sin-navegador", action="store_true", help="no abrir el navegador automaticamente")
    args = parser.parse_args()

    try:
        servidor = ThreadingHTTPServer(("127.0.0.1", args.puerto), Manejador)
    except OSError as error:
        print("No se pudo abrir el puerto %d: %s\nPruebe con --puerto 8001" % (args.puerto, error))
        return 1

    url = "http://127.0.0.1:%d" % args.puerto
    print("Sistema experto en %s  (Ctrl+C para cerrar)" % url)
    if not args.sin_navegador:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor cerrado.")
    finally:
        servidor.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
