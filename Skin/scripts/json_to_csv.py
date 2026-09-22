#!/usr/bin/env python3
'''
Convert the JSON written by scope_func_measure.py into a flat CSV.

Usage:
    python3 json_to_csv.py data/json_data/AIR_2026-09-22_11_24_09.json
    python3 json_to_csv.py data/json_data/*.json

The CSV lands beside the JSON with the same stem. Rows are sorted by
frequency. The ratio column is CHAN2 vpp over CHAN1 vpp, which is the
observable the skin depth analysis actually uses, since it divides out the
drive amplitude drift caused by the generator's 50 ohm source impedance.

Phase is reported once per frequency, not once per channel. The scope's
:MEAS:RPH? always returns CHAN2 relative to CHAN1 regardless of :MEAS:SOUR,
so the per-channel "phi" entries in the JSON are duplicates of one value.
'''

import csv
import json
import os
import sys

# The Rigol returns this from a measurement it could not make.
RIGOL_INVALID = 9.9e37

FIELDS = ["f_hz",
          "ch1_vpp", "ch2_vpp", "ratio", "phi_deg",
          "ch1_vrms", "ch2_vrms",
          "ch1_vmax", "ch1_vmin", "ch2_vmax", "ch2_vmin",
          "ch1_freq_hz", "valid"]


def valid(x):
    return abs(x) < RIGOL_INVALID / 10


def convert(path):
    with open(path) as fh:
        data = json.load(fh)

    out_path = os.path.splitext(path)[0] + ".csv"
    n_bad = 0

    with open(out_path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        writer.writeheader()

        for key in sorted(data, key=float):
            c1 = data[key]["CHAN1"]
            c2 = data[key]["CHAN2"]

            ok = valid(c1["vpp"]) and valid(c2["vpp"]) and c1["vpp"] != 0
            if not ok:
                n_bad += 1

            writer.writerow({
                "f_hz": float(key),
                "ch1_vpp": c1["vpp"],
                "ch2_vpp": c2["vpp"],
                "ratio": (c2["vpp"] / c1["vpp"]) if ok else "",
                "phi_deg": c1["phi"] if valid(c1["phi"]) else "",
                "ch1_vrms": c1["vrms"],
                "ch2_vrms": c2["vrms"],
                "ch1_vmax": c1["vmax"],
                "ch1_vmin": c1["vmin"],
                "ch2_vmax": c2["vmax"],
                "ch2_vmin": c2["vmin"],
                "ch1_freq_hz": c1["freq"] if "freq" in c1 else "",
                "valid": int(ok),
            })

    print("{0}  ->  {1}  ({2} rows{3})".format(
        os.path.basename(path), os.path.basename(out_path), len(data),
        ", {0} unusable".format(n_bad) if n_bad else ""))


if len(sys.argv) < 2:
    print(__doc__)
    sys.exit(1)

for arg in sys.argv[1:]:
    convert(arg)
