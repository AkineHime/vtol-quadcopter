#!/usr/bin/env python3
"""
mesh_from_step.py -- turn the printed-build STEP into the Gazebo visual mesh,
without FreeCAD (uses gmsh's OpenCASCADE reader).

    python mesh_from_step.py

  in : airframe/out/coconut_quadplane_build.step   (mm, build frame X aft / Y right / Z up;
       written by airframe/build_airframe.py)
  out: flight_software/gazebo/models/coconut_quadplane/meshes/coconut_quadplane.stl

gen_sdf.py applies the mm -> m scale, the 180 deg yaw and the CG offset.
"""
from pathlib import Path

import gmsh

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
STEP = REPO / "airframe" / "out" / "coconut_quadplane_build.step"
OUT = HERE / "models" / "coconut_quadplane" / "meshes" / "coconut_quadplane.stl"


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    gmsh.initialize()
    gmsh.option.setNumber("General.Terminal", 1)
    gmsh.model.add("cq")
    gmsh.model.occ.importShapes(str(STEP))
    gmsh.model.occ.synchronize()
    # coarse surface mesh: visual only, keep it light for the renderer
    gmsh.option.setNumber("Mesh.MeshSizeMin", 3.0)
    gmsh.option.setNumber("Mesh.MeshSizeMax", 25.0)
    gmsh.option.setNumber("Mesh.MeshSizeFromCurvature", 12)
    gmsh.option.setNumber("Mesh.Binary", 1)
    gmsh.model.mesh.generate(2)
    xmin, ymin, zmin, xmax, ymax, zmax = gmsh.model.getBoundingBox(-1, -1)
    gmsh.write(str(OUT))
    gmsh.finalize()
    print(f"wrote {OUT}  ({OUT.stat().st_size / 1e6:.1f} MB)")
    print(f"bbox mm: x {xmin:.0f}..{xmax:.0f}  y {ymin:.0f}..{ymax:.0f}  z {zmin:.0f}..{zmax:.0f}")


if __name__ == "__main__":
    main()
