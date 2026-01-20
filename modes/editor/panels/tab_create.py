from ..ui_core import *
import numpy as np

def build(ui_list, start_y, state, engine):
    ys = start_y
    
    lbl(ui_list, 10, ys, "ADD PRIMITIVE", 12, COL_ACCENT)
    ys += 25
    
    # Helper pour ajouter devant la caméra
    def add_prim(type_str):
        state.add_primitive(type_str)

    # Grille de boutons 2 colonnes
    bw = (PANEL_W - 30) // 2
    
    btn(ui_list, 10, ys, bw, 30, "Sphere", add_prim, "sphere")
    btn(ui_list, 10+bw+10, ys, bw, 30, "Cube", add_prim, "cube")
    ys += 40
    
    btn(ui_list, 10, ys, bw, 30, "Plane (Floor)", add_prim, "quad_floor")
    btn(ui_list, 10+bw+10, ys, bw, 30, "Quad (Wall)", add_prim, "quad_wall")
    ys += 40

    ui_list.append(Separator(ys))
    ys += 15
    
    lbl(ui_list, 10, ys, "ADD LIGHT", 12, COL_ACCENT)
    ys += 25
    
    btn(ui_list, 10, ys, PANEL_W-20, 30, "Sphere Light", add_prim, "light_sphere")
    ys += 35
    
    btn(ui_list, 10, ys, PANEL_W-20, 30, "Ceiling Light (Quad)", add_prim, "light_quad")
    ys += 40