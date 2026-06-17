# Martin A. Volpi - Lateral Goniometry

Este repositorio contiene scripts en Python para realizar análisis de goniometría lateral de la extremidad posterior a partir de archivos `.csv` exportados desde DeepLabCut.

El objetivo es analizar videos de locomoción en vista lateral y calcular los ángulos articulares de cadera, rodilla, tobillo y pie durante el ciclo de marcha.

El análisis está diseñado para estudios de locomoción en ratones usando puntos anatómicos de la extremidad posterior visible en vista lateral.

---

## Estructura del repositorio

El análisis se divide en dos etapas:

1. `lateral_goniometry.py`
   Procesa los archivos `.csv` de DeepLabCut y genera resultados angulares por video.

2. `group_longitudinal_goniometry.py`
   Usa los archivos `*_video_summary.csv` generados por `lateral_goniometry.py` y construye la tabla final por animal, grupo y estadio.

---

## Etapa 1: lateral_goniometry.py

Este script realiza el análisis angular desde los archivos `.csv` de DeepLabCut.

### Qué hace

`lateral_goniometry.py` permite:

1. Leer archivos `.csv` filtrados de DeepLabCut.
2. Extraer coordenadas `x`, `y` y `likelihood`.
3. Filtrar puntos con baja confianza usando `PCUTOFF`.
4. Interpolar coordenadas faltantes o de baja confianza.
5. Suavizar las coordenadas.
6. Calcular ángulos articulares frame a frame.
7. Detectar ciclos de marcha usando el movimiento vertical del `toe`.
8. Normalizar cada ciclo de marcha de 0 a 100%.
9. Calcular el rango angular de cada ciclo como `ángulo máximo - ángulo mínimo`.
10. Promediar los rangos angulares de los ciclos válidos del video.
11. Exportar tablas `.csv` y gráficos `.png`.

---

## Puntos anatómicos requeridos

El archivo de DeepLabCut debe contener los siguientes puntos anatómicos:

* `crest`
* `hip`
* `knee`
* `ankle`
* `foot`
* `toe`

El orden anatómico esperado es:

`crest → hip → knee → ankle → foot → toe`

---

## Ángulos calculados

El script calcula los siguientes ángulos:

| Articulación | Puntos usados         |
| ------------ | --------------------- |
| Cadera       | `crest - hip - knee`  |
| Rodilla      | `hip - knee - ankle`  |
| Tobillo      | `knee - ankle - foot` |
| Pie          | `ankle - foot - toe`  |

Cada ángulo se calcula frame a frame usando las coordenadas `x` e `y` de tres puntos anatómicos consecutivos.

---

## Escala pixel/cm

No se necesita escala pixel/cm para este análisis.

Los ángulos se calculan en grados a partir de la posición relativa entre puntos anatómicos. La escala espacial solo sería necesaria para variables como distancia, velocidad, desplazamiento corporal o altura del dedo en centímetros.

---

## Requisitos

El análisis requiere Python 3 y las siguientes librerías:

* `pandas`
* `numpy`
* `scipy`
* `matplotlib`

Instalación:

`pip install pandas numpy scipy matplotlib`

---

## Uso de lateral_goniometry.py

Abrir el archivo:

`lateral_goniometry.py`

Modificar las rutas al inicio del script:

`INPUT_PATH = r"ruta/al/archivo_o_carpeta"`

`OUTPUT_DIR = r"ruta/a/la/carpeta_de_resultados"`

Luego ejecutar:

`python lateral_goniometry.py`

---

## Análisis de un solo archivo

Para analizar un único archivo `.csv`, colocar en `INPUT_PATH` la ruta completa del archivo:

`INPUT_PATH = r"C:\Users\Usuario\Desktop\raton1_P30_filtered.csv"`

`OUTPUT_DIR = r"C:\Users\Usuario\Desktop\resultados_angulos"`

---

## Análisis de una carpeta completa

Para analizar varios archivos `.csv`, colocar en `INPUT_PATH` la ruta de la carpeta que contiene los archivos:

`INPUT_PATH = r"C:\Users\Usuario\Desktop\csvs_DLC"`

`OUTPUT_DIR = r"C:\Users\Usuario\Desktop\resultados_angulos"`

El script buscará automáticamente archivos `.csv` dentro de esa carpeta.

---

## Parámetros principales de lateral_goniometry.py

| Parámetro            | Función                                            |
| -------------------- | -------------------------------------------------- |
| `FPS`                | Fotogramas por segundo del video                   |
| `PCUTOFF`            | Umbral mínimo de confianza de DeepLabCut           |
| `SMOOTH_WINDOW`      | Ventana de suavizado temporal                      |
| `N_POINTS_PER_CYCLE` | Número de puntos usados para normalizar cada ciclo |

Valores por defecto:

| Parámetro            | Valor  |
| -------------------- | ------ |
| `FPS`                | `30`   |
| `PCUTOFF`            | `0.80` |
| `SMOOTH_WINDOW`      | `10`   |
| `N_POINTS_PER_CYCLE` | `51`   |

---

## Archivos de salida de lateral_goniometry.py

Por cada video analizado, el script genera:

| Archivo                      | Contenido                                |
| ---------------------------- | ---------------------------------------- |
| `*_frame_angles.csv`         | Ángulos articulares frame a frame        |
| `*_cycle_angle_profiles.csv` | Perfiles angulares por ciclo normalizado |
| `*_ranges_by_cycle.csv`      | Rango angular de cada ciclo              |
| `*_video_summary.csv`        | Promedio del rango angular del video     |
| `*_cycle_detection_QC.png`   | Control visual de detección de ciclos    |
| `*_hip_angle_profile.png`    | Perfil angular de cadera                 |
| `*_knee_angle_profile.png`   | Perfil angular de rodilla                |
| `*_ankle_angle_profile.png`  | Perfil angular de tobillo                |
| `*_foot_angle_profile.png`   | Perfil angular de pie                    |

El archivo más importante para el análisis grupal es:

`*_video_summary.csv`

---

## Etapa 2: group_longitudinal_goniometry.py

Este script realiza el análisis grupal y longitudinal usando los resultados generados por `lateral_goniometry.py`.

Este script no lee archivos originales de DeepLabCut, no recalcula ángulos y no detecta ciclos. Solo usa los archivos `*_video_summary.csv`.

### Qué hace

`group_longitudinal_goniometry.py` permite:

1. Leer todos los archivos `*_video_summary.csv`.
2. Crear una plantilla de metadata si no existe.
3. Unir cada video con su animal, grupo y estadio.
4. Promediar videos repetidos dentro de cada animal y estadio.
5. Generar una tabla final animal × estadio.
6. Exportar tablas por articulación.
7. Calcular cambios entre estadio basal y final.
8. Generar gráficos longitudinales por articulación.

---

## Metadata

El segundo script necesita un archivo llamado:

`metadata_goniometry.csv`

Este archivo debe contener las siguientes columnas:

| Columna        | Descripción                               |
| -------------- | ----------------------------------------- |
| `summary_file` | Nombre del archivo `*_video_summary.csv`  |
| `file`         | Nombre del archivo original de DeepLabCut |
| `animal`       | Identificador del animal                  |
| `group`        | Grupo experimental                        |
| `stage`        | Estadio o edad                            |

Ejemplo:

| summary_file                 | file                    | animal | group | stage |
| ---------------------------- | ----------------------- | ------ | ----- | ----- |
| raton1_P30_video_summary.csv | raton1_P30_filtered.csv | WT01   | WT    | P30   |
| raton1_P37_video_summary.csv | raton1_P37_filtered.csv | WT01   | WT    | P37   |
| raton6_P30_video_summary.csv | raton6_P30_filtered.csv | SOD01  | SOD1  | P30   |
| raton6_P37_video_summary.csv | raton6_P37_filtered.csv | SOD01  | SOD1  | P37   |

Los nombres de grupo deben coincidir con `GROUP_ORDER` dentro del script.

Recomendación:

`GROUP_ORDER = ["WT", "SOD1"]`

---

## Estadios analizados

Por defecto, el script considera los siguientes estadios:

`P30, P37, P44, P51, P65, P85`

En el archivo de metadata puedes escribir los estadios como `P85`, `p85` o `85`. El script los normaliza automáticamente a `P85`.

---

## Uso de group_longitudinal_goniometry.py

Abrir el archivo:

`group_longitudinal_goniometry.py`

Modificar las rutas al inicio del script:

`SUMMARY_DIR = r"ruta/a/resultados_angulos"`

`METADATA_PATH = r"ruta/a/metadata_goniometry.csv"`

`OUTPUT_DIR = r"ruta/a/resultados_grupales"`

Luego ejecutar:

`python group_longitudinal_goniometry.py`

Si `metadata_goniometry.csv` no existe, el script creará una plantilla automáticamente. Después debes completar las columnas `animal`, `group` y `stage`, guardar el archivo y volver a ejecutar el script.

---

## Archivos de salida de group_longitudinal_goniometry.py

El segundo script genera:

| Archivo                                  | Contenido                                            |
| ---------------------------------------- | ---------------------------------------------------- |
| `merged_video_summary_with_metadata.csv` | Tabla con todos los videos unidos a la metadata      |
| `final_animal_stage_table.csv`           | Tabla final con una fila por animal, grupo y estadio |
| `final_table_hip.csv`                    | Tabla final para cadera                              |
| `final_table_knee.csv`                   | Tabla final para rodilla                             |
| `final_table_ankle.csv`                  | Tabla final para tobillo                             |
| `final_table_foot.csv`                   | Tabla final para pie                                 |
| `delta_P85_minus_P30.csv`                | Cambio entre P85 y P30                               |
| `longitudinal_hip_range.png`             | Gráfico longitudinal de cadera                       |
| `longitudinal_knee_range.png`            | Gráfico longitudinal de rodilla                      |
| `longitudinal_ankle_range.png`           | Gráfico longitudinal de tobillo                      |
| `longitudinal_foot_range.png`            | Gráfico longitudinal de pie                          |

---

## Unidad experimental

La unidad experimental debe ser el animal, no el ciclo de marcha.

Los ciclos de marcha son réplicas técnicas dentro de cada animal. Para el análisis grupal, primero se deben promediar los ciclos dentro de cada animal y estadio.

El valor final debe representar:

`un animal × un estadio`

Por lo tanto, si hay 5 animales WT y 5 animales SOD1, en cada estadio debe haber 5 valores WT y 5 valores SOD1.

---

## Análisis longitudinal

Para análisis longitudinales, cada animal debe tener un valor promedio por estadio.

Estructura final esperada:

| animal | group | stage | hip_range_deg | knee_range_deg | ankle_range_deg | foot_range_deg |
| ------ | ----- | ----- | ------------- | -------------- | --------------- | -------------- |
| WT01   | WT    | P30   | valor         | valor          | valor           | valor          |
| WT01   | WT    | P37   | valor         | valor          | valor           | valor          |
| WT01   | WT    | P44   | valor         | valor          | valor           | valor          |
| SOD01  | SOD1  | P30   | valor         | valor          | valor           | valor          |
| SOD01  | SOD1  | P37   | valor         | valor          | valor           | valor          |
| SOD01  | SOD1  | P44   | valor         | valor          | valor           | valor          |

Los gráficos longitudinales muestran animales individuales y la media del grupo por estadio.

---

## Control de calidad

Antes de usar los resultados finales, se recomienda verificar:

1. Que los puntos anatómicos estén correctamente posicionados en los videos.
2. Que los valores de `likelihood` sean adecuados.
3. El gráfico `*_cycle_detection_QC.png`.
4. El número de ciclos válidos detectados.
5. La coherencia de los perfiles angulares.
6. Algunos ángulos manualmente en frames seleccionados.

Idealmente, cada animal y estadio debería tener entre 10 y 15 ciclos válidos.

---

## Limitaciones

Este repositorio está diseñado para análisis de vista lateral.

Permite calcular:

* ángulos articulares;
* perfiles angulares;
* ciclos de marcha;
* rangos angulares;
* análisis longitudinal de rangos articulares.

No calcula variables que requieren vista ventral o calibración espacial, como:

* coordinación izquierda-derecha;
* coordinación diagonal;
* velocidad real en cm/s;
* distancia recorrida;
* desplazamiento corporal en centímetros.

---

## Consideraciones metodológicas

El análisis usa valores reales derivados de los videos procesados con DeepLabCut.

El pipeline recomendado es:

`CSV DeepLabCut → lateral_goniometry.py → *_video_summary.csv → group_longitudinal_goniometry.py → tabla animal × estadio`

---

## Autor

Martin A. Volpi
