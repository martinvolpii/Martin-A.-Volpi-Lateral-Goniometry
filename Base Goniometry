#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Analisis lateral de angulos tipo Fig. 8 desde CSV de DeepLabCut.

QUE HACE:
1. Lee un CSV filtrado de DeepLabCut.
2. Extrae los puntos: crest, hip, knee, ankle, foot, toe.
3. Calcula angulos frame a frame:
   - hip   = crest-hip-knee
   - knee  = hip-knee-ankle
   - ankle = knee-ankle-foot
   - foot  = ankle-foot-toe
4. Detecta ciclos de marcha usando el movimiento vertical del toe.
5. Normaliza cada ciclo a 0-100% con 51 puntos.
6. Calcula rango angular por ciclo: maximo - minimo.
7. Promedia los ciclos del video.
8. Exporta CSVs y graficos.

IMPORTANTE:
- No necesitas escala pixel/cm para angulos.
- Cada video entrega valores del video. Para estadistica final debes promediar por raton/estadio.
- Idealmente usa 10-15 ciclos validos por raton/estadio.

REQUISITOS:
pip install pandas numpy scipy matplotlib
"""

# ============================================================
# CAMBIA SOLO ESTAS LINEAS
# ============================================================

INPUT_PATH = r"C:\CAMBIA\ESTA\RUTA\raton 3DLC_resnet50_EntrenamientoMay18shuffle1_50000_filtered.csv"
OUTPUT_DIR = r"C:\CAMBIA\ESTA\RUTA\resultados_angulos"

FPS = 30
PCUTOFF = 0.80
SMOOTH_WINDOW = 10
N_POINTS_PER_CYCLE = 51

# Si tus puntos se llaman distinto en DeepLabCut, cambia el nombre de la derecha.
# La izquierda NO la cambies.
BODYPART_MAP = {
    "crest": "crest",
    "hip": "hip",
    "knee": "knee",
    "ankle": "ankle",
    "foot": "foot",
    "toe": "toe",
}

# ============================================================
# NO CAMBIAR DESDE AQUI, SALVO QUE QUIERAS MODIFICAR EL METODO
# ============================================================

from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.signal import find_peaks


JOINT_DEFINITIONS = {
    "hip":   ("crest", "hip",   "knee"),
    "knee":  ("hip",   "knee",  "ankle"),
    "ankle": ("knee",  "ankle", "foot"),
    "foot":  ("ankle", "foot",  "toe"),
}


def read_dlc_csv(csv_path):
    """
    Lee CSV de DeepLabCut con header de 3 filas:
    scorer / bodyparts / coords.
    """
    df = pd.read_csv(csv_path, header=[0, 1, 2])

    scorers = [c[0] for c in df.columns if c[0] != "scorer"]
    if len(scorers) == 0:
        raise ValueError("No pude detectar el scorer/modelo de DeepLabCut en el CSV.")

    scorer = scorers[0]
    return df, scorer


def extract_coords(df, scorer, bodypart_map, pcutoff):
    """
    Extrae x, y y likelihood.
    Los frames con likelihood bajo se reemplazan por NaN y luego se interpolan.
    """
    coords = {}
    available = set(df[scorer].columns.get_level_values(0))

    for standard_name, dlc_name in bodypart_map.items():
        if dlc_name not in available:
            raise ValueError(
                f"No encontre el punto '{dlc_name}' en el CSV.\n"
                f"Puntos disponibles: {sorted(available)}"
            )

        sub = df[scorer][dlc_name].copy()
        sub.columns = sub.columns.astype(str)

        x = pd.to_numeric(sub["x"], errors="coerce")
        y = pd.to_numeric(sub["y"], errors="coerce")
        likelihood = pd.to_numeric(sub["likelihood"], errors="coerce")

        low_confidence = likelihood < pcutoff
        x = x.mask(low_confidence)
        y = y.mask(low_confidence)

        x = x.interpolate(limit_direction="both")
        y = y.interpolate(limit_direction="both")

        coords[standard_name] = pd.DataFrame({
            "x": x,
            "y": y,
            "likelihood": likelihood,
        })

    return coords


def smooth_series(series, window):
    if window <= 1:
        return series
    return series.rolling(window=window, center=True, min_periods=1).mean()


def smooth_coords(coords, window):
    out = {}
    for bp, data in coords.items():
        smoothed = data.copy()
        smoothed["x"] = smooth_series(smoothed["x"], window)
        smoothed["y"] = smooth_series(smoothed["y"], window)
        out[bp] = smoothed
    return out


def angle_three_points(a, b, c):
    """
    Calcula el angulo ABC en grados.
    a, b y c son arrays Nx2.
    """
    v1 = a - b
    v2 = c - b

    norm1 = np.linalg.norm(v1, axis=1)
    norm2 = np.linalg.norm(v2, axis=1)
    denom = norm1 * norm2

    dot = np.sum(v1 * v2, axis=1)
    cosang = np.divide(
        dot,
        denom,
        out=np.full_like(dot, np.nan, dtype=float),
        where=denom != 0,
    )
    cosang = np.clip(cosang, -1.0, 1.0)

    return np.degrees(np.arccos(cosang))


def calculate_joint_angles(coords):
    """
    Calcula angulos frame a frame:
    hip, knee, ankle, foot.
    """
    def xy(bp):
        return coords[bp][["x", "y"]].to_numpy(dtype=float)

    angles = {}
    for joint, (p1, p2, p3) in JOINT_DEFINITIONS.items():
        angles[joint] = angle_three_points(xy(p1), xy(p2), xy(p3))

    angles_df = pd.DataFrame(angles)
    angles_df.insert(0, "frame", np.arange(len(angles_df)))
    return angles_df


def detect_cycles_from_toe(coords, fps):
    """
    Detecta ciclos usando la coordenada vertical del toe.
    En imagen, y aumenta hacia abajo. Por eso usamos -y para que toe alto sea peak.
    """
    toe_y = coords["toe"]["y"].to_numpy(dtype=float)
    toe_height = -toe_y

    toe_height = pd.Series(toe_height).rolling(
        window=5,
        center=True,
        min_periods=1
    ).mean().to_numpy()

    min_cycle_seconds = 0.18
    min_distance = max(2, int(min_cycle_seconds * fps))
    prominence = np.nanstd(toe_height) * 0.25

    peaks, _ = find_peaks(
        toe_height,
        distance=min_distance,
        prominence=prominence
    )

    # Si detecta muy pocos ciclos, intenta criterio menos estricto.
    if len(peaks) < 3:
        peaks, _ = find_peaks(toe_height, distance=min_distance)

    return peaks, toe_height


def normalize_cycles(angles_df, peaks, n_points):
    """
    Normaliza cada ciclo peak-to-peak a 0-100% con n_points.
    Devuelve tabla larga:
    cycle, percent_gait_cycle, hip, knee, ankle, foot.
    """
    all_cycles = []
    x_new = np.linspace(0, 100, n_points)

    for cycle_number, (start, end) in enumerate(zip(peaks[:-1], peaks[1:]), start=1):
        if end <= start + 2:
            continue

        x_old = np.linspace(0, 100, end - start)

        cycle_data = {
            "cycle": np.repeat(cycle_number, n_points),
            "percent_gait_cycle": x_new,
        }

        for joint in JOINT_DEFINITIONS.keys():
            y_old = angles_df[joint].iloc[start:end].to_numpy(dtype=float)
            cycle_data[joint] = np.interp(x_new, x_old, y_old)

        all_cycles.append(pd.DataFrame(cycle_data))

    if len(all_cycles) == 0:
        return pd.DataFrame(columns=["cycle", "percent_gait_cycle", *JOINT_DEFINITIONS.keys()])

    return pd.concat(all_cycles, ignore_index=True)


def summarize_ranges_by_cycle(cycles_df):
    """
    Calcula rango angular por ciclo:
    maximo - minimo.
    """
    rows = []

    for cycle_number, group in cycles_df.groupby("cycle"):
        row = {"cycle": cycle_number}
        for joint in JOINT_DEFINITIONS.keys():
            row[f"{joint}_range_deg"] = group[joint].max() - group[joint].min()
        rows.append(row)

    return pd.DataFrame(rows)


def summarize_video(per_cycle_ranges):
    """
    Promedia los rangos de todos los ciclos del video.
    Este resumen es el valor que luego deberia entrar como dato del raton/estadio.
    """
    if per_cycle_ranges.empty:
        return pd.DataFrame()

    summary = {}
    for joint in JOINT_DEFINITIONS.keys():
        col = f"{joint}_range_deg"
        summary[f"{joint}_range_mean_deg"] = per_cycle_ranges[col].mean()
        summary[f"{joint}_range_sem_deg"] = per_cycle_ranges[col].sem()

    summary["n_cycles"] = len(per_cycle_ranges)
    return pd.DataFrame([summary])


def plot_joint_profiles(cycles_df, output_dir, stem):
    """
    Grafica cada articulacion en una imagen separada:
    media ± SEM de los ciclos.
    """
    if cycles_df.empty:
        return

    for joint in JOINT_DEFINITIONS.keys():
        grouped = cycles_df.groupby("percent_gait_cycle")[joint]
        mean = grouped.mean()
        sem = grouped.sem().fillna(0)

        x = mean.index.to_numpy(dtype=float)
        y = mean.to_numpy(dtype=float)
        e = sem.to_numpy(dtype=float)

        fig, ax = plt.subplots(figsize=(6, 4))
        ax.plot(x, y, linewidth=2)
        ax.fill_between(x, y - e, y + e, alpha=0.25)
        ax.set_title(f"{joint}: perfil angular")
        ax.set_xlabel("Ciclo de marcha (%)")
        ax.set_ylabel("Angulo (grados)")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        fig.tight_layout()

        fig_path = output_dir / f"{stem}_{joint}_angle_profile.png"
        fig.savefig(fig_path, dpi=300)
        plt.close(fig)


def plot_cycle_detection(toe_height, peaks, output_dir, stem):
    """
    Grafico de control para revisar si los ciclos fueron detectados correctamente.
    """
    fig, ax = plt.subplots(figsize=(8, 3))
    ax.plot(toe_height, linewidth=1)
    ax.plot(peaks, toe_height[peaks], "o")
    ax.set_title("Control de deteccion de ciclos usando toe")
    ax.set_xlabel("Frame")
    ax.set_ylabel("Altura relativa del toe")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()

    fig_path = output_dir / f"{stem}_cycle_detection_QC.png"
    fig.savefig(fig_path, dpi=300)
    plt.close(fig)


def process_one_csv(csv_path, output_dir):
    csv_path = Path(csv_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    df, scorer = read_dlc_csv(csv_path)

    coords = extract_coords(
        df=df,
        scorer=scorer,
        bodypart_map=BODYPART_MAP,
        pcutoff=PCUTOFF,
    )

    coords = smooth_coords(coords, SMOOTH_WINDOW)

    angles_df = calculate_joint_angles(coords)
    peaks, toe_height = detect_cycles_from_toe(coords, FPS)
    cycles_df = normalize_cycles(angles_df, peaks, N_POINTS_PER_CYCLE)
    per_cycle_ranges = summarize_ranges_by_cycle(cycles_df)
    video_summary = summarize_video(per_cycle_ranges)

    stem = csv_path.stem

    # Guardar salidas
    angles_df.to_csv(output_dir / f"{stem}_frame_angles.csv", index=False)
    cycles_df.to_csv(output_dir / f"{stem}_cycle_angle_profiles.csv", index=False)
    per_cycle_ranges.to_csv(output_dir / f"{stem}_ranges_by_cycle.csv", index=False)

    if not video_summary.empty:
        video_summary.insert(0, "file", csv_path.name)
        video_summary.insert(1, "fps", FPS)
        video_summary.insert(2, "pcutoff", PCUTOFF)
        video_summary.insert(3, "smooth_window", SMOOTH_WINDOW)
        video_summary.to_csv(output_dir / f"{stem}_video_summary.csv", index=False)

    plot_joint_profiles(cycles_df, output_dir, stem)
    plot_cycle_detection(toe_height, peaks, output_dir, stem)

    print("=" * 70)
    print(f"Archivo procesado: {csv_path.name}")
    print(f"Scorer/modelo DLC detectado: {scorer}")
    print(f"Ciclos detectados: {max(0, len(peaks)-1)}")
    print(f"Carpeta de salida: {output_dir}")
    print("=" * 70)


def main():
    input_path = Path(INPUT_PATH)
    output_dir = Path(OUTPUT_DIR)

    if input_path.is_dir():
        csv_files = sorted(input_path.glob("*filtered.csv"))
        if len(csv_files) == 0:
            csv_files = sorted(input_path.glob("*.csv"))

        if len(csv_files) == 0:
            raise FileNotFoundError(f"No encontre CSVs en la carpeta: {input_path}")

        for csv_file in csv_files:
            process_one_csv(csv_file, output_dir)

    else:
        if not input_path.exists():
            raise FileNotFoundError(f"No existe el archivo: {input_path}")

        process_one_csv(input_path, output_dir)


if __name__ == "__main__":
    main()
