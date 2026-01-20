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
    #lbl(ui_list, 10, y+3, "Mode", 12, COL_TEXT_DIM)
    def set_mode(m): state.preview_mode = m; state.dirty = True
    grp_mode = []
    btn(ui_list, 10, y, 60, 20, "Normals", set_mode, 0, True, grp_mode, state.preview_mode==0)
    btn(ui_list, 75, y, 60, 20, "Clay", set_mode, 1, True, grp_mode, state.preview_mode==1)
    btn(ui_list, 140, y, 60, 20, "Ray", set_mode, 2, True, grp_mode, state.preview_mode==2)
    y += 45

    # --- BARRE DU HAUT : FICHIER ---
    # On utilise un style plus petit/discret
    
    # Boutons placés à gauche
    bx = 10
    # On appelle directement state.save_scene_dialog
    btn(ui_list, bx, y, 60, 24, "SAVE", state.save_scene_dialog, col_ov=(40, 40, 40))
    bx += 65
    btn(ui_list, bx, y, 60, 24, "LOAD", state.load_scene_dialog, col_ov=(40, 40, 40))
    y += 35

    # 4. TABS
    def set_tab(t): state.set_active_tab(t) # Main loop détectera le changement et reconstruira le contenu
    grp_tabs = []
    tab_w = 100
    
    # SCENE
    b1 = btn(ui_list, 10, y, tab_w, 28, "SCENE", set_tab, "SCENE", True, grp_tabs, state.active_tab=="SCENE", COL_TAB_INA)
    b1.corners = {'tl': 4, 'bl': 4, 'tr': 0, 'br': 0}
    
    # OBJECT
    b2 = btn(ui_list, 10 + tab_w, y, tab_w, 28, "OBJECT", set_tab, "OBJECT", True, grp_tabs, state.active_tab=="OBJECT", COL_TAB_INA)
    b2.corners = {} # Carré
    
    # RENDER
    b3 = btn(ui_list, 10 + 2*tab_w, y, tab_w, 28, "RENDER", set_tab, "RENDER", True, grp_tabs, state.active_tab=="RENDER", COL_TAB_INA)
    b3.corners = {'tl': 0, 'bl': 0, 'tr': 4, 'br': 4}
    
    return y + 40 # Retourne la position Y de départ pour le contenu des onglets