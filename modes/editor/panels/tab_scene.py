from ..ui_core import *

def build(ui_list, start_y, state, engine):
    ys = start_y

    def draw_header(title, section_name, toggle_switch=None):
        nonlocal ys
        # Vérifie si CETTE section est celle active dans l'onglet SCENE
        is_open = state.is_accordion_open("SCENE", section_name)
        
        lbl(ui_list, 10, ys, title, 14, COL_ACCENT)
        
        def toggle():
            state.toggle_accordion("SCENE", section_name)
            # Pas besoin de rappeler build(), la boucle main le fera car l'UI est reconstruite à chaque frame/event
        
        txt = "-" if is_open else "+"
        btn(ui_list, PANEL_W - 35, ys-2, 24, 20, txt, toggle)
        
        if toggle_switch:
            sw_txt, sw_cb, sw_active = toggle_switch
            # Si actif -> Bleu, sinon -> Gris standard (None)
            col = COL_BTN_ACT if sw_active else None
            btn(ui_list, PANEL_W - 85, ys-2, 40, 20, sw_txt, sw_cb, col_ov=col)

        ys += 25
        return is_open

    def set_env(attr, val):
        setattr(state, attr, val)
        state.update_environment(engine)

    # --- 1. CAMERA ---
    if draw_header("CAMERA", "CAMERA"):
        def adj(attr, d): setattr(state, attr, getattr(state, attr)+d); state.dirty=True
        def set_v(attr, v): setattr(state, attr, v); state.dirty=True
        
        # FOV
        lbl(ui_list, 10, ys+4, "FOV", 12)
        btn(ui_list, 80, ys, 30, 22, "-", lambda: adj('vfov', -5))
        ui_list.append(NumberField(VIEW_W+115, ys, 40, 22, lambda: state.vfov, lambda v: set_v('vfov', v)))
        btn(ui_list, 160, ys, 30, 22, "+", lambda: adj('vfov', 5))
        ys += 28
        # Aperture
        lbl(ui_list, 10, ys+4, "Aperture", 12)
        btn(ui_list, 80, ys, 30, 22, "-", lambda: adj('aperture', -0.02))
        ui_list.append(NumberField(VIEW_W+115, ys, 40, 22, lambda: state.aperture, lambda v: set_v('aperture', v)))
        btn(ui_list, 160, ys, 30, 22, "+", lambda: adj('aperture', 0.02))
        ys += 28
        # Focus
        lbl(ui_list, 10, ys+4, "Focus Dist", 12)
        btn(ui_list, 80, ys, 30, 22, "-", lambda: adj('focus_dist', -0.5))
        ui_list.append(NumberField(VIEW_W+115, ys, 40, 22, lambda: state.focus_dist, lambda v: set_v('focus_dist', v)))
        btn(ui_list, 160, ys, 30, 22, "+", lambda: adj('focus_dist', 0.5))
        ys += 35
    else: ys += 5

    # --- 2. ENVIRONMENT ---
    if draw_header("ENVIRONMENT", "ENVIRONMENT"):
        btn(ui_list, 10, ys, 290, 24, "LOAD NEW HDR MAP...", lambda: state.load_new_env_map(engine))
        ys += 30
        
        lbl(ui_list, 10, ys, lambda: f"Rotation: {state.env_rotation:.0f}°", 12, COL_TEXT_DIM)
        ui_list.append(Slider(VIEW_W+90, ys, 210, 14, 0.0, 360.0, lambda: state.env_rotation, lambda v: set_env('env_rotation', v)))
        ys += 25
        
        lbl(ui_list, 10, ys, lambda: f"Cam Direct: {state.env_direct_level:.2f}", 12, COL_TEXT_DIM)
        ui_list.append(Slider(VIEW_W+90, ys, 210, 14, 0.0, 10.0, lambda: state.env_direct_level, lambda v: set_env('env_direct_level', v)))
        ys += 25
        
        col_lbl = COL_TEXT_DIM if not state.sun_enabled else (80, 80, 80)
        lbl(ui_list, 10, ys, lambda: f"Global Light: {state.env_light_level:.2f}", 12, col_lbl)
        sl = Slider(VIEW_W+90, ys, 210, 14, 0.0, 15.0, lambda: state.env_light_level, lambda v: set_env('env_light_level', v))
        sl.enabled = not state.sun_enabled
        ui_list.append(sl)
        ys += 25
        
        lbl(ui_list, 10, ys, lambda: f"Reflections: {state.env_indirect_level:.2f}", 12, COL_TEXT_DIM)
        ui_list.append(Slider(VIEW_W+90, ys, 210, 14, 0.0, 15.0, lambda: state.env_indirect_level, lambda v: set_env('env_indirect_level', v)))
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
            lbl(ui_list, 10, ys, lambda: f"Sun Power: {state.sun_intensity:.1f}", 12, COL_TEXT_DIM)
            ui_list.append(Slider(VIEW_W+90, ys, 210, 14, 0.0, 500.0, lambda: state.sun_intensity, lambda v: set_env('sun_intensity', v)))
            ys += 20
            
            lbl(ui_list, 10, ys, lambda: f"Ambience: {state.auto_sun_env_level:.3f}", 12, COL_TEXT_DIM)
            ui_list.append(Slider(VIEW_W+90, ys, 210, 14, 0.0, 10.0, lambda: state.auto_sun_env_level, lambda v: set_env('auto_sun_env_level', v)))
            ys += 20

            lbl(ui_list, 10, ys, lambda: f"Softness: {state.sun_radius:.1f}", 12, COL_TEXT_DIM)
            ui_list.append(Slider(VIEW_W+90, ys, 210, 14, 1.0, 200.0, lambda: state.sun_radius, lambda v: set_env('sun_radius', v)))
            ys += 20

            lbl(ui_list, 10, ys, lambda: f"Distance: {state.sun_dist:.0f}", 12, COL_TEXT_DIM)
            ui_list.append(Slider(VIEW_W+90, ys, 210, 14, 10.0, 5000.0, lambda: state.sun_dist, lambda v: set_env('sun_dist', v)))
            ys += 20
        else:
            lbl(ui_list, 10, ys, "Enable Auto Sun to generate sun light", 12, (100,100,100))
            ys += 20