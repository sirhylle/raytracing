from ..ui_core import *

def build(ui_list, start_y, state, engine, on_start_render):
    ys = start_y
    
    # --- ACCORDION HELPER (Identical to tab_scene) ---
    def draw_header(title, section_name, toggle_switch=None):
        nonlocal ys
        def toggle(): state.toggle_accordion("RENDER", section_name)
        is_open = state.is_accordion_open("RENDER", section_name)

        ui_list.append(HeaderBar(VIEW_W + 5, ys-4, PANEL_W - 10, 26, COL_HEADER, callback=toggle))
        lbl(ui_list, 15, ys, title, 14, COL_ACCENT)
        lbl(ui_list, PANEL_W - 25, ys-2, "-", 16, COL_TEXT_DIM) if is_open else lbl(ui_list, PANEL_W - 26, ys-1, "+", 16, COL_TEXT_DIM)
        
        if toggle_switch:
            sw_txt, sw_cb, sw_active = toggle_switch
            col = COL_BTN_ACT if sw_active else None
            btn(ui_list, PANEL_W - 85, ys-2, 40, 20, sw_txt, sw_cb, col_ov=col)

        ys += 30
        return is_open

    # Config access helpers (with getattr/setattr to handle optional params)
    def get_c(k, default): return getattr(state.conf, k, default)
    def set_c(k, v): setattr(state.conf, k, v); state.dirty = True ; state.needs_ui_rebuild = True

    # ==================== 1. OUTPUT (Résolution) ====================
    if draw_header("OUTPUT", "OUTPUT"):
        # W x H
        lbl(ui_list, 10, ys+4, "Resolution", 12, COL_TEXT_DIM)
        
        # W
        ui_list.append(NumberField(VIEW_W+80, ys, 40, 22, 
                                   lambda: state.conf.width, 
                                   lambda v: state.update_resolution(v, state.conf.height), fmt="{:.0f}"))
        lbl(ui_list, 125, ys+4, "x", 12)
        # H
        ui_list.append(NumberField(VIEW_W+135, ys, 40, 22, 
                                   lambda: state.conf.height, 
                                   lambda v: state.update_resolution(state.conf.width, v), fmt="{:.0f}"))
        ys += 30
        
        # Presets
        def set_preset(w, h): state.update_resolution(w, h)
        bw = (PANEL_W - 30) // 4
        btn(ui_list, 10, ys, bw, 20, "720p", lambda: set_preset(1280, 720))
        btn(ui_list, 10+bw+3, ys, bw, 20, "4:3", lambda: set_preset(1440, 1080))
        btn(ui_list, 10+2*(bw+3), ys, bw, 20, "1080p", lambda: set_preset(1920, 1080))
        btn(ui_list, 10+3*(bw+3), ys, bw, 20, "4k", lambda: set_preset(3840, 2160))
        ys += 40
        
        # --- Output Options (Save Raw / Stamp) ---
        # Checkboxes
        is_raw = get_c('save_raw', False)
        btn(ui_list, 10, ys, 140, 24, "Save Raw", lambda: set_c('save_raw', not is_raw), toggle=True, active=is_raw)
        
        is_stamp = get_c('param_stamp', False)
        btn(ui_list, 160, ys, 140, 24, "Stamp Params", lambda: set_c('param_stamp', not is_stamp), toggle=True, active=is_stamp)
        
        ys += 40

    # ==================== 2. QUALITY ====================
    if draw_header("QUALITY", "QUALITY"):
        # SPP
        lbl(ui_list, 10, ys+4, "Max Samples", 12, COL_TEXT_DIM)
        ui_list.append(NumberField(VIEW_W+100, ys, 60, 22, 
                                   lambda: state.conf.spp, lambda v: set_c('spp', int(v)), fmt="{:.0f}"))
        ys += 30
        
        # Depth
        lbl(ui_list, 10, ys+4, "Max Bounces", 12, COL_TEXT_DIM)
        ui_list.append(NumberField(VIEW_W+100, ys, 60, 22, 
                                   lambda: state.conf.depth, lambda v: set_c('depth', int(v)), fmt="{:.0f}"))
        ys += 30

        # Offline Sampler
        lbl(ui_list, 10, ys+3, "Offline Sampler", 12, COL_TEXT_DIM)
        grp_samp = []
        def set_render_samp(v): state.render_sampler = v
        # 0=Random, 1=Sobol
        btn(ui_list, 100, ys, 80, 22, "Random", set_render_samp, 0, True, grp_samp, (state.render_sampler==0)).corners={'tl':4, 'bl':4}
        btn(ui_list, 180, ys, 80, 22, "Sobol",  set_render_samp, 1, True, grp_samp, (state.render_sampler==1)).corners={'tr':4, 'br':4}
        ys += 40

    # ==================== 3. ANIMATION (New) ====================
    # Use a switch in the header to toggle animation
    def toggle_anim(): 
        current = get_c('animate', False)
        set_c('animate', not current)

    is_anim = get_c('animate', False)
    if draw_header("ANIMATION", "ANIMATION", ("ON" if is_anim else "OFF", toggle_anim, is_anim)):
        if is_anim:
            # Frames
            lbl(ui_list, 10, ys+4, "Total Frames", 12, COL_TEXT_DIM)
            ui_list.append(NumberField(VIEW_W+100, ys, 60, 22, 
                                       lambda: get_c('frames', 120), lambda v: set_c('frames', int(v)), fmt="{:.0f}"))
            ys += 30

            # FPS
            lbl(ui_list, 10, ys+4, "Framerate", 12, COL_TEXT_DIM)
            ui_list.append(NumberField(VIEW_W+100, ys, 60, 22, 
                                       lambda: get_c('fps', 24), lambda v: set_c('fps', int(v)), fmt="{:.0f}"))
            ys += 30
            
            # Turntable Radius (Distance caméra pour le tour)
            lbl(ui_list, 10, ys+4, "Turntable Dist", 12, COL_TEXT_DIM)
            ui_list.append(NumberField(VIEW_W+100, ys, 60, 22, 
                                       lambda: get_c('radius', 0.0), lambda v: set_c('radius', v), fmt="{:.2f}"))
            ys += 30
            
            lbl(ui_list, 10, ys, "Note: Rotating Camera around (0,0,0)", 11, (100,100,100))
            ys += 40
        else:
            lbl(ui_list, 10, ys, "Render single still image.", 11, (100,100,100))
            ys += 40

    # ==================== 4. SYSTEM / TECH (New) ====================
    if draw_header("SYSTEM", "SYSTEM"):
        # Threads
        lbl(ui_list, 10, ys+4, "CPU Threads", 12, COL_TEXT_DIM)
        # 0 = Auto
        ui_list.append(NumberField(VIEW_W+100, ys, 60, 22, 
                                   lambda: get_c('threads', 0), lambda v: set_c('threads', int(v)), fmt="{:.0f}"))
        lbl(ui_list, 170, ys+4, "(0=Auto)", 11, (100,100,100))
        ys += 30

        # Leave Cores
        lbl(ui_list, 10, ys+4, "Leave Cores", 12, COL_TEXT_DIM)
        ui_list.append(NumberField(VIEW_W+100, ys, 60, 22, 
                                   lambda: get_c('leave_cores', 0), lambda v: set_c('leave_cores', int(v)), fmt="{:.0f}"))
        lbl(ui_list, 170, ys+4, "(Keep n cores free)", 11, (100,100,100))
        ys += 30

        # Epsilon
        lbl(ui_list, 10, ys+4, "Ray Epsilon", 12, COL_TEXT_DIM)
        ui_list.append(NumberField(VIEW_W+100, ys, 60, 22, 
                                   lambda: state.epsilon, lambda v: state.update_epsilon(v), fmt="{:.4f}"))
        lbl(ui_list, 170, ys+4, "(Bias, decrease if light bleeding)", 11, (100,100,100))
        ys += 30

        # Firefly Clamp
        lbl(ui_list, 10, ys+4, "Firefly Clamp", 12, COL_TEXT_DIM)
        ui_list.append(NumberField(VIEW_W+100, ys, 60, 22, 
                                   lambda: state.firefly_clamp, lambda v: state.update_firefly_clamp(v), fmt="{:.1f}"))
        lbl(ui_list, 170, ys+4, "(Max Intensity)", 11, (100,100,100))
        ys += 40
        
        
        # --- BVH Strategy ---
        # Place this BEFORE Raw/Stamp buttons
        import cpp_engine
        lbl(ui_list, 10, ys+3, "BVH Strategy", 12, COL_TEXT_DIM)
        
        # Init state if needed
        if not hasattr(state, 'bvh_type'): state.bvh_type = "Midpoint"
        
        def set_bvh(mode_str):
            state.bvh_type = mode_str
            m = cpp_engine.SplitMethod.SAH if mode_str == "SAH" else cpp_engine.SplitMethod.Midpoint
            engine.set_build_method(m)
        
        grp_bvh = []
        # Buttons: Midpoint | SAH
        # Use toggle=True so they stay "pressed" (blue) if active
        btn(ui_list, 100, ys, 80, 22, "Midpoint", lambda: set_bvh("Midpoint"), toggle=True, grp=grp_bvh, active=(state.bvh_type == "Midpoint"))\
           .corners={'tl':4, 'bl':4}
        btn(ui_list, 180, ys, 80, 22, "SAH",      lambda: set_bvh("SAH"),      toggle=True, grp=grp_bvh, active=(state.bvh_type == "SAH"))\
           .corners={'tr':4, 'br':4}
        ys += 22
        lbl(ui_list, 10, ys+4, "(Midpoint best for one complex mesh, SAH for many small objects)", 11, (100,100,100))
        
        ys += 40

    # ==================== 5. VIEWPORT PREVIEW ====================
    if draw_header("PREVIEW", "PREVIEW"):
        lbl(ui_list, 10, ys+3, "Scale", 12, COL_TEXT_DIM)
        def set_res(v): state.res_auto = (v=='AUTO'); state.res_scale = v if v!='AUTO' else 1; state.dirty = True
        grp_res = [] # Not really used for button grouping logic here, custom manual logic below
        
        # Row 1: Auto Only (Full Width)
        btn(ui_list, 100, ys, 180, 22, "Auto (Dynamic)", set_res, 'AUTO', True, grp_res, state.res_auto).corners={'tl':4, 'bl':4, 'tr':4, 'br':4}
        ys += 26
        
        # Row 2: Manual Ratios (1:4, 1:2, 1:1, 2:1)
        lbl(ui_list, 10, ys+3, "Manual", 12, COL_TEXT_DIM)
        
        # 4 boutons répartis sur 130px de large
        w_btn = 45
        x = 100
        btn(ui_list, x,    ys, w_btn, 22, "1:4", set_res, 4,   True, grp_res, (not state.res_auto and state.res_scale==4)).corners={'tl':4, 'bl':4}
        btn(ui_list, x+w_btn, ys, w_btn, 22, "1:2", set_res, 2,   True, grp_res, (not state.res_auto and state.res_scale==2)).corners={}
        btn(ui_list, x+(2*w_btn), ys, w_btn, 22, "1:1", set_res, 1,   True, grp_res, (not state.res_auto and state.res_scale==1)).corners={}
        btn(ui_list, x+(3*w_btn), ys, w_btn, 22, "2:1", set_res, 0.5, True, grp_res, (not state.res_auto and state.res_scale==0.5)).corners={'tr':4, 'br':4}
        
        ys += 40

        # Depth (Bounces)
        lbl(ui_list, 10, ys+3, "Bounces", 12, COL_TEXT_DIM)
        
        # Helper to update depth (with int cast)
        def set_depth(d): 
             d_int = int(d)
             if state.preview_depth != d_int:
                 state.preview_depth = d_int
                 if hasattr(engine, 'reset_accumulation'): engine.reset_accumulation()
                 state.accum_spp = 0
                 state.dirty = True

        # Slider 1 to 30 (Log power 1.0 = Linear is fine for small range, or 1.5 for precision at low values)
        # Using "center" display for value
        ui_list.append(Slider(VIEW_W+100, ys, 180, 22, 1, 30, lambda: state.preview_depth, set_depth, power=1.5))

        ys += 40

        # Preview Sampler
        lbl(ui_list, 10, ys+3, "Sampler", 12, COL_TEXT_DIM)
        grp_psamp = []
        def set_prev_samp(v): 
            state.preview_sampler = v
            state.accum_spp = 0
            if hasattr(engine, 'reset_accumulation'): engine.reset_accumulation()
            state.dirty = True
        
        btn(ui_list, 100, ys, 90, 22, "Random", set_prev_samp, 0, True, grp_psamp, (state.preview_sampler==0)).corners={'tl':4, 'bl':4}
        btn(ui_list, 190, ys, 90, 22, "Sobol",  set_prev_samp, 1, True, grp_psamp, (state.preview_sampler==1)).corners={'tr':4, 'br':4}

        ys += 40

    # ==================== FOOTER ACTION ====================
    # Leave some space before the big button
    # ys += 10
    # btn(ui_list, 10, ys, PANEL_W - 20, 40, "START RENDER", on_start_render, col_ov=(40, 100, 40), bd_ov=(80, 160, 80))
    # lbl(ui_list, 0, ys+45, "Will freeze editor until finished.", 11, COL_TEXT_DIM, align="center", width=PANEL_W)
    status_bar_height = 30 
    btn_h = 45
    margin = 10
    final_y = WIN_H - status_bar_height - btn_h - margin
    btn(ui_list, 10, final_y, PANEL_W - 20, btn_h, "START RENDER", on_start_render, col_ov=(40, 100, 40), bd_ov=(80, 160, 80))
    #lbl(ui_list, 0, final_y + btn_h + 2, "Will freeze editor until finished.", 11, COL_TEXT_DIM, align="center", width=PANEL_W)