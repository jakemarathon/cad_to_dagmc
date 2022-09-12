from vertices_to_h5m import vertices_to_h5m
from pathlib import Path
import math
from tempfile import mkstemp

from typing import Iterable
from cadquery import importers
from OCP.GCPnts import GCPnts_QuasiUniformDeflection

# from cadquery.occ_impl import shapes
import OCP
import cadquery as cq
from vertices_to_h5m import vertices_to_h5m
from OCP.TopLoc import TopLoc_Location
from OCP.BRep import BRep_Tool
from OCP.TopAbs import TopAbs_Orientation

from brep_to_h5m import mesh_brep, brep_to_h5m
import brep_part_finder as bpf

class CadToDagmc():
    def __init__(self):
        self.parts = []
        self.material_tags = []

    def add_stp_file(self, filename: str, material_tags: Iterable[str], scale_factor: float = 1.0):
        """Loads a stp file and makes the 3D solid and wires available for use.
        Args:
            filename: the filename used to save the html graph.
            scale_factor: a scaling factor to apply to the geometry that can be
                used to increase the size or decrease the size of the geometry.
                Useful when converting the geometry to cm for use in neutronics
                simulations.
            auto_merge: whether or not to merge the surfaces. This defaults to True
                as merged surfaces are needed to avoid overlapping meshes in some
                cases. More details on the merging process in the DAGMC docs
                https://svalinn.github.io/DAGMC/usersguide/cubit_basics.html
        Returns:
            CadQuery.solid, CadQuery.Wires: solid and wires belonging to the object
        """

        part = importers.importStep(str(filename)).val()

        if scale_factor == 1:
            scaled_part = part
        else:
            scaled_part = part.scale(scale_factor)

        for solid in scaled_part.Solids():
            self.parts.append(solid)
        for material_tag in material_tags:
            self.material_tags.append(material_tag)

    def export_dagmc_h5m_file(self, filename='dagmc.h5m', min_mesh_size=1, max_mesh_size=10):

        volume_atol: float = 0.000001
        center_atol: float = 0.000001
        bounding_box_atol: float = 0.000001

        brep_shape = self._merge_surfaces()

        brep_file_part_properties = bpf.get_brep_part_properties_from_shape(brep_shape)
        print(brep_file_part_properties)

        shape_properties = {}
        for counter, solid in enumerate(self.parts):
            sub_solid_descriptions = []

            # checks if the solid is a cq.Compound or not
            # if isinstance(solid, cq.occ_impl.shapes.Compound):
            iterable_solids = solid.Solids()
            # else:
            #     iterable_solids = solid.val().Solids()

            for sub_solid in iterable_solids:
                part_bb = sub_solid.BoundingBox()
                part_center = sub_solid.Center()
                sub_solid_description = {
                    "volume": sub_solid.Volume(),
                    "center": (part_center.x, part_center.y, part_center.z),
                    "bounding_box": (
                        (part_bb.xmin, part_bb.ymin, part_bb.zmin),
                        (part_bb.xmax, part_bb.ymax, part_bb.zmax),
                    ),
                }
                sub_solid_descriptions.append(sub_solid_description)

                shape_properties[self.material_tags[counter]] = sub_solid_descriptions

        key_and_part_id = bpf.get_dict_of_part_ids(
                brep_part_properties=brep_file_part_properties,
                shape_properties=shape_properties,
                volume_atol=volume_atol,
                center_atol=center_atol,
                bounding_box_atol=bounding_box_atol,
            )

        tmp_brep_filename = mkstemp(suffix=".brep", prefix="paramak_")[1]
        brep_shape.exportBrep(tmp_brep_filename)

        brep_to_h5m(
            brep_filename=tmp_brep_filename,
            volumes_with_tags=key_and_part_id,
            h5m_filename=filename,
            min_mesh_size=min_mesh_size,
            max_mesh_size=max_mesh_size,
        )

    def _merge_surfaces(self):
        """Merges surfaces in the geometry that are the same"""

        # solids = geometry.Solids()

        bldr = OCP.BOPAlgo.BOPAlgo_Splitter()

        if len(self.parts) == 1:
            # merged_solid = cq.Compound(solids)
            return self.parts[0]

        for solid in self.parts:
            # print(type(solid))
            # checks if solid is a compound as .val() is not needed for compounds
            if isinstance(solid, (cq.occ_impl.shapes.Compound, cq.occ_impl.shapes.Solid)):
                bldr.AddArgument(solid.wrapped)
            else:
                bldr.AddArgument(solid.val().wrapped)

        bldr.SetNonDestructive(True)

        bldr.Perform()

        bldr.Images()

        merged_solid = cq.Compound(bldr.Shape())

        return merged_solid


    # def tessellate(parts, tolerance: float = 0.1, angularTolerance: float = 0.1):
    #     """Creates a mesh / faceting / tessellation of the surface"""

    #     parts.mesh(tolerance, angularTolerance)

    #     offset = 0

    #     vertices: List[Vector] = []
    #     triangles = {}

    #     for f in parts.Faces():
    #         print(f)

    #         loc = TopLoc_Location()
    #         poly = BRep_Tool.Triangulation_s(f.wrapped, loc)
    #         Trsf = loc.Transformation()

    #         reverse = (
    #             True
    #             if f.wrapped.Orientation() == TopAbs_Orientation.TopAbs_REVERSED
    #             else False
    #         )

    #         # add vertices
    #         face_verticles = [
    #             (v.X(), v.Y(), v.Z()) for v in (v.Transformed(Trsf) for v in poly.Nodes())
    #         ]
    #         vertices += face_verticles

    #         face_triangles = [
    #             (
    #                 t.Value(1) + offset - 1,
    #                 t.Value(3) + offset - 1,
    #                 t.Value(2) + offset - 1,
    #             )
    #             if reverse
    #             else (
    #                 t.Value(1) + offset - 1,
    #                 t.Value(2) + offset - 1,
    #                 t.Value(3) + offset - 1,
    #             )
    #             for t in poly.Triangles()
    #         ]
    #         triangles[f.hashCode()] = face_triangles

    #         offset += poly.NbNodes()

    #     list_of_triangles_per_solid = []
    #     for s in parts.Solids():
    #         print(s)
    #         triangles_on_solid = []
    #         for f in s.Faces():
    #             print(s, f)
    #             triangles_on_solid += triangles[f.hashCode()]
    #         list_of_triangles_per_solid.append(triangles_on_solid)
    #     for vert in vertices:
    #         print(vert)
    #     for tri in list_of_triangles_per_solid:
    #         print(tri)
    #     return vertices, list_of_triangles_per_solid
