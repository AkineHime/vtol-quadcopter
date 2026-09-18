import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from stl import mesh

m = mesh.Mesh.from_file(
    r"E:\proggramming\semester proj\models\freecad\coconut_quadplane_assembly.stl")

fig = plt.figure(figsize=(10, 8))
ax = fig.add_subplot(111, projection="3d")
coll = Poly3DCollection(m.vectors, facecolor="lightgrey", edgecolor="k",
                        linewidths=0.1, alpha=0.95)
ax.add_collection3d(coll)

pts = m.vectors.reshape(-1, 3)
mins, maxs = pts.min(axis=0), pts.max(axis=0)
print("bounding box mm:", dict(zip("xyz", zip(mins, maxs))))
print("length (x):", maxs[0] - mins[0])
print("span (y)  :", maxs[1] - mins[1])
print("height(z) :", maxs[2] - mins[2])

ctr = (mins + maxs) / 2
rng = (maxs - mins).max() / 2 * 1.1
ax.set_xlim(ctr[0] - rng, ctr[0] + rng)
ax.set_ylim(ctr[1] - rng, ctr[1] + rng)
ax.set_zlim(ctr[2] - rng, ctr[2] + rng)
ax.view_init(elev=22, azim=-60)
ax.set_box_aspect([1, 1, 1])
ax.set_title("FreeCAD solid assembly -- quick render check")
fig.tight_layout()
fig.savefig(r"E:\proggramming\semester proj\models\freecad\_render_check.png", dpi=160)
print("wrote _render_check.png")
