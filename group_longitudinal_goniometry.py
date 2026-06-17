#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Analisis grupal y longitudinal de goniometria lateral.

Este script corresponde a la etapa 2 del analisis.

QUE HACE:
1. Lee los archivos *_video_summary.csv generados por lateral_goniometry.py.
2. Usa una tabla de metadata para identificar animal, grupo y estadio.
3. Une todos los videos en una tabla por video.
4. Promedia videos repetidos dentro de cada animal y estadio.
5. Genera una tabla final animal x estadio.
6. Genera graficos longitudinales por articulacion.
7. Exporta tablas listas para estadistica.

Por defecto considera estadios P30, P37, P44, P51, P65 y P85.

IMPORTANTE:
- Este script NO lee archivos originales de DeepLabCut.
- Este script NO recalcula angulos.
- Este script NO detecta ciclos.
- Este script usa solamente los resumenes generados por lateral_goniometry.py.

REQUISITOS:
pip install pandas numpy matplotlib
"""

# ============================================================
# CAMBIA SOLO ESTAS LINEAS
# ============================================================

SUMMARY_DIR = r"C:\CAMBIA\ESTA\RUTA\resultados_angulos"
METADATA_PATH = r"C:\CAMBIA\ESTA\RUTA\metadata_goniometry.csv"
OUTPUT_DIR = r"C:\CAMBIA\ESTA\RUTA\resultados_grupales"

STAGE_ORDER = ["P30", "P37", "P44", "P51", "P65", "P85"]
GROUP_ORDER = ["WT", "SOD1"]

BASELINE_STAGE = "P30"
FINAL_STAGE = "P85"

# ============================================================
# NO CAMBIAR DESDE AQUI, SALVO QUE QUIERAS MODIFICAR EL METODO
# ============================================================

from pathlib import Path
import re
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


JOINTS = ["hip", "knee", "ankle", "foot"]


def normalize_stage_label(stage):
    """
    Normaliza estadios para que el usuario pueda escribir P85, p85 o 85.
    """
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
    """
    Ordena estadios tipo P30, P37, P44.
    Si no encuentra numero, ordena alfabeticamente.
    """
    text = str(stage)
    match = re.search(r"(\d+)", text)
    if match:
        return int(match.group(1))
    return text


def ordered_unique(values, preferred_order=None):
    """
    Devuelve valores unicos respetando un orden definido por el usuario.
    """
    values = [str(v) for v in values if pd.notna(v)]
    unique_values = list(dict.fromkeys(values))

    if preferred_order:
        preferred = [v for v in preferred_order if v in unique_values]
        remaining = [v for v in unique_values if v not in preferred_order]
        remaining = sorted(remaining, key=natural_stage_key)
        return preferred + remaining

    return sorted(unique_values, key=natural_stage_key)


def read_video_summaries(summary_dir):
    """
    Lee todos los archivos *_video_summary.csv generados por lateral_goniometry.py.
    """
    summary_dir = Path(summary_dir)
    files = sorted(summary_dir.rglob("*_video_summary.csv"))

    if len(files) == 0:
        raise FileNotFoundError(
            f"No encontre archivos *_video_summary.csv en: {summary_dir}"
        )

    tables = []

    for path in files:
        df = pd.read_csv(path)

        if "file" not in df.columns:
            df.insert(0, "file", path.name.replace("_video_summary.csv", ".csv"))

        df.insert(0, "summary_file", path.name)
        df.insert(1, "summary_path", str(path))

        # Estas columnas se manejaran desde la metadata externa.
        for col in ["animal", "group", "stage"]:
            if col in df.columns:
                df = df.drop(columns=col)

        tables.append(df)

    return pd.concat(tables, ignore_index=True)


def create_metadata_template(video_table, metadata_path):
    """
    Crea una plantilla de metadata si no existe.
    El usuario debe completarla antes de correr el analisis grupal.
    """
    metadata_path = Path(metadata_path)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)

    template = video_table[["summary_file", "file"]].copy()
    template["animal"] = ""
    template["group"] = ""
    template["stage"] = ""

    template.to_csv(metadata_path, index=False)

    raise SystemExit(
        "\nSe creo una plantilla de metadata.\n"
        f"Archivo: {metadata_path}\n\n"
        "Completa las columnas animal, group y stage.\n"
        "Despues vuelve a ejecutar este script.\n"
    )


def load_metadata(metadata_path, video_table):
    """
    Carga metadata.
    Si no existe, crea una plantilla automaticamente.
    """
    metadata_path = Path(metadata_path)

    if not metadata_path.exists():
        create_metadata_template(video_table, metadata_path)

    metadata = pd.read_csv(metadata_path)

    required = {"animal", "group", "stage"}
    missing = required.difference(metadata.columns)

    if missing:
        raise ValueError(
            "La metadata debe contener las columnas: animal, group, stage.\n"
            f"Columnas faltantes: {sorted(missing)}"
        )

    if "summary_file" not in metadata.columns and "file" not in metadata.columns:
        raise ValueError(
            "La metadata debe contener al menos una columna para unir los datos: "
            "summary_file o file."
        )

    return metadata


def merge_video_table_with_metadata(video_table, metadata):
    """
    Une resumenes por video con la metadata del experimento.
    Usa summary_file si existe. Si no, usa file.
    """
    if "summary_file" in metadata.columns:
        merged = video_table.merge(
            metadata,
            on="summary_file",
            how="left",
            suffixes=("", "_metadata"),
        )
    else:
        merged = video_table.merge(
            metadata,
            on="file",
            how="left",
            suffixes=("", "_metadata"),
        )

    # Si metadata tambien tenia file, dejar una sola columna limpia.
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
        cols = ["summary_file", "file"]
        missing_preview = missing_rows[cols].drop_duplicates()
        raise ValueError(
            "Hay archivos sin metadata completa.\n"
            "Completa animal, group y stage en metadata_goniometry.csv.\n\n"
            f"{missing_preview.to_string(index=False)}"
        )

    merged["animal"] = merged["animal"].astype(str)
    merged["group"] = merged["group"].astype(str)
    merged["stage"] = merged["stage"].apply(normalize_stage_label)

    return merged


def make_animal_stage_table(merged):
    """
    Promedia videos repetidos dentro de cada animal y estadio.
    Devuelve una tabla final con una fila por animal x grupo x estadio.
    """
    value_cols = []

    for joint in JOINTS:
        col = f"{joint}_range_mean_deg"
        if col in merged.columns:
            value_cols.append(col)

    if len(value_cols) == 0:
        raise ValueError(
            "No encontre columnas de rango angular en los resumenes.\n"
            "Esperaba columnas como hip_range_mean_deg, knee_range_mean_deg, etc."
        )

    agg_dict = {col: "mean" for col in value_cols}

    if "n_cycles" in merged.columns:
        agg_dict["n_cycles"] = "sum"

    grouped = (
        merged
        .groupby(["animal", "group", "stage"], as_index=False)
        .agg(agg_dict)
    )

    video_counts = (
        merged
        .groupby(["animal", "group", "stage"], as_index=False)
        .size()
        .rename(columns={"size": "n_videos"})
    )

    grouped = grouped.merge(
        video_counts,
        on=["animal", "group", "stage"],
        how="left",
    )

    rename_map = {
        f"{joint}_range_mean_deg": f"{joint}_range_deg"
        for joint in JOINTS
        if f"{joint}_range_mean_deg" in grouped.columns
    }

    grouped = grouped.rename(columns=rename_map)

    stage_rank = {stage: i for i, stage in enumerate(STAGE_ORDER)}
    group_rank = {group: i for i, group in enumerate(GROUP_ORDER)}

    grouped["_group_rank"] = grouped["group"].map(group_rank).fillna(999)
    grouped["_stage_rank"] = grouped["stage"].map(stage_rank)

    # Si hay estadios que no estan en STAGE_ORDER, ordenarlos por numero si es posible.
    fallback_stage_rank = grouped["stage"].apply(natural_stage_key)
    grouped["_stage_rank"] = grouped["_stage_rank"].where(
        grouped["_stage_rank"].notna(),
        fallback_stage_rank,
    )

    grouped = grouped.sort_values(
        ["_group_rank", "animal", "_stage_rank"]
    ).drop(columns=["_group_rank", "_stage_rank"])

    return grouped


def make_joint_tables(final_table, output_dir):
    """
    Exporta una tabla individual para cada articulacion.
    """
    output_dir = Path(output_dir)

    for joint in JOINTS:
        col = f"{joint}_range_deg"
        if col not in final_table.columns:
            continue

        out = final_table[["animal", "group", "stage", col]].copy()
        out.to_csv(output_dir / f"final_table_{joint}.csv", index=False)


def make_delta_table(final_table, output_dir):
    """
    Calcula cambio entre estadio final y basal:
    delta = final - basal.
    """
    if not BASELINE_STAGE or not FINAL_STAGE:
        return None

    value_cols = [
        f"{joint}_range_deg"
        for joint in JOINTS
        if f"{joint}_range_deg" in final_table.columns
    ]

    baseline = final_table[final_table["stage"] == BASELINE_STAGE][
        ["animal", "group", *value_cols]
    ].copy()

    final = final_table[final_table["stage"] == FINAL_STAGE][
        ["animal", "group", *value_cols]
    ].copy()

    if baseline.empty or final.empty:
        return None

    merged = baseline.merge(
        final,
        on=["animal", "group"],
        how="inner",
        suffixes=("_baseline", "_final"),
    )

    delta = merged[["animal", "group"]].copy()

    for joint in JOINTS:
        base_col = f"{joint}_range_deg_baseline"
        final_col = f"{joint}_range_deg_final"

        if base_col in merged.columns and final_col in merged.columns:
            delta[f"{joint}_delta_{FINAL_STAGE}_minus_{BASELINE_STAGE}"] = (
                merged[final_col] - merged[base_col]
            )

    if len(delta.columns) > 2:
        path = Path(output_dir) / f"delta_{FINAL_STAGE}_minus_{BASELINE_STAGE}.csv"
        delta.to_csv(path, index=False)
        return delta

    return None


def make_longitudinal_plots(final_table, output_dir):
    """
    Genera graficos longitudinales por articulacion.
    Muestra animales individuales y media ± SEM por grupo.
    """
    output_dir = Path(output_dir)

    stages = ordered_unique(final_table["stage"], STAGE_ORDER)
    groups = ordered_unique(final_table["group"], GROUP_ORDER)

    stage_to_x = {stage: i for i, stage in enumerate(stages)}

    for joint in JOINTS:
        col = f"{joint}_range_deg"
        if col not in final_table.columns:
            continue

        fig, ax = plt.subplots(figsize=(7, 4.5))

        for group in groups:
            group_data = final_table[final_table["group"] == group]

            for animal, animal_data in group_data.groupby("animal"):
                animal_data = animal_data.copy()
                animal_data["x"] = animal_data["stage"].map(stage_to_x)
                animal_data = animal_data.sort_values("x")

                ax.plot(
                    animal_data["x"],
                    animal_data[col],
                    marker="o",
                    linewidth=1,
                    alpha=0.35,
                )

            mean_table = (
                group_data
                .groupby("stage")[col]
                .agg(["mean", "sem"])
                .reset_index()
            )

            mean_table["x"] = mean_table["stage"].map(stage_to_x)
            mean_table = mean_table.sort_values("x")

            ax.errorbar(
                mean_table["x"],
                mean_table["mean"],
                yerr=mean_table["sem"].fillna(0),
                marker="o",
                linewidth=2.5,
                capsize=4,
                label=group,
            )

        ax.set_title(f"{joint}: rango angular longitudinal")
        ax.set_xlabel("Estadio")
        ax.set_ylabel("Rango angular (grados)")
        ax.set_xticks(range(len(stages)))
        ax.set_xticklabels(stages)
        ax.legend(title="Grupo")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        fig.tight_layout()

        fig.savefig(output_dir / f"longitudinal_{joint}_range.png", dpi=300)
        plt.close(fig)


def print_summary(final_table):
    """
    Imprime resumen rapido en consola.
    """
    print("=" * 70)
    print("Analisis grupal completado")
    print("=" * 70)
    print(f"Animales detectados: {final_table['animal'].nunique()}")
    print(f"Grupos detectados: {', '.join(ordered_unique(final_table['group'], GROUP_ORDER))}")
    print(f"Estadios detectados: {', '.join(ordered_unique(final_table['stage'], STAGE_ORDER))}")
    print("=" * 70)


def main():
    summary_dir = Path(SUMMARY_DIR)
    metadata_path = Path(METADATA_PATH)
    output_dir = Path(OUTPUT_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)

    video_table = read_video_summaries(summary_dir)
    metadata = load_metadata(metadata_path, video_table)
    merged = merge_video_table_with_metadata(video_table, metadata)
    final_table = make_animal_stage_table(merged)

    merged.to_csv(output_dir / "merged_video_summary_with_metadata.csv", index=False)
    final_table.to_csv(output_dir / "final_animal_stage_table.csv", index=False)

    make_joint_tables(final_table, output_dir)
    make_delta_table(final_table, output_dir)
    make_longitudinal_plots(final_table, output_dir)
    print_summary(final_table)

    print(f"Carpeta de salida: {output_dir}")


if __name__ == "__main__":
    main()
