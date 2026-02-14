from ..ui_core import *
import numpy as np

def build(ui_list, start_y, state, engine):
    ys = start_y
    
    # Helper identical to other tabs for visual consistency
    def draw_header(title, section_name):
        nonlocal ys
        
        def toggle():
            state.toggle_accordion("CREATE", section_name)

        is_open = state.is_accordion_open("CREATE", section_name)

        ui_list.append(HeaderBar(VIEW_W + 5, ys - 4, PANEL_W - 10, 26, COL_HEADER, callback=toggle))
        lbl(ui_list, 15, ys, title, 14, COL_ACCENT)
        
        lbl(ui_list, PANEL_W - 25, ys-2, "-", 16, COL_TEXT_DIM) if is_open else lbl(ui_list, PANEL_W - 26, ys-1, "+", 16, COL_TEXT_DIM)
        
        ys += 30
        return is_open

    # Helper Action
    def add_prim(type_str):
        state.add_primitive(type_str)

    # --- 1. PRIMITIVES ---
    if draw_header("PRIMITIVES", "PRIMITIVES"):
        # Button Grid (2 columns)
        bw = (PANEL_W - 30) // 2
        
        btn(ui_list, 10, ys, bw, 30, "Sphere", add_prim, "sphere")
        btn(ui_list, 10+bw+10, ys, bw, 30, "Cube", add_prim, "cube")
        ys += 40
        
        btn(ui_list, 10, ys, bw, 30, "Cylinder", add_prim, "cylinder")
        btn(ui_list, 10+bw+10, ys, bw, 30, "Cone", add_prim, "cone")
        ys += 40

        btn(ui_list, 10, ys, bw, 30, "Pyramid", add_prim, "pyramid")
        btn(ui_list, 10+bw+10, ys, bw, 30, "Tetrahedron", add_prim, "tetrahedron")
        ys += 40

        btn(ui_list, 10, ys, bw, 30, "Icosahedron", add_prim, "icosahedron")
        ys += 40
        
        btn(ui_list, 10, ys, bw, 30, "Plane (Floor)", add_prim, "quad_floor")
        btn(ui_list, 10+bw+10, ys, bw, 30, "Quad (Wall)", add_prim, "quad_wall")
        ys += 40
        ys += 10
    else:
        ys += 5

    # --- 2. LIGHTS ---
    if draw_header("LIGHTS", "LIGHTS"):
        btn(ui_list, 10, ys, PANEL_W-20, 30, "Sphere Light", add_prim, "light_sphere")
        ys += 35
        
        btn(ui_list, 10, ys, PANEL_W-20, 30, "Ceiling Light (Quad)", add_prim, "light_quad")
        ys += 40
        ys += 10
    else:
        ys += 5

    # --- 3. IMPORT ---
    if draw_header("IMPORT", "IMPORT"):
        btn(ui_list, 10, ys, PANEL_W-20, 30, "LOAD MESH FILE...", lambda: state.load_mesh_dialog(engine))
        ys += 40
        
        lbl(ui_list, 10, ys, "Supports .obj, .glb, .stl", 11, COL_TEXT_DIM)
        ys += 20
        ys += 10
    else:
         ys += 5