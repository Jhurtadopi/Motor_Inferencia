# -*- coding: utf-8 -*-
"""Sistema Experto - Diagnostico de fallas en redes y equipos informaticos.

- Base de conocimiento (BC) en un archivo JSON externo.
- Hechos iniciales desde un archivo JSON o de forma interactiva.
- Encadenamiento hacia adelante con resolucion de conflictos explicita.
- Traza paso a paso (consola, interfaz web o reporte) y recomendaciones
  ordenadas por prioridad.

El modulo se puede usar de tres formas:
    python3 motor_inferencia_taller.py                    (interactivo)
    python3 motor_inferencia_taller.py --caso casos/caso_1.json
    python3 motor_inferencia_taller.py --demo             (todos los casos)
    python3 interfaz_web.py                               (interfaz grafica)
"""

import argparse
import datetime
import glob
import json
import os
import sys

DIRECTORIO_BASE = os.path.dirname(os.path.abspath(__file__))
RUTA_BASE_CONOCIMIENTO = os.path.join(DIRECTORIO_BASE, "base_conocimiento.json")
DIRECTORIO_CASOS = os.path.join(DIRECTORIO_BASE, "casos")
DIRECTORIO_SALIDAS = os.path.join(DIRECTORIO_BASE, "salidas")
CODIFICACION_ARCHIVO = "utf-8"


# ============================================================================
# CARGA Y VALIDACION DE LA BASE DE CONOCIMIENTO (JSON)
# ============================================================================

def reglas_desde_datos(datos):
    """
    Valida y normaliza una base de conocimiento ya leida como JSON.

    Formato: lista de objetos con las claves:
        nombre        (str, obligatorio)
        antecedentes  (list[str], obligatorio)
        consecuentes  (list[str], obligatorio)
        prioridad     (int, opcional, por defecto 0)
        recomendacion (str, opcional, por defecto "")
    """
    if not isinstance(datos, list):
        raise ValueError("El JSON raiz debe ser una lista de reglas")

    reglas = []
    for num, item in enumerate(datos, start=1):
        if not isinstance(item, dict):
            raise ValueError("La regla #%d no es un objeto JSON" % num)

        try:
            prioridad = int(item.get("prioridad", 0) or 0)
        except (TypeError, ValueError):
            raise ValueError("La regla #%d tiene una prioridad que no es un entero" % num)

        regla = {
            "nombre": item.get("nombre", ""),
            "antecedentes": item.get("antecedentes", []) or [],
            "consecuentes": item.get("consecuentes", []) or [],
            "prioridad": prioridad,
            "recomendacion": item.get("recomendacion", "") or "",
        }

        for campo in ("antecedentes", "consecuentes"):
            if not isinstance(regla[campo], list) or not all(isinstance(h, str) for h in regla[campo]):
                raise ValueError("La regla #%d debe usar listas de texto en '%s'" % (num, campo))

        _validar_regla(regla, num)
        reglas.append(regla)

    if not reglas:
        raise ValueError("La base de conocimiento no tiene reglas")
    return reglas


def cargar_base_conocimiento(ruta_archivo, codificacion=CODIFICACION_ARCHIVO):
    """Carga la base de conocimiento desde un archivo JSON."""
    with open(ruta_archivo, "r", encoding=codificacion) as archivo:
        datos = json.load(archivo)
    return reglas_desde_datos(datos)


def _validar_regla(regla, num_regla):
    faltantes = [campo for campo in ("nombre", "antecedentes", "consecuentes") if not regla.get(campo)]
    if faltantes:
        raise ValueError(
            "Regla incompleta (#%d), faltan: %s" % (num_regla, ", ".join(faltantes))
        )


# ============================================================================
# HECHOS: VOCABULARIO, CARGA Y VALIDACION
# ============================================================================

def obtener_hechos_entrada(reglas):
    """Devuelve los hechos que solo aparecen como antecedentes (sintomas)."""
    antecedentes_totales = set()
    consecuentes_totales = set()
    for regla in reglas:
        antecedentes_totales.update(regla["antecedentes"])
        consecuentes_totales.update(regla["consecuentes"])
    return sorted(antecedentes_totales - consecuentes_totales)


def obtener_vocabulario(reglas):
    """Todos los hechos que la base de conocimiento conoce."""
    vocabulario = set()
    for regla in reglas:
        vocabulario.update(regla["antecedentes"])
        vocabulario.update(regla["consecuentes"])
    return vocabulario


def hechos_desde_datos(datos):
    """
    Convierte el contenido de un archivo de caso en una lista de hechos.

    Formatos aceptados:
        {"latencia_alta": true, "perdida_paquetes": false, "_descripcion": "..."}
        ["latencia_alta", "perdida_paquetes"]
    Las claves que empiezan por "_" son metadatos y se ignoran.
    """
    if isinstance(datos, dict):
        hechos = []
        for hecho, valor in datos.items():
            if hecho.startswith("_"):
                continue
            if not isinstance(valor, bool):
                raise ValueError("El valor del hecho '%s' debe ser true o false" % hecho)
            if valor:
                hechos.append(hecho)
        return hechos
    if isinstance(datos, list):
        if not all(isinstance(h, str) for h in datos):
            raise ValueError("La lista de hechos solo puede contener texto")
        return list(datos)
    raise ValueError("El archivo de hechos debe ser un objeto o una lista JSON")


def cargar_hechos(ruta_archivo, codificacion=CODIFICACION_ARCHIVO):
    with open(ruta_archivo, "r", encoding=codificacion) as archivo:
        return hechos_desde_datos(json.load(archivo))


def validar_hechos(hechos, reglas):
    """Separa los hechos conocidos por la BC de los que no existen en ella."""
    vocabulario = obtener_vocabulario(reglas)
    validos, desconocidos = [], []
    for hecho in hechos:
        destino = validos if hecho in vocabulario else desconocidos
        if hecho not in destino:
            destino.append(hecho)
    return validos, desconocidos


def ingresar_hechos_interactivo(reglas):
    hechos_sintoma = obtener_hechos_entrada(reglas)
    print("\nResponda de acuerdo con lo que observa en el equipo o en la red.")
    print("Escriba 's' para si, 'n' para no.\n")

    hechos_iniciales = []
    for hecho in hechos_sintoma:
        pregunta = hecho.replace("_", " ")
        while True:
            respuesta = input(" - %s? (s/n): " % pregunta).strip().lower()
            if respuesta in ("s", "si", "sí"):
                hechos_iniciales.append(hecho)
                break
            if respuesta in ("n", "no"):
                break
            print("   Por favor responda 's' o 'n'.")
    return hechos_iniciales


# ============================================================================
# MOTOR DE INFERENCIA (encadenamiento hacia adelante)
# ============================================================================

def inferir(hechos_iniciales, reglas):
    """
    Ejecuta el ciclo reconocer-resolver-actuar hasta que no haya reglas aplicables.

    Devuelve (hechos_finales, pasos). Cada paso describe una iteracion:
        iteracion, conflicto, criterio, descartes, regla, nuevos_hechos, hechos
    El ultimo paso tiene regla=None (conjunto de conflicto vacio).
    """
    hechos = set(hechos_iniciales)
    orden_llegada = {hecho: 0 for hecho in hechos}
    reglas_disparadas = set()
    pasos = []
    iteracion = 0

    while True:
        iteracion += 1

        # 1. Reconocer: reglas cuyo antecedente esta completo y que no se han disparado.
        conjunto_conflicto = [
            (indice, regla)
            for indice, regla in enumerate(reglas)
            if indice not in reglas_disparadas and set(regla["antecedentes"]).issubset(hechos)
        ]

        descripcion_conflicto = [
            {
                "nombre": regla["nombre"],
                "prioridad": regla["prioridad"],
                "especificidad": len(regla["antecedentes"]),
                "recencia": _recencia(regla, orden_llegada),
                "detalle_consecuente": len(regla["consecuentes"]),
                "posicion": indice + 1,
            }
            for indice, regla in conjunto_conflicto
        ]

        if not conjunto_conflicto:
            pasos.append({
                "iteracion": iteracion,
                "conflicto": [],
                "criterio": None,
                "descartes": [],
                "regla": None,
                "nuevos_hechos": [],
                "hechos": sorted(hechos),
            })
            break

        # 2. Resolver el conflicto.
        indice_sel, regla_sel, criterio, descartes = _resolver_conflicto(conjunto_conflicto, orden_llegada)
        reglas_disparadas.add(indice_sel)

        # 3. Actuar: agregar los consecuentes a la memoria de trabajo.
        nuevos_hechos = []
        for consecuente in regla_sel["consecuentes"]:
            if consecuente not in hechos:
                hechos.add(consecuente)
                orden_llegada[consecuente] = iteracion
                nuevos_hechos.append(consecuente)

        pasos.append({
            "iteracion": iteracion,
            "conflicto": descripcion_conflicto,
            "criterio": criterio,
            "descartes": descartes,
            "regla": {
                "nombre": regla_sel["nombre"],
                "antecedentes": list(regla_sel["antecedentes"]),
                "consecuentes": list(regla_sel["consecuentes"]),
                "prioridad": regla_sel["prioridad"],
                "recomendacion": regla_sel["recomendacion"],
            },
            "nuevos_hechos": nuevos_hechos,
            "hechos": sorted(hechos),
        })

    return hechos, pasos


def _recencia(regla, orden_llegada):
    """Iteracion en la que llego el hecho mas reciente del antecedente (0 = dato inicial)."""
    return max(orden_llegada.get(a, 0) for a in regla["antecedentes"])


def _resolver_conflicto(conjunto_conflicto, orden_llegada):
    """
    Estrategia de resolucion de conflictos (se aplica en cascada; cada criterio
    conserva solo las reglas con el mayor valor y se detiene al quedar una):

        0. Refraccion      : una regla ya disparada no vuelve a entrar al conjunto.
        1. Prioridad       : valor definido por el experto en la base de conocimiento.
        2. Especificidad   : mas antecedentes = regla mas especifica.
        3. Recencia        : usa el dato mas reciente en la memoria de trabajo.
        4. Detalle         : mas consecuentes = conclusion mas informativa.
        5. Orden en la BC  : desempate determinista (la regla que aparece primero).

    Devuelve (indice, regla, criterio_decisivo, descartes).
    """
    criterios = [
        ("prioridad", lambda i, r: r["prioridad"], lambda v: v),
        ("especificidad", lambda i, r: len(r["antecedentes"]), lambda v: v),
        ("recencia", lambda i, r: _recencia(r, orden_llegada), lambda v: v),
        ("detalle_consecuente", lambda i, r: len(r["consecuentes"]), lambda v: v),
        ("orden_en_base_conocimiento", lambda i, r: -i, lambda v: 1 - v),
    ]

    candidatas = list(conjunto_conflicto)
    criterio_decisivo = "conjunto_de_conflicto_unitario"
    descartes = []

    for nombre_criterio, valor, mostrar in criterios:
        if len(candidatas) == 1:
            break
        valores = [(i, r, valor(i, r)) for i, r in candidatas]
        maximo = max(v for _, _, v in valores)
        candidatas = [(i, r) for i, r, v in valores if v == maximo]
        criterio_decisivo = nombre_criterio
        descartes.append({
            "criterio": nombre_criterio,
            "valores": [{"regla": r["nombre"], "valor": mostrar(v)} for _, r, v in valores],
            "quedan": [r["nombre"] for _, r in candidatas],
        })

    indice, regla = candidatas[0]
    return indice, regla, criterio_decisivo, descartes


def motor_inferencia_avanzado(hechos_iniciales, reglas, imprimir=True, pausar=False):
    """Envoltorio de compatibilidad: ejecuta la inferencia e imprime la traza."""
    hechos, pasos = inferir(hechos_iniciales, reglas)
    if imprimir:
        for paso in pasos:
            imprimir_paso(paso)
            if pausar and paso["regla"] is not None:
                _esperar_enter()
    return hechos, pasos


# ============================================================================
# SALIDA: CONSOLA, RECOMENDACIONES Y REPORTE
# ============================================================================

def _esperar_enter():
    try:
        input("     [Enter para el siguiente paso] ")
    except EOFError:
        pass


def imprimir_paso(paso):
    if paso["regla"] is None:
        print("\n[Iteracion %d] Sin reglas aplicables. Fin de la inferencia." % paso["iteracion"])
        return

    print("\n[Iteracion %d] Conjunto de conflicto (%d):" % (paso["iteracion"], len(paso["conflicto"])))
    for c in paso["conflicto"]:
        print("   - %s  (prioridad=%d, antecedentes=%d, recencia=%d)"
              % (c["nombre"], c["prioridad"], c["especificidad"], c["recencia"]))
    for d in paso["descartes"]:
        print("     criterio '%s' -> quedan: %s" % (d["criterio"], ", ".join(d["quedan"])))

    regla = paso["regla"]
    print("  -> Regla disparada: %s (criterio: %s)" % (regla["nombre"], paso["criterio"]))
    print("     SI %s ENTONCES %s" % (" Y ".join(regla["antecedentes"]), " Y ".join(regla["consecuentes"])))
    if paso["nuevos_hechos"]:
        print("     Hechos nuevos: %s" % ", ".join(paso["nuevos_hechos"]))
    else:
        print("     (sin hechos nuevos)")


def obtener_recomendaciones(pasos):
    """
    Recomendaciones de las reglas que se dispararon, de mayor a menor prioridad
    (a igual prioridad, en el orden en que se obtuvieron).
    """
    recomendaciones = [
        {
            "diagnostico": paso["regla"]["nombre"],
            "recomendacion": paso["regla"]["recomendacion"],
            "prioridad": paso["regla"]["prioridad"],
            "iteracion": paso["iteracion"],
        }
        for paso in pasos
        if paso["regla"] is not None and paso["regla"]["recomendacion"]
    ]
    return sorted(recomendaciones, key=lambda r: (-r["prioridad"], r["iteracion"]))


def texto_reporte(hechos_iniciales, hechos_finales, pasos, desconocidos=None):
    """Genera el reporte de diagnostico como texto."""
    lineas = []
    lineas.append("REPORTE DE DIAGNOSTICO AUTOMATICO")
    lineas.append("Sistema experto de fallas en redes y equipos informaticos")
    lineas.append("Fecha de ejecucion: %s" % datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))
    lineas.append("=" * 72)
    lineas.append("")

    lineas.append("1. HECHOS INGRESADOS (MEMORIA DE TRABAJO INICIAL)")
    if hechos_iniciales:
        for hecho in sorted(hechos_iniciales):
            lineas.append("   - %s" % hecho.replace("_", " "))
    else:
        lineas.append("   (no se reporto ningun sintoma)")
    if desconocidos:
        lineas.append("   Hechos ignorados por no existir en la base de conocimiento: %s"
                      % ", ".join(desconocidos))
    lineas.append("")

    lineas.append("2. TRAZA DE EJECUCION DEL MOTOR DE INFERENCIA")
    for paso in pasos:
        if paso["regla"] is None:
            lineas.append("")
            lineas.append("Iteracion %d - sin reglas aplicables. Fin de la inferencia." % paso["iteracion"])
            continue
        lineas.append("")
        lineas.append("Iteracion %d - conjunto de conflicto: %s"
                      % (paso["iteracion"], ", ".join(c["nombre"] for c in paso["conflicto"])))
        for d in paso["descartes"]:
            lineas.append("   Criterio '%s' -> quedan: %s" % (d["criterio"], ", ".join(d["quedan"])))
        lineas.append("   Regla disparada: %s (criterio de seleccion: %s)"
                      % (paso["regla"]["nombre"], paso["criterio"]))
        if paso["nuevos_hechos"]:
            lineas.append("   Nuevos hechos agregados: %s" % ", ".join(paso["nuevos_hechos"]))
        else:
            lineas.append("   No se agregaron hechos nuevos (ya existian)")
    lineas.append("")

    lineas.append("3. DIAGNOSTICOS Y RECOMENDACIONES (DE MAYOR A MENOR PRIORIDAD)")
    recomendaciones = obtener_recomendaciones(pasos)
    if recomendaciones:
        for posicion, rec in enumerate(recomendaciones, start=1):
            lineas.append("")
            lineas.append("   %d. Diagnostico: %s (prioridad %d)" % (posicion, rec["diagnostico"], rec["prioridad"]))
            lineas.append("      Recomendacion: %s" % rec["recomendacion"])
    else:
        lineas.append("")
        lineas.append("   No se alcanzo ningun diagnostico final con la informacion suministrada.")
        lineas.append("   Se recomienda ingresar mas sintomas o consultar a un tecnico.")
    lineas.append("")
    lineas.append("=" * 72)
    return "\n".join(lineas) + "\n"


def generar_reporte(hechos_iniciales, hechos_finales, pasos, ruta_salida, desconocidos=None):
    carpeta = os.path.dirname(os.path.abspath(ruta_salida))
    os.makedirs(carpeta, exist_ok=True)
    with open(ruta_salida, "w", encoding="utf-8") as reporte:
        reporte.write(texto_reporte(hechos_iniciales, hechos_finales, pasos, desconocidos))


def imprimir_recomendaciones(pasos):
    recomendaciones = obtener_recomendaciones(pasos)
    print("\n" + "=" * 72)
    print("RECOMENDACION DEL SISTEMA EXPERTO")
    print("=" * 72)
    if not recomendaciones:
        print("No se alcanzo ningun diagnostico con la informacion suministrada.")
        print("Ingrese mas sintomas o consulte a un tecnico.")
        return
    for posicion, rec in enumerate(recomendaciones, start=1):
        print("\n%d. %s (prioridad %d)" % (posicion, rec["diagnostico"], rec["prioridad"]))
        print("   %s" % rec["recomendacion"])


# ============================================================================
# EJECUCION DESDE CONSOLA
# ============================================================================

def ejecutar_caso(reglas, hechos, nombre_reporte, carpeta_salida, pausar=False):
    """Valida los hechos, corre la inferencia, muestra todo y guarda el reporte."""
    validos, desconocidos = validar_hechos(hechos, reglas)
    if desconocidos:
        print("AVISO: hechos ignorados por no existir en la base de conocimiento: %s"
              % ", ".join(desconocidos))

    hechos_finales, pasos = motor_inferencia_avanzado(validos, reglas, pausar=pausar)
    imprimir_recomendaciones(pasos)

    ruta = os.path.join(carpeta_salida, nombre_reporte)
    generar_reporte(validos, hechos_finales, pasos, ruta, desconocidos)
    print("\nHechos deducidos en total: %d" % len(hechos_finales))
    print("Reporte generado en: %s" % ruta)
    return hechos_finales, pasos


def ejecutar_demo(reglas, carpeta_casos, carpeta_salida, pausar=False):
    rutas = sorted(glob.glob(os.path.join(carpeta_casos, "*.json")))
    if not rutas:
        print("No hay casos .json en '%s'." % carpeta_casos)
        return
    for ruta in rutas:
        nombre = os.path.splitext(os.path.basename(ruta))[0]
        with open(ruta, "r", encoding="utf-8") as f:
            datos = json.load(f)
        descripcion = datos.get("_descripcion", "") if isinstance(datos, dict) else ""
        hechos = hechos_desde_datos(datos)
        print("\n" + "#" * 72)
        print("%s%s" % (nombre, " - " + descripcion if descripcion else ""))
        print("Hechos iniciales: %s" % (", ".join(hechos) or "(ninguno)"))
        ejecutar_caso(reglas, hechos, "reporte_%s.txt" % nombre, carpeta_salida, pausar)


def main(argumentos=None):
    parser = argparse.ArgumentParser(description="Sistema experto de diagnostico de fallas en redes.")
    parser.add_argument("--kb", default=RUTA_BASE_CONOCIMIENTO, help="archivo JSON de la base de conocimiento")
    parser.add_argument("--caso", help="archivo JSON con los hechos iniciales")
    parser.add_argument("--demo", action="store_true", help="ejecuta todos los casos de la carpeta casos/")
    parser.add_argument("--paso-a-paso", action="store_true", help="espera Enter entre cada paso de la inferencia")
    parser.add_argument("--salida", default=DIRECTORIO_SALIDAS, help="carpeta donde se guardan los reportes")
    args = parser.parse_args(argumentos)

    print("=" * 72)
    print("SISTEMA EXPERTO - DIAGNOSTICO DE FALLAS EN REDES Y EQUIPOS INFORMATICOS")
    print("=" * 72)

    try:
        reglas = cargar_base_conocimiento(args.kb)
    except (OSError, ValueError) as error:
        print("No se pudo cargar la base de conocimiento '%s': %s" % (args.kb, error))
        return 1
    print("\nBase de conocimiento cargada: %d reglas desde '%s'" % (len(reglas), os.path.basename(args.kb)))

    if args.demo:
        ejecutar_demo(reglas, DIRECTORIO_CASOS, args.salida, args.paso_a_paso)
        return 0

    if args.caso:
        try:
            hechos = cargar_hechos(args.caso)
        except (OSError, ValueError) as error:
            print("No se pudo cargar el caso '%s': %s" % (args.caso, error))
            return 1
        print("Hechos cargados desde '%s': %s" % (args.caso, ", ".join(hechos) or "(ninguno)"))
        nombre = "reporte_%s.txt" % os.path.splitext(os.path.basename(args.caso))[0]
    else:
        hechos = ingresar_hechos_interactivo(reglas)
        nombre = "reporte_diagnostico.txt"

    ejecutar_caso(reglas, hechos, nombre, args.salida, args.paso_a_paso)
    return 0


if __name__ == "__main__":
    sys.exit(main())
