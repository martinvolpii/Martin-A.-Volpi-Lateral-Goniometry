# Martin A. Volpi - Lateral Goniometry

Este repositorio contiene un script en Python para realizar **goniometría lateral de la extremidad posterior** a partir de archivos `.csv` exportados desde **DeepLabCut**.

El objetivo del código es analizar videos de locomoción en vista lateral y calcular los ángulos articulares de:

- cadera
- rodilla
- tobillo
- pie

El análisis está pensado para estudios de locomoción en ratones, usando puntos anatómicos de la extremidad posterior visible en vista lateral.

---

## ¿Qué hace este código?

El script permite:

1. Leer archivos `.csv` filtrados de DeepLabCut.
2. Extraer coordenadas `x`, `y` y `likelihood` de puntos anatómicos.
3. Calcular ángulos articulares frame a frame.
4. Detectar ciclos de marcha usando el movimiento vertical del dedo (`toe`).
5. Normalizar cada ciclo de marcha de 0 a 100%.
6. Calcular perfiles angulares por ciclo.
7. Calcular el rango angular por ciclo:
8. Promediar los rangos angulares de los ciclos válidos de cada video.

   rango angular = ángulo máximo - ángulo mínimo
   
9. Exportar tablas .csv con los resultados.
10. Generar gráficos de control y perfiles angulares.
    
## Puntos anatómicos requeridos

El archivo de DeepLabCut debe contener los siguientes puntos anatómicos:

- `crest`
- `hip`
- `knee`
- `ankle`
- `foot`
- `toe`

El orden anatómico esperado es:

`crest → hip → knee → ankle → foot → toe`

## Ángulos calculados

El script calcula los siguientes ángulos:

| Articulación | Puntos usados |
|---------------|--------------|
| Cadera | `crest - hip - knee` |
| Rodilla | `hip - knee - ankle` |
| Tobillo | `knee - ankle - foot` |
| Pie | `ankle - foot - toe` |

Cada ángulo se calcula frame a frame usando las coordenadas `x` e `y` de tres puntos anatómicos consecutivos.

## Cómo funciona el análisis

El flujo del análisis es:

1. Leer el archivo `.csv` filtrado de DeepLabCut.
2. Extraer coordenadas `x`, `y` y `likelihood`.
3. Filtrar puntos con baja confianza usando `PCUTOFF`.
4. Interpolar coordenadas faltantes o de baja confianza.
5. Suavizar las coordenadas.
6. Calcular ángulos articulares frame a frame.
7. Detectar ciclos de marcha usando el movimiento vertical del `toe`.
8. Normalizar cada ciclo de marcha de 0 a 100%.
9. Calcular el rango angular de cada ciclo como `ángulo máximo - ángulo mínimo`.
10. Promediar los rangos angulares de los ciclos válidos.
11. Exportar tablas `.csv` y gráficos `.png`.

## ¿Se necesita escala pixel/cm?

No se necesita escala pixel/cm para este análisis.
Los ángulos se calculan en grados a partir de la posición relativa entre puntos anatómicos. La escala espacial solo sería necesaria para variables como distancia, velocidad o desplazamiento en centímetros.

## Requisitos

El script requiere Python 3 y las siguientes librerías:

- `pandas`
- `numpy`
- `scipy`
- `matplotlib`

Instalación:

`pip install pandas numpy scipy matplotlib`

## Uso

Abrir el archivo principal:

`lateral_goniometry.py`

Modificar las rutas al inicio del script:

`INPUT_PATH = r"ruta/al/archivo_o_carpeta"`

`OUTPUT_DIR = r"ruta/a/la/carpeta_de_resultados"`

**Luego ejecutar:**

`python lateral_goniometry.py`

**Análisis de un solo archivo**

Para analizar un único archivo .csv, escribe la ruta completa del archivo:

`INPUT_PATH = r"ruta/al/archivo_o_carpeta"`

`OUTPUT_DIR = r"ruta/a/la/carpeta_de_resultados"`

**Análisis de una carpeta completa**

También puedes analizar una carpeta completa con múltiples archivos .csv.
En ese caso, coloca como `INPUT_PATH` la ruta de la carpeta:

`INPUT_PATH = r"C:\Users\Usuario\Desktop\csvs_DLC"`

`OUTPUT_DIR = r"C:\Users\Usuario\Desktop\resultados_angulos"`

El script buscará automáticamente archivos `.csv` dentro de esa carpeta.

## Parámetros principales

Los parámetros principales del script son:

*| Parámetro |*
|---|---|
|`FPS` = 30| 
|`PCUTOFF` = 0.80| 
|`SMOOTH_WINDOW` = 10|
|`N_POINTS_PER_CYCLE` = 51| 

|FPS|Corresponde a los fotogramas por segundo del video|
|PCUTOFF|Es el umbral mínimo de confianza de DeepLabCut| Si un punto tiene likelihood menor que este valor, el código lo considera de baja confianza, lo reemplaza temporalmente por NaN y luego interpola su posición.
|SMOOTH_WINDOW|Define el suavizado temporal aplicado a las coordenadas| Un valor mayor suaviza más la señal, pero puede reducir detalles rápidos del movimiento.
|N_POINTS_PER_CYCLE|Define a cuántos puntos se normaliza cada ciclo de marcha| Esto significa que cada ciclo se representa desde 0% hasta 100% usando 51 puntos.

## Archivos de salida

El script genera los siguientes archivos por cada video analizado:

| Archivo |                                                     Contenido |
|----------------------|--------------------------------------------------|
| `*_frame_angles.csv` | Ángulos articulares frame a frame |
| `*_cycle_angle_profiles.csv` | Perfiles angulares por ciclo normalizado |
| `*_ranges_by_cycle.csv` | Rango angular de cada ciclo |
| `*_video_summary.csv` | Promedio del rango angular del video |
| `*_cycle_detection_QC.png` | Control visual de detección de ciclos |
| `*_hip_angle_profile.png` | Perfil angular de cadera |
| `*_knee_angle_profile.png` | Perfil angular de rodilla |
| `*_ankle_angle_profile.png` | Perfil angular de tobillo |
| `*_foot_angle_profile.png` | Perfil angular de pie |

## Unidad experimental

La unidad experimental debe ser el animal, no el ciclo de marcha>
Los ciclos de marcha son réplicas técnicas dentro de cada animal. Para análisis grupal, primero se deben promediar los ciclos dentro de cada animal y estadio.

El valor final debe representar:

`un animal × un estadio`

## Análisis longitudinal

Para análisis longitudinales, cada animal debe tener un valor promedio por estadio.

Ejemplo de estructura final:

| animal | grupo | estadio | hip_range | knee_range | ankle_range | foot_range |
|---|---|---|---|---|---|---|
| WT01 | WT | P30 | valor | valor | valor | valor |
| WT01 | WT | P37 | valor | valor | valor | valor |
| SOD01 | SOD | P30 | valor | valor | valor | valor |
| SOD01 | SOD | P37 | valor | valor | valor | valor |

Para graficar resultados longitudinales, se recomienda mostrar los animales individuales y la media del grupo por estadio.

## Control de calidad

Se recomienda:

1. Verificar visualmente que los puntos anatómicos estén correctamente posicionados en el video|
2. Asegurar valores bajos de `likelihood`|Valores <0.80 se interpolan|
3. Visualizar el gráfico `*_cycle_detection_QC.png`|
4. Contar el número de ciclos válidos detectados|10 ciclos de marcha|
5. Verificar algunos ángulos manualmente en frames seleccionados|Se recomienda comparar algunos ángulos calculados por el script con mediciones manuales en algunos frames usando ImageJ, Fiji|

## Limitaciones

Este script está diseñado para análisis lateral|
Permite calcular ángulos articulares, perfiles angulares, ciclos de marcha y rangos articulares|
No calcula variables que requieren vista ventral o calibración espacial|

## Autor

Martin A. Volpi
