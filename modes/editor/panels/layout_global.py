import pygame
from ..ui_core import *

def build_header(ui_list, state):
    y = 5 
    
    # --- LIGNE 1 : FICHIER (Gauche) + MODES DE VUE (Droite) ---
    
    # 1. Fichier
    b_save = btn(ui_list, 10, y, 50, 22, "SAVE", state.save_scene_dialog, col_ov=(45, 45, 45))
    b_save.corners = {'tl': 4, 'bl': 4, 'tr': 0, 'br': 0}
    b_load = btn(ui_list, 60, y, 50, 22, "LOAD", state.load_scene_dialog, col_ov=(45, 45, 45))
    b_load.corners = {'tl': 0, 'bl': 0, 'tr': 4, 'br': 4}
    
    # 2. Modes de Vue (Alignés à droite)
    # On calcule pour coller au bord droit : (Largeur Panel) - (3 boutons de 55px) - Marge
    mode_w = 55
    start_x = PANEL_W - (3 * mode_w) - 10
    
    def set_mode(m):
        # STABILIZATION: If switching TO Raytracing from other modes, force low resolution (Scale 4)
        # to prevent "blinking" caused by immediate high-res render -> auto-downscale loop.
        if m == 2 and state.preview_mode != 2:
            if state.res_auto:
                state.res_scale = 4 # Start rough, let auto-scaler improve it
                
        state.preview_mode = m
        state.dirty = True

    grp_mode = []
    
    b1 = btn(ui_list, start_x, y, mode_w, 22, "Norm", set_mode, 0, True, grp_mode, state.preview_mode==0)
    b1.corners = {'tl': 4, 'bl': 4, 'tr': 0, 'br': 0}
    
    b2 = btn(ui_list, start_x + mode_w, y, mode_w, 22, "Clay", set_mode, 1, True, grp_mode, state.preview_mode==1)
    b2.corners = {} 
    
    b3 = btn(ui_list, start_x + 2*mode_w, y, mode_w, 22, "Ray", set_mode, 2, True, grp_mode, state.preview_mode==2)
    b3.corners = {'tl': 0, 'bl': 0, 'tr': 4, 'br': 4}

    ui_list.append(Separator(y + 15, color=(65, 65, 65)))
    
    y += 60

    # --- LIGNE 2 : ONGLETS (Toute largeur) ---
    def set_tab(t): state.set_active_tab(t)
    grp_tabs = []
    
    tabs = ["SCENE", "OBJECT", "CREATE", "RENDER"]
    tab_w = (PANEL_W - 20) / len(tabs) 
    curr_x = 10
    
    for i, t_name in enumerate(tabs):
        corners = {}
        if i == 0: corners = {'tl': 4, 'bl': 0, 'tr': 0, 'br': 0}
        elif i == len(tabs)-1: corners = {'tl': 0, 'bl': 0, 'tr': 4, 'br': 0}
        
        w = tab_w if i < len(tabs)-1 else (PANEL_W - 20) - (int(tab_w) * (len(tabs)-1))
        
        b = btn(ui_list, curr_x, y, int(w), 26, t_name, set_tab, t_name, True, grp_tabs, state.active_tab==t_name, COL_TAB_INA)
        b.corners = corners
        curr_x += int(w)

    return y + 35 

def draw_footer_status(screen, fonts, state):
    """Footer technique : FPS | SPP | Résolution"""
    h = 24 
    y = WIN_H - h
    
    # Fond
    pygame.draw.rect(screen, (25, 25, 25), (VIEW_W, y, PANEL_W, h))
    pygame.draw.line(screen, (60, 60, 60), (VIEW_W, y), (WIN_W, y))
    
    f = fonts.get(12)
    col = (160, 160, 160)
    
    # 1. FPS (Gauche) - On lit la valeur stockée dans state
    fps_txt = f"FPS: {int(state.current_fps):.0f}"
    
    # Scale Text
    s = state.res_scale
    if s < 0.9: scale_txt = "2:1"
    else: scale_txt = f"1:{int(s)}"
    
    label_left = f"{fps_txt}   |   Scale: {scale_txt}"
    screen.blit(f.render(label_left, True, col), (VIEW_W + 10, y + 5))
    
    # 2. Infos Rendu (Droite)
    info_str = f"SPP: {state.accum_spp}   |   {state.conf.width}x{state.conf.height}"
    i_surf = f.render(info_str, True, col)
    i_rect = i_surf.get_rect(topright=(WIN_W - 10, y + 5))
    screen.blit(i_surf, i_rect)