#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
gait_phase_.py

Analisis independiente de fases del ciclo de marcha desde CSV de DeepLabCut.

- puntos laterales: crest, hip, knee, ankle, foot, toe
- suavizado temporal de coordenadas
- deteccion de ciclos con peaks del toe
- fase swing definida cuando toe y foot se elevan respecto al suelo del ciclo
- stick diagrams con stance en gris y swing en rojo

Este script NO calcula angulos articulares y NO reemplaza a lateral_goniometry.py.
Su objetivo es calcular variables temporales/de contacto estimado:
- stance_percent
- swing_percent
- cycle_duration_s
- toe_clearance_px
- drag_fraction

Entrada:
- CSV filtrado de DeepLabCut con header de 3 filas y puntos laterales.

Salida por video:
- *_gait_phase_by_cycle.csv
- *_gait_phase_video_summary.csv
- *_normalized_stick_points.csv
- *_gait_phase_QC.png
- *_gait_phase_percentages.png
- *_toe_clearance_drag.png
- *_stick_diagram_kiehn_style.png

Opcional:
- Si entregas METADATA_PATH, genera tablas grupales animal x estadio.
"""

# ============================================================
# CAMBIA SOLO ESTAS LINEAS
# ============================================================

INPUT_PATH = r"C:\CAMBIA\ESTA\RUTA\csvs_DLC"
OUTPUT_DIR = r"C:\CAMBIA\ESTA\RUTA\resultados_gait_phase"

# Opcional. Si lo dejas vacio, solo hace analisis por video.
METADATA_PATH = r""

FPS = 30
PCUTOFF = 0.80
SMOOTH_WINDOW = 10

# Numero maximo de ciclos validos usados para resumir cada video.
N_CYCLES_TO_USE = 10

# Numero de puntos para normalizar el ciclo en el archivo de stick diagram.
N_POINTS_PER_CYCLE = 51

# Orden longitudinal/grupal si usas metadata.
STAGE_ORDER = ["P30", "P37", "P44", "P51", "P65", "P85"]
GROUP_ORDER = ["WT", "SOD1"]

# Umbral de swing en unidades normalizadas.
# En la logica Kiehn/Allodi, dentro de cada ciclo se lleva el toe al suelo = 0.
# swing = toe y foot por encima de este umbral.
SWING_HEIGHT_THRESHOLD_NORM = 0.03

# Umbral para drag_fraction.
# drag_fraction = fraccion de frames de swing donde el toe va demasiado bajo.
# Debe ser mayor que SWING_HEIGHT_THRESHOLD_NORM para no quedar siempre en cero.
DRAG_HEIGHT_THRESHOLD_NORM = 0.08

# Estimacion del suelo en pixeles para toe_clearance_px.
# En imagenes, y aumenta hacia abajo; percentiles altos de y estan cerca del suelo.
GROUND_PERCENTILE_PX = 95

# Filtro de ciclos validos.
MIN_CYCLE_DURATION_S = 0.15
MAX_CYCLE_DURATION_S = 2.00
MIN_STANCE_PERCENT = 5
MAX_STANCE_PERCENT = 95

# Si hay segmentos stance/swing de 1 frame por ruido, se eliminan.
MIN_PHASE_RUN_FRAMES = 2

# Stick diagram.
STICK_PERCENTAGES_TO_PLOT = [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
STICK_SPACING = 0.35  # usado solo para el CSV/compatibilidad
STICK_DELTA = 0.015
STICK_STANCE_DELTA_FACTOR = 0.05
STICK_VERTICAL_SCALE = 0.75

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
import re
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.signal import find_peaks


BODYPART_ORDER = ["crest", "hip", "knee", "ankle", "foot", "toe"]
TOE_INDEX = BODYPART_ORDER.index("toe")
FOOT_INDEX = BODYPART_ORDER.index("foot")
HIP_INDEX = BODYPART_ORDER.index("hip")

PHASE_METRICS = [
    "stance_percent",
    "swing_percent",
    "cycle_duration_s",
    "toe_clearance_px",
    "drag_fraction",
]


def normalize_stage_label(stage):
    text = str(stage).strip()
    if text == "" or text.lower() == "nan":
        return text
    if re.fullmatch(r"\d+", text):
        return f"P{text}"
    match = re.fullmatch(r"[pP]\s*(\d+)", text)
    if match:
        return f"P{match.group(1)}"
    return text


def natural_stage_key(stage):
    text = str(stage)
    match = re.search(r"(\d+)", text)
    if match:
        return int(match.group(1))
    return text


def ordered_unique(values, preferred_order=None):
    values = [str(v) for v in values if pd.notna(v)]
    unique_values = list(dict.fromkeys(values))
    if preferred_order:
        preferred = [v for v in preferred_order if v in unique_values]
        remaining = [v for v in unique_values if v not in preferred_order]
        remaining = sorted(remaining, key=natural_stage_key)
        return preferred + remaining
    return sorted(unique_values, key=natural_stage_key)


def read_dlc_csv(csv_path):
    """Lee un CSV de DeepLabCut con header scorer/bodyparts/coords."""
    df = pd.read_csv(csv_path, header=[0, 1, 2])
    scorers = [c[0] for c in df.columns if c[0] != "scorer"]
    scorers = list(dict.fromkeys(scorers))
    if len(scorers) == 0:
        raise ValueError("No pude detectar el scorer/modelo de DeepLabCut en el CSV.")
    return df, scorers[0]


def extract_coords(df, scorer, bodypart_map, pcutoff):
    """Extrae x, y y likelihood. Interpola puntos con likelihood bajo."""
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

        required = {"x", "y", "likelihood"}
        missing = required.difference(sub.columns)
        if missing:
            raise ValueError(
                f"El punto '{dlc_name}' no tiene columnas {sorted(missing)}."
            )

        x = pd.to_numeric(sub["x"], errors="coerce")
        y = pd.to_numeric(sub["y"], errors="coerce")
        likelihood = pd.to_numeric(sub["likelihood"], errors="coerce")

        low_confidence = likelihood < pcutoff
        x = x.mask(low_confidence).interpolate(limit_direction="both")
        y = y.mask(low_confidence).interpolate(limit_direction="both")

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


def coords_to_arrays(coords):
    """Devuelve x_raw, y_raw con columnas en BODYPART_ORDER."""
    x = []
    y = []
    for bp in BODYPART_ORDER:
        x.append(coords[bp]["x"].to_numpy(dtype=float))
        y.append(coords[bp]["y"].to_numpy(dtype=float))
    x = np.vstack(x).T
    y = np.vstack(y).T
    return x, y


def normalize_lateral_coordinates(x_raw, y_raw):
    """
    Normaliza coordenadas siguiendo la logica lateral de Kiehn/Allodi:
    - y_height: 0 cerca del suelo, 1 mas alto.
    - x_norm: reescalado por frame entre 0 y 1.
    """
    y_min = np.nanmin(y_raw)
    y_max = np.nanmax(y_raw)
    y_range = y_max - y_min
    if not np.isfinite(y_range) or y_range == 0:
        raise ValueError("No se pudo normalizar y: rango vertical igual a cero o no finito.")

    y_height = 1 - ((y_raw - y_min) / y_range)

    x_min = np.nanmin(x_raw, axis=1, keepdims=True)
    x_max = np.nanmax(x_raw, axis=1, keepdims=True)
    x_range = x_max - x_min
    x_range[x_range == 0] = np.nan
    x_norm = (x_raw - x_min) / x_range
    x_norm = pd.DataFrame(x_norm).interpolate(limit_direction="both").to_numpy(dtype=float)

    return x_norm, y_height


def robust_iqr_mean(values):
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if len(values) == 0:
        return np.nan
    if len(values) < 4:
        return float(np.mean(values))
    q1, q3 = np.percentile(values, [25, 75])
    keep = values[(values >= q1) & (values <= q3)]
    if len(keep) == 0:
        return float(np.mean(values))
    return float(np.mean(keep))


def detect_cycles_from_toe_height(toe_height, fps):
    """
    Detecta ciclos usando peaks del toe height.
    Usa una primera pasada para estimar distancia media entre peaks y una segunda
    para remover peaks espurios, inspirado en lateral.py.
    """
    toe_height = pd.Series(toe_height).rolling(
        window=5,
        center=True,
        min_periods=1,
    ).mean().to_numpy(dtype=float)

    min_cycle_seconds = 0.18
    min_distance = max(2, int(min_cycle_seconds * fps))
    prominence = max(1e-6, np.nanstd(toe_height) * 0.10)

    peaks, _ = find_peaks(
        toe_height,
        distance=min_distance,
        prominence=prominence,
    )

    if len(peaks) >= 3:
        mean_step = robust_iqr_mean(np.diff(peaks))
        if np.isfinite(mean_step) and mean_step >= 2:
            adaptive_distance = max(min_distance, int(round(mean_step * 0.60)))
            peaks2, _ = find_peaks(
                toe_height,
                distance=adaptive_distance,
                prominence=prominence,
            )
            if len(peaks2) >= 2:
                peaks = peaks2

    if len(peaks) < 3:
        peaks, _ = find_peaks(toe_height, distance=min_distance)

    return peaks, toe_height


def fill_short_runs(mask, min_len, fill_value=False):
    """Elimina bloques cortos de True en mask poniendolos en fill_value."""
    arr = np.asarray(mask, dtype=bool).copy()
    if min_len <= 1 or len(arr) == 0:
        return arr

    padded = np.concatenate([[False], arr, [False]])
    changes = np.diff(padded.astype(int))
    starts = np.where(changes == 1)[0]
    ends = np.where(changes == -1)[0]

    for start, end in zip(starts, ends):
        if (end - start) < min_len:
            arr[start:end] = fill_value

    return arr


def contiguous_runs(boolean_array):
    arr = np.asarray(boolean_array, dtype=bool)
    if len(arr) == 0:
        return []
    padded = np.concatenate([[False], arr, [False]])
    changes = np.diff(padded.astype(int))
    starts = np.where(changes == 1)[0]
    ends = np.where(changes == -1)[0]
    return list(zip(starts, ends))


def classify_phase_for_cycle(y_height, start, end):
    """
    Clasifica stance/swing dentro de un ciclo.
    Logica basada en getSwingIdx(): se lleva el minimo del toe del ciclo a suelo 0;
    swing ocurre cuando toe y foot estan sobre el umbral.
    """
    step = y_height[start:end, :].copy()
    if step.shape[0] < 3:
        return None

    ground_norm = np.nanmin(step[:, TOE_INDEX])
    toe_rel = step[:, TOE_INDEX] - ground_norm
    foot_rel = step[:, FOOT_INDEX] - ground_norm

    swing = (toe_rel >= SWING_HEIGHT_THRESHOLD_NORM) & (foot_rel >= SWING_HEIGHT_THRESHOLD_NORM)
    swing = fill_short_runs(swing, MIN_PHASE_RUN_FRAMES, fill_value=False)
    stance = ~swing

    return stance, swing, toe_rel, foot_rel, ground_norm


def phase_onset_offset_percent(swing_mask):
    swing_mask = np.asarray(swing_mask, dtype=bool)
    if not swing_mask.any():
        return np.nan, np.nan
    idx = np.where(swing_mask)[0]
    denom = max(1, len(swing_mask) - 1)
    return 100 * idx[0] / denom, 100 * idx[-1] / denom


def summarize_gait_phases_by_cycle(peaks, x_raw, y_raw, x_norm, y_height, fps):
    rows = []
    frame_phase = np.array(["unknown"] * len(y_height), dtype=object)
    frame_cycle = np.full(len(y_height), np.nan)

    for cycle_number, (start, end) in enumerate(zip(peaks[:-1], peaks[1:]), start=1):
        if end <= start + 2:
            continue

        result = classify_phase_for_cycle(y_height, start, end)
        if result is None:
            continue

        stance, swing, toe_rel, foot_rel, ground_norm = result
        cycle_len = end - start
        duration_s = cycle_len / fps

        stance_frames = int(np.sum(stance))
        swing_frames = int(np.sum(swing))
        stance_percent = 100 * stance_frames / cycle_len
        swing_percent = 100 - stance_percent
        swing_start_percent, swing_end_percent = phase_onset_offset_percent(swing)

        toe_y_raw = y_raw[start:end, TOE_INDEX]
        ground_y_px = np.nanpercentile(toe_y_raw, GROUND_PERCENTILE_PX)
        toe_clearance_px_series = ground_y_px - toe_y_raw

        if swing_frames > 0:
            toe_clearance_px = float(np.nanmax(toe_clearance_px_series[swing]))
            drag_fraction = float(np.mean(toe_rel[swing] <= DRAG_HEIGHT_THRESHOLD_NORM))
        else:
            toe_clearance_px = np.nan
            drag_fraction = np.nan

        valid = (
            np.isfinite(duration_s)
            and duration_s >= MIN_CYCLE_DURATION_S
            and duration_s <= MAX_CYCLE_DURATION_S
            and stance_percent >= MIN_STANCE_PERCENT
            and stance_percent <= MAX_STANCE_PERCENT
            and swing_frames > 0
            and stance_frames > 0
        )

        frame_slice = slice(start, end)
        frame_cycle[frame_slice] = cycle_number
        labels = np.where(swing, "swing", "stance")
        frame_phase[frame_slice] = labels

        rows.append({
            "cycle": cycle_number,
            "start_frame": int(start),
            "end_frame": int(end),
            "cycle_duration_s": duration_s,
            "stance_time_s": stance_frames / fps,
            "swing_time_s": swing_frames / fps,
            "stance_percent": stance_percent,
            "swing_percent": swing_percent,
            "swing_start_percent": swing_start_percent,
            "swing_end_percent": swing_end_percent,
            "toe_clearance_px": toe_clearance_px,
            "drag_fraction": drag_fraction,
            "ground_y_px": ground_y_px,
            "ground_norm": ground_norm,
            "valid_cycle": bool(valid),
            "used_for_summary": False,
        })

    cycles = pd.DataFrame(rows)

    if not cycles.empty:
        valid_indices = cycles.index[cycles["valid_cycle"]].tolist()
        selected_indices = valid_indices[:N_CYCLES_TO_USE]
        cycles.loc[selected_indices, "used_for_summary"] = True

    return cycles, frame_phase, frame_cycle


def summarize_video_phase(cycles_df):
    if cycles_df.empty:
        return pd.DataFrame()

    selected = cycles_df[cycles_df["used_for_summary"]].copy()
    if selected.empty:
        return pd.DataFrame()

    summary = {}
    for metric in PHASE_METRICS:
        summary[f"{metric}_mean"] = selected[metric].mean()
        summary[f"{metric}_sd"] = selected[metric].std(ddof=1)
        summary[f"{metric}_sem"] = selected[metric].sem()

    summary["n_cycles_phase"] = len(selected)
    summary["n_cycles_detected"] = len(cycles_df)
    summary["n_cycles_valid"] = int(cycles_df["valid_cycle"].sum())
    summary["swing_threshold_norm"] = SWING_HEIGHT_THRESHOLD_NORM
    summary["drag_threshold_norm"] = DRAG_HEIGHT_THRESHOLD_NORM

    return pd.DataFrame([summary])


def interpolate_vector(values, n_points):
    values = np.asarray(values, dtype=float)
    x_old = np.linspace(0, 100, len(values))
    x_new = np.linspace(0, 100, n_points)
    return np.interp(x_new, x_old, values)


def build_normalized_stick_points(x_norm, y_height, cycles_df, n_points):
    selected = cycles_df[cycles_df["used_for_summary"]].copy()
    if selected.empty:
        return pd.DataFrame()

    rows = []
    percent_axis = np.linspace(0, 100, n_points)

    for _, row in selected.iterrows():
        cycle = int(row["cycle"])
        start = int(row["start_frame"])
        end = int(row["end_frame"])

        result = classify_phase_for_cycle(y_height, start, end)
        if result is None:
            continue
        stance, swing, toe_rel, foot_rel, ground_norm = result

        hip_x = interpolate_vector(x_norm[start:end, HIP_INDEX], n_points)
        phase_numeric = interpolate_vector(swing.astype(float), n_points)

        for bp_idx, bp in enumerate(BODYPART_ORDER):
            x_interp = interpolate_vector(x_norm[start:end, bp_idx], n_points)
            y_interp = interpolate_vector(y_height[start:end, bp_idx] - ground_norm, n_points)

            x_aligned = x_interp - hip_x
            y_relative = y_interp

            for p, xa, yr, ph in zip(percent_axis, x_aligned, y_relative, phase_numeric):
                rows.append({
                    "cycle": cycle,
                    "percent_gait_cycle": p,
                    "bodypart": bp,
                    "x_aligned_norm": xa,
                    "y_relative_norm": yr,
                    "phase": "swing" if ph >= 0.5 else "stance",
                    "swing_probability_at_percent": ph,
                })

    return pd.DataFrame(rows)


def plot_qc(toe_height_smooth, peaks, frame_phase, output_dir, stem):
    frame = np.arange(len(toe_height_smooth))
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(frame, toe_height_smooth, linewidth=1.2, label="toe height normalizado")
    if len(peaks) > 0:
        ax.plot(peaks, toe_height_smooth[peaks], "o", markersize=4, label="peaks/ciclos")

    swing_mask = frame_phase == "swing"
    for start, end in contiguous_runs(swing_mask):
        ax.axvspan(start, end, color="tab:red", alpha=0.15)

    ax.set_title("QC: deteccion de ciclos y fase swing estimada")
    ax.set_xlabel("Frame")
    ax.set_ylabel("Altura normalizada del toe")
    ax.legend(loc="best")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    fig.savefig(Path(output_dir) / f"{stem}_gait_phase_QC.png", dpi=300)
    plt.close(fig)


def plot_phase_percentages(cycles_df, output_dir, stem):
    selected = cycles_df[cycles_df["used_for_summary"]].copy()
    if selected.empty:
        return

    means = [selected["stance_percent"].mean(), selected["swing_percent"].mean()]
    sds = [selected["stance_percent"].std(ddof=1), selected["swing_percent"].std(ddof=1)]

    fig, ax = plt.subplots(figsize=(5.2, 4.2))
    ax.bar(["stance", "swing"], means, yerr=sds, capsize=5, color=["tab:gray", "tab:red"])
    ax.set_ylabel("Porcentaje del ciclo (%)")
    ax.set_title(f"Fases del ciclo de marcha\nmedia ± DE, n={len(selected)} ciclos")
    ax.set_ylim(0, 100)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    fig.savefig(Path(output_dir) / f"{stem}_gait_phase_percentages.png", dpi=300)
    plt.close(fig)


def plot_toe_clearance_drag(cycles_df, output_dir, stem):
    selected = cycles_df[cycles_df["used_for_summary"]].copy()
    if selected.empty:
        return

    fig, axes = plt.subplots(1, 2, figsize=(8, 4))

    metrics = ["toe_clearance_px", "drag_fraction"]
    titles = ["Toe clearance", "Drag fraction"]
    ylabels = ["px", "fraccion de swing"]

    for ax, metric, title, ylabel in zip(axes, metrics, titles, ylabels):
        mean = selected[metric].mean()
        sd = selected[metric].std(ddof=1)
        ax.bar([metric], [mean], yerr=[sd], capsize=5, color="tab:gray")
        ax.scatter(np.zeros(len(selected)), selected[metric], color="black", s=18, alpha=0.7)
        ax.set_title(title)
        ax.set_ylabel(ylabel)
        ax.set_xticks([])
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

    fig.tight_layout()
    fig.savefig(Path(output_dir) / f"{stem}_toe_clearance_drag.png", dpi=300)
    plt.close(fig)


def plot_stick_diagram(x_norm, y_height, cycles_df, output_dir, stem):
    """
    Stick diagram continuo estilo Kiehn/Allodi.

    Esta version no dibuja solo 0,10,20...% del ciclo.
    Dibuja todos los frames de los ciclos usados, avanzando poco durante stance
    y mas durante swing, siguiendo la logica visual de makeStickFigure del repositorio original.

    Gris = stance estimado.
    Rojo = swing estimado.
    """
    selected = cycles_df[cycles_df["used_for_summary"]].copy()
    if selected.empty:
        return

    fig, ax = plt.subplots(figsize=(14, 3.2))

    step = 0.0

    for _, row in selected.iterrows():
        start_frame = int(row["start_frame"])
        end_frame = int(row["end_frame"])

        result = classify_phase_for_cycle(y_height, start_frame, end_frame)
        if result is None:
            continue

        stance, swing, toe_rel, foot_rel, ground_norm = result

        for local_idx, frame_idx in enumerate(range(start_frame, end_frame)):
            x_frame = x_norm[frame_idx, :].copy()
            y_frame = (y_height[frame_idx, :].copy() - ground_norm) * STICK_VERTICAL_SCALE

            if swing[local_idx]:
                step += STICK_DELTA
                color = "tab:red"
            else:
                step += STICK_STANCE_DELTA_FACTOR * STICK_DELTA
                color = "tab:gray"
                # En el codigo original, durante stance se tira la punta al suelo.
                y_frame = y_frame - y_frame[TOE_INDEX]

            ax.plot(
                x_frame + step,
                y_frame + 0.10,
                color=color,
                linewidth=0.35,
                alpha=0.80,
            )

    ax.set_title("Stick diagram continuo comprimido: stance gris, swing rojo")
    ax.set_aspect("equal", adjustable="datalim")
    ax.axis("off")
    fig.tight_layout()
    fig.savefig(Path(output_dir) / f"{stem}_stick_diagram_kiehn_style.png", dpi=300)
    plt.close(fig)

def process_one_csv(csv_path, output_dir):
    csv_path = Path(csv_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    df, scorer = read_dlc_csv(csv_path)
    coords = extract_coords(df, scorer, BODYPART_MAP, PCUTOFF)
    coords = smooth_coords(coords, SMOOTH_WINDOW)

    x_raw, y_raw = coords_to_arrays(coords)
    x_norm, y_height = normalize_lateral_coordinates(x_raw, y_raw)

    peaks, toe_height_smooth = detect_cycles_from_toe_height(y_height[:, TOE_INDEX], FPS)

    cycles_df, frame_phase, frame_cycle = summarize_gait_phases_by_cycle(
        peaks=peaks,
        x_raw=x_raw,
        y_raw=y_raw,
        x_norm=x_norm,
        y_height=y_height,
        fps=FPS,
    )

    video_summary = summarize_video_phase(cycles_df)
    stick_df = build_normalized_stick_points(x_norm, y_height, cycles_df, N_POINTS_PER_CYCLE)

    stem = csv_path.stem

    cycles_df.to_csv(output_dir / f"{stem}_gait_phase_by_cycle.csv", index=False)
    stick_df.to_csv(output_dir / f"{stem}_normalized_stick_points.csv", index=False)

    if not video_summary.empty:
        video_summary.insert(0, "file", csv_path.name)
        video_summary.insert(1, "animal", "NA")
        video_summary.insert(2, "group", "NA")
        video_summary.insert(3, "stage", "NA")
        video_summary.insert(4, "fps", FPS)
        video_summary.insert(5, "pcutoff", PCUTOFF)
        video_summary.insert(6, "smooth_window", SMOOTH_WINDOW)
        video_summary.to_csv(output_dir / f"{stem}_gait_phase_video_summary.csv", index=False)

    plot_qc(toe_height_smooth, peaks, frame_phase, output_dir, stem)
    plot_phase_percentages(cycles_df, output_dir, stem)
    plot_toe_clearance_drag(cycles_df, output_dir, stem)
    plot_stick_diagram(x_norm, y_height, cycles_df, output_dir, stem)

    print("=" * 70)
    print(f"Archivo procesado: {csv_path.name}")
    print(f"Scorer/modelo DLC detectado: {scorer}")
    print(f"Ciclos detectados: {max(0, len(peaks) - 1)}")
    print(f"Ciclos validos: {0 if cycles_df.empty else int(cycles_df['valid_cycle'].sum())}")
    print(f"Ciclos usados para resumen: {0 if cycles_df.empty else int(cycles_df['used_for_summary'].sum())}")
    print(f"Carpeta de salida: {output_dir}")
    print("=" * 70)


def collect_csv_files(input_path):
    input_path = Path(input_path)
    if input_path.is_dir():
        csv_files = sorted(input_path.glob("*filtered.csv"))
        if len(csv_files) == 0:
            csv_files = sorted(input_path.glob("*.csv"))
        if len(csv_files) == 0:
            raise FileNotFoundError(f"No encontre CSVs en la carpeta: {input_path}")
        return csv_files
    if not input_path.exists():
        raise FileNotFoundError(f"No existe el archivo: {input_path}")
    return [input_path]


def read_phase_summaries(output_dir):
    files = sorted(Path(output_dir).glob("*_gait_phase_video_summary.csv"))
    if len(files) == 0:
        raise FileNotFoundError(
            f"No encontre archivos *_gait_phase_video_summary.csv en {output_dir}"
        )
    tables = []
    for path in files:
        df = pd.read_csv(path)
        df.insert(0, "summary_file", path.name)
        for col in ["animal", "group", "stage"]:
            if col in df.columns:
                df = df.drop(columns=col)
        tables.append(df)
    return pd.concat(tables, ignore_index=True)


def create_metadata_template(video_table, metadata_path):
    metadata_path = Path(metadata_path)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    template = video_table[["summary_file", "file"]].copy()
    template["animal"] = ""
    template["group"] = ""
    template["stage"] = ""
    template.to_csv(metadata_path, index=False)
    print("\nSe creo una plantilla de metadata:")
    print(metadata_path)
    print("Completa animal, group y stage; luego vuelve a ejecutar el script.\n")


def run_group_analysis(output_dir, metadata_path):
    if metadata_path is None or str(metadata_path).strip() == "":
        return

    output_dir = Path(output_dir)
    metadata_path = Path(metadata_path)
    video_table = read_phase_summaries(output_dir)

    if not metadata_path.exists():
        create_metadata_template(video_table, metadata_path)
        return

    metadata = pd.read_csv(metadata_path)
    required = {"animal", "group", "stage"}
    missing = required.difference(metadata.columns)
    if missing:
        raise ValueError(
            "La metadata debe contener animal, group y stage.\n"
            f"Columnas faltantes: {sorted(missing)}"
        )

    if "summary_file" in metadata.columns:
        merged = video_table.merge(metadata, on="summary_file", how="left", suffixes=("", "_metadata"))
    elif "file" in metadata.columns:
        merged = video_table.merge(metadata, on="file", how="left", suffixes=("", "_metadata"))
    else:
        raise ValueError("La metadata debe tener summary_file o file para unir los datos.")

    if "file_metadata" in merged.columns:
        merged = merged.drop(columns=["file_metadata"])

    missing_rows = merged[
        merged["animal"].isna()
        | merged["group"].isna()
        | merged["stage"].isna()
        | (merged["animal"].astype(str).str.strip() == "")
        | (merged["group"].astype(str).str.strip() == "")
        | (merged["stage"].astype(str).str.strip() == "")
    ]
    if len(missing_rows) > 0:
        raise ValueError(
            "Hay archivos sin metadata completa.\n"
            f"{missing_rows[['summary_file', 'file']].to_string(index=False)}"
        )

    merged["animal"] = merged["animal"].astype(str)
    merged["group"] = merged["group"].astype(str)
    merged["stage"] = merged["stage"].apply(normalize_stage_label)

    mean_cols = [f"{metric}_mean" for metric in PHASE_METRICS if f"{metric}_mean" in merged.columns]
    if len(mean_cols) == 0:
        raise ValueError("No encontre columnas *_mean de variables de fase.")

    final_table = merged.groupby(["animal", "group", "stage"], as_index=False)[mean_cols].mean()
    final_table = final_table.rename(columns={f"{metric}_mean": metric for metric in PHASE_METRICS})

    stage_rank = {stage: i for i, stage in enumerate(STAGE_ORDER)}
    group_rank = {group: i for i, group in enumerate(GROUP_ORDER)}
    final_table["_group_rank"] = final_table["group"].map(group_rank).fillna(999)
    final_table["_stage_rank"] = final_table["stage"].map(stage_rank)
    fallback_stage_rank = final_table["stage"].apply(natural_stage_key)
    final_table["_stage_rank"] = final_table["_stage_rank"].where(final_table["_stage_rank"].notna(), fallback_stage_rank)
    final_table = final_table.sort_values(["_group_rank", "animal", "_stage_rank"])
    final_table = final_table.drop(columns=["_group_rank", "_stage_rank"])

    merged.to_csv(output_dir / "gait_phase_merged_video_summary_with_metadata.csv", index=False)
    final_table.to_csv(output_dir / "gait_phase_final_animal_stage_table.csv", index=False)

    for metric in PHASE_METRICS:
        if metric not in final_table.columns:
            continue
        final_table[["animal", "group", "stage", metric]].to_csv(
            output_dir / f"final_table_{metric}.csv",
            index=False,
        )
        plot_group_metric(final_table, metric, output_dir)

    print("=" * 70)
    print("Analisis grupal de fases completado")
    print(f"Animales detectados: {final_table['animal'].nunique()}")
    print(f"Grupos detectados: {', '.join(ordered_unique(final_table['group'], GROUP_ORDER))}")
    print(f"Estadios detectados: {', '.join(ordered_unique(final_table['stage'], STAGE_ORDER))}")
    print("=" * 70)


def plot_group_metric(final_table, metric, output_dir):
    stages = ordered_unique(final_table["stage"], STAGE_ORDER)
    groups = ordered_unique(final_table["group"], GROUP_ORDER)
    stage_to_x = {stage: i for i, stage in enumerate(stages)}

    fig, ax = plt.subplots(figsize=(7, 4.5))

    for group in groups:
        group_data = final_table[final_table["group"] == group]

        for animal, animal_data in group_data.groupby("animal"):
            animal_data = animal_data.copy()
            animal_data["x"] = animal_data["stage"].map(stage_to_x)
            animal_data = animal_data.sort_values("x")
            ax.plot(animal_data["x"], animal_data[metric], marker="o", linewidth=1, alpha=0.35)

        summary = group_data.groupby("stage")[metric].agg(["mean", "std"]).reset_index()
        summary["x"] = summary["stage"].map(stage_to_x)
        summary = summary.sort_values("x")
        ax.errorbar(
            summary["x"],
            summary["mean"],
            yerr=summary["std"].fillna(0),
            marker="o",
            linewidth=2.5,
            capsize=4,
            label=group,
        )

    ax.set_title(metric)
    ax.set_xlabel("Estadio")
    ax.set_ylabel(metric)
    ax.set_xticks(range(len(stages)))
    ax.set_xticklabels(stages)
    ax.legend(title="Grupo")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    fig.savefig(Path(output_dir) / f"group_{metric}.png", dpi=300)
    plt.close(fig)


def main():
    input_path = Path(INPUT_PATH)
    output_dir = Path(OUTPUT_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)

    csv_files = collect_csv_files(input_path)
    for csv_path in csv_files:
        process_one_csv(csv_path, output_dir)

    if str(METADATA_PATH).strip() != "":
        run_group_analysis(output_dir, METADATA_PATH)


if __name__ == "__main__":
    main()
