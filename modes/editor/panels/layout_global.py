import pygame
from ..ui_core import *

def build_global_layout(ui_list, state, engine, on_start_render):
    """Construit les éléments UI fixes (Header, Tabs, Footer)."""
    ui_list.clear()

    y = 10
    # 1. MONITORING
    lbl(ui_list, 10, y, lambda: f"FPS: --", 14, COL_TEXT_DIM) # Hack: FPS mis à jour par boucle main
    lbl(ui_list, 100, y, lambda: f"SPP: {state.accum_spp}", 14, COL_TEXT_DIM)
    y += 25

    # 2. RENDER SETTINGS
    lbl(ui_list, 10, y+3, "Qual", 12, COL_TEXT_DIM)
    def set_res(v): state.res_auto = (v=='AUTO'); state.res_scale = v if v!='AUTO' else 1; state.dirty = True
    grp_res = []
    btn(ui_list, 50, y, 45, 20, "Auto", set_res, 'AUTO', True, grp_res, state.res_auto)
    btn(ui_list, 100, y, 35, 20, "1:1", set_res, 1, True, grp_res, (not state.res_auto and state.res_scale==1))
    btn(ui_list, 140, y, 35, 20, "1:2", set_res, 2, True, grp_res, (state.res_scale==2))
    btn(ui_list, 180, y, 35, 20, "1:4", set_res, 4, True, grp_res, (state.res_scale==4))
    y += 26

    lbl(ui_list, 10, y+3, "Mode", 12, COL_TEXT_DIM)
    def set_mode(m): state.preview_mode = m; state.dirty = True
    grp_mode = []
    btn(ui_list, 50, y, 60, 20, "Normals", set_mode, 0, True, grp_mode, state.preview_mode==0)
    btn(ui_list, 115, y, 60, 20, "Clay", set_mode, 1, True, grp_mode, state.preview_mode==1)
    btn(ui_list, 180, y, 60, 20, "Ray", set_mode, 2, True, grp_mode, state.preview_mode==2)
    y += 45

    # 4. TABS
    def set_tab(t): state.set_active_tab(t) # Main loop détectera le changement et reconstruira le contenu
    grp_tabs = []
    tab_w = 150
    b1 = btn(ui_list, 10, y, tab_w, 28, "SCENE", set_tab, "SCENE", True, grp_tabs, state.active_tab=="SCENE", COL_TAB_INA)
    b1.corners = {'tl': 4, 'bl': 4, 'tr': 0, 'br': 0}
    b2 = btn(ui_list, 10 + tab_w, y, tab_w, 28, "OBJECT", set_tab, "OBJECT", True, grp_tabs, state.active_tab=="OBJECT", COL_TAB_INA)
    b2.corners = {'tl': 0, 'bl': 0, 'tr': 4, 'br': 4}
    
    # 5. FOOTER
    btn(ui_list, 10, WIN_H - 42, 300, 34, "RENDER FINAL IMAGE", on_start_render)
    
    return y + 40 # Retourne la position Y de départ pour le contenu des onglets