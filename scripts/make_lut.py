#!/usr/bin/env python3
"""Write a Sony S-Log3 / S-Gamut3.Cine -> Rec.709 conversion LUT (.cube, 33^3).

Usage: make_lut.py OUT.cube [--exposure 1.0]
Sony's published S-Log3 curve and S-Gamut3.Cine matrix, a filmic shoulder (ACES-fit) and the
Rec.709 display curve. Drop Sony's own .cube into luts/ instead if you prefer it; edit.sh uses
whatever style.json -> grade.lut points to.
"""
import argparse
import numpy as np

ap = argparse.ArgumentParser(); ap.add_argument("out"); ap.add_argument("--exposure", type=float, default=1.0)
a = ap.parse_args()
N = 33

def slog3_to_lin(x):
    x = x * 1023
    return np.where(x >= 171.2102946929, 10 ** ((x - 420) / 261.5) * 0.19 - 0.01, (x - 95) * 0.01125 / (171.2102946929 - 95))

SG3C_XYZ = np.array([[0.5990839208, 0.2489255161, 0.1024464902],
                     [0.2150758201, 0.8850685017, -0.1001443219],
                     [-0.0320658495, -0.0276583907, 1.1487819910]])
XYZ_709 = np.array([[3.2404542, -1.5371385, -0.4985314],
                    [-0.9692660, 1.8760108, 0.0415560],
                    [0.0556434, -0.2040259, 1.0572252]])
M = XYZ_709 @ SG3C_XYZ

def filmic(x):  # Narkowicz ACES fit; mid grey 0.18 lands near 0.45 after the 709 curve
    x = np.maximum(x, 0) * 0.8 * a.exposure
    return np.clip(x * (2.51 * x + 0.03) / (x * (2.43 * x + 0.59) + 0.14), 0, 1)

def rec709(L):
    return np.where(L < 0.018, 4.5 * L, 1.099 * np.power(L, 0.45) - 0.099)

g = np.linspace(0, 1, N)
b, gg, r = np.meshgrid(g, g, g, indexing="ij")          # .cube order: red changes fastest
rgb = np.stack([r, gg, b], -1).reshape(-1, 3)
lin = slog3_to_lin(rgb) @ M.T
out = np.clip(rec709(filmic(lin)), 0, 1)
with open(a.out, "w") as f:
    f.write(f'TITLE "S-Log3 SGamut3.Cine to Rec709 (OVS)"\nLUT_3D_SIZE {N}\n')
    f.writelines(f"{p[0]:.6f} {p[1]:.6f} {p[2]:.6f}\n" for p in out)
grey = rec709(filmic(slog3_to_lin(np.array([0.41]))))[0]  # S-Log3 18% grey sits at code 0.41
print(f"{a.out}: {N}^3, 18% grey -> {grey:.3f}")
