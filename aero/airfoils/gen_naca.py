#!/usr/bin/env python3
"""Generate a NACA 4-digit airfoil .dat file (Selig format, TE->top->LE->bot->TE).

Usage:  python gen_naca.py 0009 NACA0009.dat [n_points_per_surface]
"""
import sys
import math


def naca4(code: str, n: int = 100):
    m = int(code[0]) / 100.0          # max camber
    p = int(code[1]) / 10.0           # camber position
    t = int(code[2:]) / 100.0         # thickness

    # cosine spacing, LE-clustered
    beta = [math.pi * i / (n - 1) for i in range(n)]
    x = [(1 - math.cos(b)) / 2 for b in beta]

    def yt(xc):
        return 5 * t * (0.2969 * math.sqrt(xc) - 0.1260 * xc
                        - 0.3516 * xc**2 + 0.2843 * xc**3
                        - 0.1015 * xc**4)   # open TE (standard)

    def camber(xc):
        if m == 0 or p == 0:
            return 0.0, 0.0
        if xc < p:
            yc = m / p**2 * (2 * p * xc - xc**2)
            dyc = 2 * m / p**2 * (p - xc)
        else:
            yc = m / (1 - p)**2 * ((1 - 2 * p) + 2 * p * xc - xc**2)
            dyc = 2 * m / (1 - p)**2 * (p - xc)
        return yc, dyc

    upper, lower = [], []
    for xc in x:
        th = yt(xc)
        yc, dyc = camber(xc)
        theta = math.atan(dyc)
        upper.append((xc - th * math.sin(theta), yc + th * math.cos(theta)))
        lower.append((xc + th * math.sin(theta), yc - th * math.cos(theta)))

    # Selig order: TE -> upper surface -> LE -> lower surface -> TE
    pts = list(reversed(upper)) + lower[1:]
    return pts


if __name__ == "__main__":
    code = sys.argv[1] if len(sys.argv) > 1 else "0009"
    out = sys.argv[2] if len(sys.argv) > 2 else f"NACA{code}.dat"
    n = int(sys.argv[3]) if len(sys.argv) > 3 else 120
    pts = naca4(code, n)
    with open(out, "w") as f:
        f.write(f"NACA {code}\n")
        for xx, yy in pts:
            f.write(f"{xx:9.6f} {yy:9.6f}\n")
    print(f"wrote {out}  ({len(pts)} points)")
