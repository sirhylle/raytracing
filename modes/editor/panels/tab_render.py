from ..ui_core import *

def build(ui_list, start_y, state, engine, on_start_render):
    ys = start_y
    
    # --- 1. SETTINGS ---
    lbl(ui_list, 10, ys, "Output Resolution", 14, COL_ACCENT)
    ys += 25
    
    # Champs W / H
    lbl(ui_list, 10, ys+3, "W", 12, COL_TEXT_DIM)
    ui_list.append(NumberField(VIEW_W+30, ys, 60, 22, 
                               lambda: state.conf.width, 
                               lambda v: state.update_resolution(v, state.conf.height), fmt="{:.0f}"))
                               
    lbl(ui_list, 110, ys+3, "H", 12, COL_TEXT_DIM)
    ui_list.append(NumberField(VIEW_W+130, ys, 60, 22, 
                               lambda: state.conf.height, 
                               lambda v: state.update_resolution(state.conf.width, v), fmt="{:.0f}"))
    ys += 30

    # Presets de Ratio (Boutons rapides)
    def set_preset(w, h): state.update_resolution(w, h)
    
    btn(ui_list, 10, ys, 60, 20, "720p", lambda: set_preset(1280, 720))
    btn(ui_list, 75, ys, 60, 20, "1080p", lambda: set_preset(1920, 1080))
    btn(ui_list, 140, ys, 60, 20, "Square", lambda: set_preset(1080, 1080))
    btn(ui_list, 205, ys, 60, 20, "Portrait", lambda: set_preset(1080, 1350)) # Instagram
    ys += 40
    
    ui_list.append(Separator(ys, "QUALITY"))
    ys += 25
    
    # SPP
    lbl(ui_list, 10, ys+3, "Max SPP", 12)
    ui_list.append(NumberField(VIEW_W+80, ys, 60, 22, 
                               lambda: state.conf.spp, 
                               lambda v: setattr(state.conf, 'spp', int(v)), fmt="{:.0f}"))
    ys += 30
    
    # Depth
    lbl(ui_list, 10, ys+3, "Bounces", 12)
    ui_list.append(NumberField(VIEW_W+80, ys, 60, 22, 
                               lambda: state.conf.depth, 
                               lambda v: setattr(state.conf, 'depth', int(v)), fmt="{:.0f}"))
    ys += 30

    # --- 2. PREVIEW SCALING ---
    # On déplace ici les réglages "Auto / 1:1" qui étaient dans le header global
    ui_list.append(Separator(ys, "VIEWPORT PREVIEW"))
    ys += 25
    
    lbl(ui_list, 10, ys+3, "Quality", 12, COL_TEXT_DIM)
    def set_res(v): state.res_auto = (v=='AUTO'); state.res_scale = v if v!='AUTO' else 1; state.dirty = True
    grp_res = []
    btn(ui_list, 50, ys, 45, 20, "Auto", set_res, 'AUTO', True, grp_res, state.res_auto)
    btn(ui_list, 100, ys, 35, 20, "1:1", set_res, 1, True, grp_res, (not state.res_auto and state.res_scale==1))
    btn(ui_list, 140, ys, 35, 20, "1:2", set_res, 2, True, grp_res, (state.res_scale==2))
    btn(ui_list, 180, ys, 35, 20, "1:4", set_res, 4, True, grp_res, (state.res_scale==4))
    ys += 40

    # --- 3. ACTION ---
    # Le gros bouton
    btn(ui_list, 10, ys, 300, 50, "START RENDER", on_start_render, col_ov=(50, 100, 50), bd_ov=(100, 200, 100))
    lbl(ui_list, 20, ys+55, "Will freeze editor until finished.", 11, COL_TEXT_DIM)