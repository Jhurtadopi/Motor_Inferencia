# -*- coding: utf-8 -*-
"""Sistema Experto - Diagnostico de fallas en redes y equipos informaticos.

Base de conocimiento en JSON, hechos iniciales desde archivo o interactivo,
inferencia paso a paso visible en consola y reporte final en archivo.
"""

import sys
import json
import random
import datetime
import os

RUTA_BASE_CONOCIMIENTO = "base_conocimiento.json"
RUTA_REPORTE = "reporte_diagnostico.txt"
CODIFICACION_ARCHIVO = "utf-8"


# ============================================================================
# CARGA DE LA BASE DE CONOCIMIENTO (JSON)
# ============================================================================

def cargar_base_conocimiento(ruta_archivo, codificacion=CODIFICACION_ARCHIVO):
    """
    Carga la base de conocimiento desde un archivo JSON.

    Formato: lista de objetos con las claves:
        nombre        (str, obligatorio)
        antecedentes  (list[str], obligatorio)
        consecuentes  (list[str], obligatorio)
        prioridad     (int, opcional, por defecto 0)
        recomendacion (str, opcional, por defecto "")
    """
    with open(ruta_archivo, "r", encoding=codificacion) as archivo:
        datos = json.load(archivo)

    if not isinstance(datos, list):
        raise ValueError("El JSON raiz debe ser una lista de reglas")

    reglas = []
    for num, item in enumerate(datos, start=1):
        if not isinstance(item, dict):
            raise ValueError("La regla #%d no es un objeto JSON" % num)

        regla = {
            "nombre": item.get("nombre", ""),
            "antecedentes": item.get("antecedentes", []) or [],
            "consecuentes": item.get("consecuentes", []) or [],
            "prioridad": int(item.get("prioridad", 0) or 0),
            "recomendacion": item.get("recomendacion", "") or "",
        }

        if not isinstance(regla["antecedentes"], list) or not isinstance(regla["consecuentes"], list):
            raise ValueError("La regla #%d debe usar listas en antecedentes/consecuentes" % num)

        _validar_regla(regla, num)
        reglas.append(regla)

    return reglas


def _validar_regla(regla, num_regla):
    faltantes = [campo for campo in ("nombre", "antecedentes", "consecuentes") if not regla.get(campo)]
    if faltantes:
        raise ValueError(
            "Regla incompleta (#%d), faltan: %s" % (num_regla, ", ".join(faltantes))
        )


# ============================================================================
# ENTRADA DE HECHOS
# ============================================================================

def obtener_hechos_entrada(reglas):
    """Devuelve los hechos que solo aparecen como antecedentes (sintomas)."""
    antecedentes_totales = set()
    consecuentes_totales = set()
    for regla in reglas:
        antecedentes_totales.update(regla["antecedentes"])
        consecuentes_totales.update(regla["consecuentes"])
    return sorted(antecedentes_totales - consecuentes_totales)


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


def construir_hechos_desde_diccionario(datos):
    return [hecho for hecho, valor in datos.items() if valor]


# ============================================================================
# MOTOR DE INFERENCIA (encadenamiento hacia adelante)
# ============================================================================

def motor_inferencia_avanzado(hechos_iniciales, reglas):
    hechos = set(hechos_iniciales)
    orden_llegada = {hecho: 0 for hecho in hechos}
    reglas_disparadas = set()
    bitacora = []
    iteracion = 0

    while True:
        iteracion += 1
        conjunto_conflicto = []
        for indice, regla in enumerate(reglas):
            if indice in reglas_disparadas:
                continue
            if set(regla["antecedentes"]).issubset(hechos):
                conjunto_conflicto.append((indice, regla))

        bitacora.append({
            "tipo": "conflicto",
            "iteracion": iteracion,
            "reglas": [regla["nombre"] for _, regla in conjunto_conflicto],
        })

        # ----- Mostrar paso a paso en consola -----
        if conjunto_conflicto:
            print("\n[Iteracion %d] Conjunto de conflicto:" % iteracion)
            for _, r in conjunto_conflicto:
                print("   - %s" % r["nombre"])
        else:
            print("\n[Iteracion %d] Sin reglas aplicables. Fin de la inferencia." % iteracion)

        if not conjunto_conflicto:
            break

        indice_sel, regla_sel, criterio = _resolver_conflicto(conjunto_conflicto, orden_llegada)
        reglas_disparadas.add(indice_sel)

        nuevos_hechos = []
        for consecuente in regla_sel["consecuentes"]:
            if consecuente not in hechos:
                hechos.add(consecuente)
                orden_llegada[consecuente] = iteracion
                nuevos_hechos.append(consecuente)

        bitacora.append({
            "tipo": "disparo",
            "iteracion": iteracion,
            "regla": regla_sel["nombre"],
            "criterio_seleccion": criterio,
            "antecedentes": regla_sel["antecedentes"],
            "nuevos_hechos": nuevos_hechos,
            "recomendacion": regla_sel.get("recomendacion", ""),
        })

        # ----- Mostrar disparo en consola -----
        print("  -> Regla disparada: %s (criterio: %s)" % (regla_sel["nombre"], criterio))
        if nuevos_hechos:
            print("     Hechos nuevos: %s" % ", ".join(nuevos_hechos))
        else:
            print("     (sin hechos nuevos)")

    return hechos, bitacora


def _resolver_conflicto(conjunto_conflicto, orden_llegada):
    candidatas = list(conjunto_conflicto)
    criterio_decisivo = "conjunto_de_conflicto_unitario"

    criterios = [
        ("prioridad", lambda indice, regla: regla["prioridad"]),
        ("especificidad", lambda indice, regla: len(regla["antecedentes"])),
        ("recencia", lambda indice, regla: max(orden_llegada.get(a, 0) for a in regla["antecedentes"])),
        ("detalle_consecuente", lambda indice, regla: len(regla["consecuentes"])),
    ]

    for nombre_criterio, funcion_valor in criterios:
        if len(candidatas) == 1:
            break
        valor_maximo = max(funcion_valor(i, r) for i, r in candidatas)
        candidatas = [(i, r) for i, r in candidatas if funcion_valor(i, r) == valor_maximo]
        criterio_decisivo = nombre_criterio

    if len(candidatas) > 1:
        candidatas = [random.choice(candidatas)]
        criterio_decisivo = "azar"

    indice, regla = candidatas[0]
    return indice, regla, criterio_decisivo


# ============================================================================
# REPORTE
# ============================================================================

def generar_reporte(hechos_iniciales, hechos_finales, bitacora, reglas, ruta_salida=RUTA_REPORTE):
    if os.path.exists(ruta_salida):
        os.remove(ruta_salida)
    with open(ruta_salida, "w", encoding="utf-8") as reporte:
        reporte.write("REPORTE DE DIAGNOSTICO AUTOMATICO\n")
        reporte.write("Sistema experto de fallas en redes y equipos informaticos\n")
        reporte.write("Fecha de ejecucion: %s\n" % datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))
        reporte.write("=" * 72 + "\n\n")

        reporte.write("1. HECHOS INGRESADOS (MEMORIA DE TRABAJO INICIAL)\n")
        if hechos_iniciales:
            for hecho in sorted(hechos_iniciales):
                reporte.write("   - %s\n" % hecho.replace("_", " "))
        else:
            reporte.write("   (no se reporto ningun sintoma)\n")
        reporte.write("\n")

        reporte.write("2. TRAZA DE EJECUCION DEL MOTOR DE INFERENCIA\n")
        for evento in bitacora:
            if evento["tipo"] == "conflicto":
                reglas_txt = ", ".join(evento["reglas"]) if evento["reglas"] else "(ninguna regla aplicable)"
                reporte.write("\nIteracion %d - conjunto de conflicto: %s\n" % (evento["iteracion"], reglas_txt))
            else:
                reporte.write(
                    "   Regla disparada: %s (criterio de seleccion: %s)\n"
                    % (evento["regla"], evento["criterio_seleccion"])
                )
                if evento["nuevos_hechos"]:
                    reporte.write("   Nuevos hechos agregados: %s\n" % ", ".join(evento["nuevos_hechos"]))
                else:
                    reporte.write("   No se agregaron hechos nuevos (ya existian)\n")
        reporte.write("\n")

        reporte.write("3. DIAGNOSTICOS Y RECOMENDACIONES PARA APOYAR LA DECISION\n")
        diagnosticos_disparados = [
            regla for regla in reglas
            if regla.get("recomendacion") and set(regla["consecuentes"]).issubset(hechos_finales)
        ]
        if diagnosticos_disparados:
            for regla in diagnosticos_disparados:
                reporte.write("\n   Diagnostico: %s\n" % regla["nombre"])
                reporte.write("   Recomendacion: %s\n" % regla["recomendacion"])
        else:
            reporte.write("\n   No se alcanzo ningun diagnostico final con la informacion suministrada.\n")
            reporte.write("   Se recomienda ingresar mas sintomas o consultar a un tecnico.\n")
        reporte.write("\n" + "=" * 72 + "\n")


# ============================================================================
# CASOS DE EJEMPLO (para --demo)
# ============================================================================

ESCENARIOS_DEMO = {
    "1": {
        "titulo": "Caso 1 - Perdida de conectividad por IP duplicada",
        "hechos": ["ip_duplicada", "tiene_conexion_internet"],
    },
    "2": {
        "titulo": "Caso 2 - Lentitud por congestion e interferencia inalambrica",
        "hechos": ["latencia_alta", "perdida_paquetes", "senal_inalambrica_debil", "desconexiones_frecuentes"],
    },
    "3": {
        "titulo": "Caso 3 - Indicio de ataque de red",
        "hechos": ["trafico_anomalo", "intentos_conexion_externa", "latencia_alta", "perdida_paquetes"],
    },
}


def ejecutar_demo():
    reglas = cargar_base_conocimiento(RUTA_BASE_CONOCIMIENTO)
    for clave in sorted(ESCENARIOS_DEMO):
        escenario = ESCENARIOS_DEMO[clave]
        print("\n" + "#" * 72)
        print(escenario["titulo"])
        print("Hechos iniciales: %s" % ", ".join(escenario["hechos"]))

        hechos_finales, bitacora = motor_inferencia_avanzado(escenario["hechos"], reglas)
        ruta_reporte = "reporte_demo_%s.txt" % clave
        generar_reporte(escenario["hechos"], hechos_finales, bitacora, reglas, ruta_reporte)

        print("\nHechos finales inferidos: %s" % ", ".join(sorted(hechos_finales)))
        print("Reporte generado en: %s" % ruta_reporte)


# ============================================================================
# MAIN
# ============================================================================

def main():
    global RUTA_BASE_CONOCIMIENTO
    RUTA_BASE_CONOCIMIENTO = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "base_conocimiento.json"
    )

    print("=" * 72)
    print("SISTEMA EXPERTO - DIAGNOSTICO DE FALLAS EN REDES Y EQUIPOS INFORMATICOS")
    print("=" * 72)

    # Modo demo
    if len(sys.argv) > 1 and sys.argv[1] == "--demo":
        ejecutar_demo()
        return

    reglas = cargar_base_conocimiento(RUTA_BASE_CONOCIMIENTO)
    print("\nBase de conocimiento cargada: %d reglas desde '%s'\n"
          % (len(reglas), os.path.basename(RUTA_BASE_CONOCIMIENTO)))

    # Modo --caso archivo.json (hechos desde archivo externo)
    if len(sys.argv) > 2 and sys.argv[1] == "--caso":
        ruta_caso = sys.argv[2]
        with open(ruta_caso, "r", encoding="utf-8") as f:
            datos = json.load(f)
        hechos_iniciales = construir_hechos_desde_diccionario(datos)
        print("Hechos cargados desde '%s': %s\n"
              % (ruta_caso, ", ".join(hechos_iniciales)))
    else:
        # Modo interactivo
        hechos_iniciales = ingresar_hechos_interactivo(reglas)

    hechos_finales, bitacora = motor_inferencia_avanzado(hechos_iniciales, reglas)
    generar_reporte(hechos_iniciales, hechos_finales, bitacora, reglas)

    print("\n" + "=" * 72)
    print("Proceso de inferencia finalizado.")
    print("Hechos deducidos en total: %d" % len(hechos_finales))
    print("Reporte de diagnostico generado en '%s'" % RUTA_REPORTE)


if __name__ == "__main__":
    main()