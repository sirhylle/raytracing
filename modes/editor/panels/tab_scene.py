from ..ui_core import *

def build(ui_list, start_y, state, engine):
    ys = start_y

    def draw_header(title, section_name, toggle_switch=None):
        nonlocal ys
        
        def toggle():
            state.toggle_accordion("SCENE", section_name)

        # Vérifie si CETTE section est celle active dans l'onglet SCENE
        is_open = state.is_accordion_open("SCENE", section_name)

        ui_list.append(HeaderBar(VIEW_W + 5, ys - 4, PANEL_W - 10, 26, COL_HEADER, callback=toggle))
        lbl(ui_list, 15, ys, title, 14, COL_ACCENT)
        
        lbl(ui_list, PANEL_W - 25, ys-2, "-", 16, COL_TEXT_DIM) if is_open else lbl(ui_list, PANEL_W - 26, ys-1, "+", 16, COL_TEXT_DIM)
        
        if toggle_switch:
            sw_txt, sw_cb, sw_active = toggle_switch
            # Si actif -> Bleu, sinon -> Gris standard (None)
            col = COL_BTN_ACT if sw_active else None
            btn(ui_list, PANEL_W - 85, ys-2, 40, 20, sw_txt, sw_cb, col_ov=col)

        ys += 30
        return is_open

    def set_env(attr, val):
        setattr(state, attr, val)
        state.update_environment(engine)

    # --- 1. CAMERA ---
    if draw_header("CAMERA", "CAMERA"):
        def adj(attr, d): setattr(state, attr, getattr(state, attr)+d); state.dirty=True
        def set_v(attr, v): setattr(state, attr, v); state.dirty=True
        
        # FOV
        lbl(ui_list, 10, ys+2, "FOV", 14)
        btn(ui_list, 80, ys, 30, 22, "-", lambda: adj('vfov', -5))
        ui_list.append(NumberField(VIEW_W+115, ys, 40, 22, lambda: state.vfov, lambda v: set_v('vfov', v)))
        btn(ui_list, 160, ys, 30, 22, "+", lambda: adj('vfov', 5))
        ys += 35
        # Focus
        lbl(ui_list, 10, ys+2, "Focus Dist", 14)
        btn(ui_list, 80, ys, 30, 22, "-", lambda: adj('focus_dist', -0.5))
        ui_list.append(NumberField(VIEW_W+115, ys, 40, 22, lambda: state.focus_dist, lambda v: set_v('focus_dist', v)))
        btn(ui_list, 160, ys, 30, 22, "+", lambda: adj('focus_dist', 0.5))
        def toggle_pick(): 
            state.picking_focus = not state.picking_focus
        btn_pick = Button(VIEW_W+195, ys, 45, 22, "Pick", toggle_pick)
        btn_pick.active = state.picking_focus # S'allume si on est en mode picking
        ui_list.append(btn_pick)
        ys += 38
        # Aperture
        #lbl(ui_list, 10, ys+4, "Aperture", 12)
        #btn(ui_list, 80, ys, 30, 22, "-", lambda: adj('aperture', -0.02))
        #ui_list.append(NumberField(VIEW_W+115, ys, 40, 22, lambda: state.aperture, lambda v: set_v('aperture', v)))
        #btn(ui_list, 160, ys, 30, 22, "+", lambda: adj('aperture', 0.02))
        slider_x_aperture = 80
        slider_w_aperture = PANEL_W - slider_x_aperture - 10
        lbl(ui_list, 10, ys-1, "Aperture", 14)
        ui_list.append(Slider(VIEW_W + slider_x_aperture, ys, slider_w_aperture, 16, 0.0, 2.0, 
                                  lambda: state.aperture, 
                                  lambda v: set_v('aperture', v), 
                                  power=3.0))
        ys += 30
        ui_list.append(Separator(ys, "NAVIGATION"))
        ys += 25

        lbl(ui_list, 15, ys, "Rotate : Right Click + Drag", 11, COL_TEXT_DIM)
        lbl(ui_list, 180, ys, "Pan : Middle Click + Drag", 11, COL_TEXT_DIM)
        ys += 16
        lbl(ui_list, 15, ys, "Move : Arrow Keys", 11, COL_TEXT_DIM)
        lbl(ui_list, 180, ys, "Lift : Page Up / Down", 11, COL_TEXT_DIM)
        ys += 16
        lbl(ui_list, 15, ys, "Zoom : Mouse Wheel", 11, COL_TEXT_DIM)
        lbl(ui_list, 180, ys, "Pick Focus : L + Left Click", 11, COL_TEXT_DIM)

        ys += 30
        
    else: ys += 5

    # --- 2. ENVIRONMENT ---
    if draw_header("ENVIRONMENT", "ENVIRONMENT"):
        btn(ui_list, 10, ys, 290, 24, "LOAD NEW HDR MAP...", lambda: state.load_new_env_map(engine))
        ys += 30
        
        lbl(ui_list, 10, ys, "Rotation", 12, COL_TEXT_DIM)
        ui_list.append(Slider(VIEW_W+80, ys, 210, 14, 0.0, 360.0, lambda: state.env_rotation, lambda v: set_env('env_rotation', v)))
        ys += 25
        
        lbl(ui_list, 10, ys, "Cam Direct", 12, COL_TEXT_DIM)
        ui_list.append(Slider(VIEW_W+80, ys, 210, 14, 0.0, 20.0, lambda: state.env_direct_level, lambda v: set_env('env_direct_level', v), power=1.5))
        ys += 25
        
        col_lbl = COL_TEXT_DIM if not state.sun_enabled else (80, 80, 80)
        lbl(ui_list, 10, ys, "Global Light", 12, col_lbl)
        sl = Slider(VIEW_W+80, ys, 210, 14, 0.0, 20.0, lambda: state.env_light_level, lambda v: set_env('env_light_level', v), power=3)
        sl.enabled = not state.sun_enabled
        ui_list.append(sl)
        ys += 25
        
        lbl(ui_list, 10, ys, "Reflections", 12, COL_TEXT_DIM)
        ui_list.append(Slider(VIEW_W+80, ys, 210, 14, 0.0, 20.0, lambda: state.env_indirect_level, lambda v: set_env('env_indirect_level', v), power=1.5))
        ys += 35
    else: ys += 5

    # --- 3. AUTO SUN ---
    def toggle_sun():
        state.sun_enabled = not state.sun_enabled
        state.update_environment(engine)
        state.needs_ui_rebuild = True
    
    sw_params = ("ON" if state.sun_enabled else "OFF", toggle_sun, state.sun_enabled)
    if draw_header("AUTO SUN", "SUN", sw_params):
        if state.sun_id != -1:
            lbl(ui_list, 10, ys, "Sun Power", 12, COL_TEXT_DIM)
            ui_list.append(Slider(VIEW_W+80, ys, 210, 14, 0.0, 2000.0, lambda: state.sun_intensity, lambda v: set_env('sun_intensity', v), power=2))
            ys += 20
            
            lbl(ui_list, 10, ys, "Ambience", 12, COL_TEXT_DIM)
            ui_list.append(Slider(VIEW_W+80, ys, 210, 14, 0.0, 10.0, lambda: state.auto_sun_env_level, lambda v: set_env('auto_sun_env_level', v), power=3))
            ys += 20

            lbl(ui_list, 10, ys, "Softness", 12, COL_TEXT_DIM)
            ui_list.append(Slider(VIEW_W+80, ys, 210, 14, 1.0, 200.0, lambda: state.sun_radius, lambda v: set_env('sun_radius', v)))
            ys += 20

            lbl(ui_list, 10, ys, "Distance", 12, COL_TEXT_DIM)
            ui_list.append(Slider(VIEW_W+80, ys, 210, 14, 10.0, 5000.0, lambda: state.sun_dist, lambda v: set_env('sun_dist', v)))
            ys += 20

            # Ligne de séparation explicite
            ys += 15
            ui_list.append(Separator(ys, "Envt Light Clipping"))
            #lbl(ui_list, 10, ys, "-"*22 + " Enviro Clipping " + "-"*22, 12, (80, 80, 80))
            ys += 25
            
            def toggle_clip():
                set_env('env_clipping_enabled', not state.env_clipping_enabled)
                state.needs_ui_rebuild = True # FORCE le rafraîchissement immédiat de l'UI
                
            is_on = state.env_clipping_enabled
            col_btn = (58, 110, 165) if is_on else None 
            
            # Layout compact : "Dynamic Clipping : [ ON ]"
            lbl(ui_list, 10, ys, "Dynamic Clipping", 12, COL_TEXT)
            ui_list.append(Button(VIEW_W+240, ys, 50, 16, "ON" if is_on else "OFF", 
                                  callback=toggle_clip, color_override=col_btn))
            ys += 20
            
            if state.env_clipping_enabled:
                lbl(ui_list, 10, ys, "Level (x)", 12, COL_TEXT_DIM)
                ui_list.append(Slider(VIEW_W+80, ys, 210, 14, 0.0, 100.0, lambda: state.env_clipping_multiplier, lambda v: set_env('env_clipping_multiplier', v), power=3))
                ys += 20
        else:
            lbl(ui_list, 10, ys, "Enable Auto Sun to generate sun light", 12, (100,100,100))
            ys += 20