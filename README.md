# Taller Sistemas Expertos 2026-2S: diagnóstico de fallas en redes y equipos informáticos

Sistema experto basado en reglas con encadenamiento hacia adelante. La base de conocimiento se carga desde un archivo JSON externo, los hechos iniciales se ingresan por archivo, por interacción o desde la interfaz gráfica, y la inferencia se muestra paso a paso hasta entregar una recomendación.

## Integrante

- Julian David HUrtado Pineda

## Requisitos e instalación

- Python 3.8 o superior. **No hay dependencias externas**: solo se usa la biblioteca estándar.
- No hace falta instalar nada. Basta con clonar el repositorio:

```bash
git clone https://github.com/Jhurtadopi/Motor_Inferencia.git
cd Motor_Inferencia
```

## Ejecución

### Interfaz gráfica (recomendada)

```bash
python3 interfaz_web.py
```

Abre `http://127.0.0.1:8000` en el navegador (el servidor solo escucha en el propio equipo). Opciones: `--puerto 9000`, `--sin-navegador`.

1. **Base de conocimiento:** cargue un `.json` o use la base por defecto.
2. **Hechos iniciales:** marque los síntomas, elija un caso de ejemplo o cargue un caso `.json`.
3. **Inferencia:** «Siguiente paso» muestra una iteración a la vez (conjunto de conflicto, criterios de desempate, regla disparada, hechos nuevos); «Ejecutar todo» muestra todo de una vez.
4. **Recomendación:** al terminar aparecen los diagnósticos ordenados por prioridad y se puede descargar el reporte.

### Consola

```bash
python3 motor_inferencia_taller.py                          # interactivo (preguntas s/n)
python3 motor_inferencia_taller.py --caso casos/caso_2.json # hechos desde archivo
python3 motor_inferencia_taller.py --demo                   # ejecuta todos los casos de casos/
python3 motor_inferencia_taller.py --paso-a-paso            # espera Enter entre pasos
python3 motor_inferencia_taller.py --kb otra_base.json      # usa otra base de conocimiento
python3 motor_inferencia_taller.py --salida mis_reportes    # carpeta de reportes (por defecto salidas/)
```

## Formato de la base de conocimiento (`base_conocimiento.json`)

Lista de reglas; cada regla es un objeto:

```json
{
  "nombre": "Indicio de ataque de red",
  "antecedentes": ["trafico_anomalo", "intentos_conexion_externa"],
  "consecuentes": ["indicio_ataque_red"],
  "prioridad": 5,
  "recomendacion": ""
}
```

| Campo | Tipo | Obligatorio | Descripción |
|---|---|---|---|
| `nombre` | texto | sí | Nombre de la regla (se muestra en la traza). |
| `antecedentes` | lista de texto | sí | Hechos que deben estar todos en la memoria de trabajo (conjunción). |
| `consecuentes` | lista de texto | sí | Hechos que se agregan al disparar la regla. |
| `prioridad` | entero | no (0) | Mayor valor = se atiende antes en caso de conflicto. |
| `recomendacion` | texto | no | Si no está vacía, la regla es un diagnóstico final con recomendación. |

Un hecho es un identificador de texto en minúsculas con guiones bajos (por ejemplo `latencia_alta`). Los hechos que nunca son consecuente de una regla son los **síntomas** (entrada); los demás se infieren.

## Formato de los casos (`casos/*.json`)

```json
{
  "_descripcion": "Texto opcional que se muestra en la interfaz",
  "trafico_anomalo": true,
  "intentos_conexion_externa": true
}
```

También se acepta una lista simple: `["trafico_anomalo", "intentos_conexion_externa"]`. Las claves que empiezan por `_` son metadatos. Los valores deben ser `true` o `false`. Los hechos que no existen en la base de conocimiento se ignoran y se avisa.

## Estrategia de resolución de conflictos

Se aplica en cascada hasta que queda una sola regla: **refracción** (una regla se dispara una sola vez) → **prioridad** → **especificidad** → **recencia** → **detalle del consecuente** → **orden en la base de conocimiento** (desempate determinista). El detalle y los referentes están en el documento técnico.

## Estructura de carpetas

```
.
├── README.md
├── motor_inferencia_taller.py   # motor de inferencia, carga de archivos, reporte y modo consola
├── interfaz_web.py              # servidor local de la interfaz gráfica (biblioteca estándar)
├── interfaz/
│   └── index.html               # interfaz gráfica (HTML, CSS y JavaScript sin dependencias)
├── base_conocimiento.json       # base de conocimiento (27 reglas)
├── casos/                       # casos de ejemplo (hechos iniciales)
│   └── caso_1.json ... caso_5.json
├── salidas/                     # reportes generados por el sistema
└── docs/
    └── Documento_Tecnico.docx   # documento técnico (arquitectura, hechos, conflictos, uso de IA)
```
