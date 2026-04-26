from ..ui_core import *

def build(ui_list, start_y, state, engine):
    # --- 1. EMPTY SELECTION MANAGEMENT ---
    if state.selected_id == -1:
        lbl(ui_list, 10, start_y, "No Selection, Left Click on an object", 14, COL_TEXT_DIM)
        return

    ys = start_y
    sel_data = state.get_selected_info()
    obj_name = sel_data.get('name', sel_data.get('type', 'Unknown'))

    # --- SECTION HELPER (Moved to beginning for immediate use) ---
    def draw_section_header(title, accord_key):
        """Draws a title bar with included toggle."""
        nonlocal ys
        is_open = state.is_accordion_open("OBJECT", accord_key)
        
        def toggle():
            state.toggle_accordion("OBJECT", accord_key)

        # 1. Dark Background
        ui_list.append(HeaderBar(VIEW_W + 5, ys-4, PANEL_W - 10, 26, COL_HEADER, callback=toggle))
        
        # 2. Title
        lbl(ui_list, 15, ys, title, 14, COL_ACCENT)
        
        # 3. Toggle Button (in the bar)        
        lbl(ui_list, PANEL_W - 25, ys-2, "-", 16, COL_TEXT_DIM) if is_open else lbl(ui_list, PANEL_W - 26, ys-1, "+", 16, COL_TEXT_DIM)
        
        ys += 30 
        return is_open

    # ==================== BLOCK 1 : SELECTION (Info, Axes, Actions) ====================
    if draw_section_header("SELECTION", "SELECTION"):
        
        # A. Line 1 : Object Name (Left) & Axes (Right)
        
        # 1. Name
        lbl(ui_list, 10, ys, f"ID {state.selected_id}: {obj_name}", 14, COL_TEXT)

        # 2. Axis Selector
        def set_axis(m): 
             state.axis_mode = m
             # Changing gizmo axis -> Only visual repaint, no render reset
             state.needs_repaint = True
             
        grp_axis = []
        btn_w, btn_h = 35, 20
        start_x = PANEL_W - 10 - (3 * btn_w) # Calé à droite
        
        # OFF
        b_off = btn(ui_list, start_x, ys-1, btn_w, btn_h, "OFF", set_axis, "NONE", True, grp_axis, state.axis_mode=="NONE")
        b_off.corners = {'tl': 4, 'bl': 4, 'tr': 0, 'br': 0}
        
        # LOC
        b_loc = btn(ui_list, start_x+btn_w, ys-1, btn_w, btn_h, "LOC", set_axis, "LOCAL", True, grp_axis, state.axis_mode=="LOCAL")
        b_loc.corners = {} 
        
        # GLO
        b_glo = btn(ui_list, start_x+2*btn_w, ys-1, btn_w, btn_h, "GLO", set_axis, "GLOBAL", True, grp_axis, state.axis_mode=="GLOBAL")
        b_glo.corners = {'tl': 0, 'bl': 0, 'tr': 4, 'br': 4}
        
        # Label "Axes"
        lbl(ui_list, start_x - 35, ys+2, "Axes", 12, COL_TEXT_DIM)
        
        ys += 30 # Line jump after Axes

        # B. Line 2 : Actions (Delete, Duplicate)
        
        def duplicate_obj():
            state.duplicate_selection(engine)
            # state.duplicate_selection handles flags (render reset + ui rebuild)
            
        # Duplicate Button
        btn(ui_list, 10, ys, 300, 28, "DUPLICATE OBJECT", duplicate_obj)

        ys += 30

        # 1. Delete
        def delete_obj():
            oid = state.selected_id
            engine.remove_instance(oid)
            if oid in state.builder.registry: del state.builder.registry[oid]
            state.selected_id = -1
            state.set_active_tab("SCENE") # Return to scene after deletion
            # set_active_tab sets needs_ui_rebuild
            # Object removal -> Needs render reset
            state.needs_render_reset = True
            
        # Button Delete (Red)
        btn(ui_list, 10, ys, 300, 28, "DELETE OBJECT", delete_obj, col_ov=(160, 50, 50))
        
        ys += 40
        ui_list.append(Separator(ys, "ACTIONS"))
        ys += 25

        lbl(ui_list, 15, ys, "Move : Left Click + Drag", 11, COL_TEXT_DIM)
        lbl(ui_list, 180, ys, "Lift : L + Left Click + Drag", 11, COL_TEXT_DIM)
        ys += 16
        lbl(ui_list, 15, ys, "Rot : R + Left Click + Drag", 11, COL_TEXT_DIM)
        lbl(ui_list, 180, ys, "Scale : S + Left Click + Drag", 11, COL_TEXT_DIM)

        ys += 30

    # ==================== BLOCK 2 : TRANSFORMS ====================
    if draw_section_header("TRANSFORMS", "TRANSFORMS"):
        
        # A. Gizmos
        def set_gizmo(g): 
             state.gizmo_mode = g
             # Gizmo change -> Visual repaint only
             state.needs_repaint = True
             
        grp_gizmo = []
        bw, gap = 58, 5
        total_w = (4 * bw) + (3 * gap)
        x = (PANEL_W - total_w) // 2
        
        modes = ["MOVE", "LIFT", "ROT", "SCALE"]
        for m in modes:
            btn(ui_list, x, ys, bw, 24, m, set_gizmo, m, True, grp_gizmo, state.gizmo_mode==m)
            x += bw + gap
        ys += 35

        # B. Numeric Fields
        def get_v(prop, axis): d=state.get_selected_info(); return d[prop][axis] if d else 0.0
        def set_v(val, prop, axis): 
            d=state.get_selected_info(); 
            if d: 
                 d[prop][axis]=val
                 state.update_transform(engine)
                 # update_transform sets needs_render_reset + needs_repaint
        
        props = ["pos", "rot", "scale"]
        names = ["Position", "Rotation", "Scale"]
        axis_colors = [(200, 80, 80), (80, 200, 80), (80, 80, 220)]
        axis_labels = ["X", "Y", "Z"]
        field_w = 55 
        start_x_fields = 10 + 60 + 10 
        
        for i, prop in enumerate(props):
            lbl(ui_list, 10, ys + 4, names[i], 12, COL_TEXT_DIM)
            current_x = start_x_fields
            for j in range(3):
                lbl(ui_list, current_x, ys + 4, axis_labels[j], 12, axis_colors[j])
                ui_list.append(NumberField(VIEW_W + current_x + 15, ys, field_w, 22, 
                                           lambda p=prop, ax=j: get_v(p, ax), 
                                           lambda v, p=prop, ax=j: set_v(v, p, ax)))
                current_x += 15 + field_w + 5 
            ys += 28
        ys += 10

    # ==================== BLOCK 3 : MATERIAL ====================
    if draw_section_header("MATERIAL", "MATERIAL"):
        
        # Detect if this is a light object (no PBR presets/sliders needed)
        is_light = sel_data.get('mat_type', '') in ('light', 'invisible_light')
        
        # --- PRESETS (Hidden for lights) ---
        if not is_light:
            import materials
            
            def apply_preset(name):
                p = materials.PRESETS.get(name)
                if not p: return
                d = state.get_selected_info()
                if not d: return
                
                d['mat_type'] = "standard" # Force standard PBR
                d['roughness'] = p.roughness
                d['metallic'] = p.metallic
                d['ir'] = p.ior
                d['transmission'] = p.transmission
                
                # Apply color if defined in preset (e.g. Gold)
                if p.albedo:
                    d['color'] = list(p.albedo)
                    
                state.push_material_update(engine)
            
            lbl(ui_list, 10, ys, "Presets:", 12, COL_TEXT_DIM)
            ys += 20
            
            preset_names = list(materials.PRESETS.keys())
            # Sort favorites first?
            favorites = ["CHROME", "GOLD", "GLASS", "HARD_PLASTIC"]
            others = [k for k in preset_names if k not in favorites]
            sorted_keys = favorites + others
            
            x_st = 10
            y_st = ys
            bw, bh = 95, 24
            col_count = 3
            gap = 5
            
            for i, key in enumerate(sorted_keys):
                row = i // col_count
                col = i % col_count
                px = x_st + col * (bw + gap)
                py = y_st + row * (bh + gap)
                
                btn(ui_list, px, py, bw, bh, materials.PRESETS[key].name, apply_preset, key)
                
            ys += ((len(sorted_keys) - 1) // col_count + 1) * (bh + gap) + 10

        # --- SLIDERS ---
        lbl(ui_list, 10, ys, "Light:" if is_light else "Parameters:", 12, COL_TEXT_DIM)
        ys += 20

        # Sliders...
        def get_col(i): d=state.get_selected_info(); return d.get('color', [0.8]*3)[i] if d else 0.0
        def set_col(v, i): 
            d=state.get_selected_info(); 
            if d: 
                if 'color' not in d: d['color']=[0.8]*3
                d['color'][i]=v; state.push_material_update(engine)
        
        def get_prop(k, d_val): d=state.get_selected_info(); return d.get(k, d_val) if d else d_val
        def set_prop(v, k): 
            d=state.get_selected_info(); 
            if d: d[k]=v; state.push_material_update(engine)

        cols = [(180,50,50), (50,180,50), (50,50,180)]
        labels = ["R", "G", "B"]
        slider_x_rgb = 75
        slider_w_rgb = PANEL_W - slider_x_rgb - 10 
        
        for i in range(3):
            lbl(ui_list, 10, ys, lambda idx=i: f"{labels[idx]} ({get_col(idx):.2f})", 12, COL_TEXT_DIM)
            ui_list.append(Slider(VIEW_W + slider_x_rgb, ys, slider_w_rgb, 12, 0.0, 1.0, 
                                  lambda idx=i: get_col(idx), 
                                  lambda v, idx=i: set_col(v, idx), 
                                  power=1.0, color_track=cols[i])) # Integration power/color
            ys += 20
        ys += 10

        # --- LIGHT INTENSITY SLIDER (Only for emissive materials) ---
        
        if is_light:
            def get_intensity():
                d = state.get_selected_info()
                return d.get('intensity', 10.0) if d else 10.0
            def set_intensity(v):
                d = state.get_selected_info()
                if d:
                    d['intensity'] = v
                    state.push_material_update(engine)
            
            slider_x_int = 90
            slider_w_int = PANEL_W - slider_x_int - 10
            lbl(ui_list, 10, ys, lambda: f"Intens. ({get_intensity():.1f})", 12, (220, 180, 50))
            ui_list.append(Slider(VIEW_W + slider_x_int, ys, slider_w_int, 12, 0.0, 1000.0, 
                                  get_intensity, set_intensity, power=2.0, color_track=(220, 180, 50)))
            ys += 30

        # --- PBR SLIDERS (Hidden for lights) ---
        if not is_light:
            slider_x_prop = 90
            slider_w_prop = PANEL_W - slider_x_prop - 10
            
            # Roughness (Legacy Fuzz)
            lbl(ui_list, 10, ys, lambda: f"Rough ({get_prop('roughness', 0.5):.2f})", 12, COL_TEXT_DIM)
            ui_list.append(Slider(VIEW_W + slider_x_prop, ys, slider_w_prop, 12, 0.0, 1.0, 
                                  lambda: get_prop('roughness', 0.5), lambda v: set_prop(v, 'roughness'), power=1.5))
            ys += 20

            # Metallic
            lbl(ui_list, 10, ys, lambda: f"Metal ({get_prop('metallic', 0.0):.2f})", 12, COL_TEXT_DIM)
            ui_list.append(Slider(VIEW_W + slider_x_prop, ys, slider_w_prop, 12, 0.0, 1.0, 
                                  lambda: get_prop('metallic', 0.0), lambda v: set_prop(v, 'metallic')))
            ys += 20
            
            # Transmission
            lbl(ui_list, 10, ys, lambda: f"Trans ({get_prop('transmission', 0.0):.2f})", 12, COL_TEXT_DIM)
            ui_list.append(Slider(VIEW_W + slider_x_prop, ys, slider_w_prop, 12, 0.0, 1.0, 
                                  lambda: get_prop('transmission', 0.0), lambda v: set_prop(v, 'transmission')))
            ys += 20
            
            # IOR
            lbl(ui_list, 10, ys, lambda: f"IoR ({get_prop('ir', 1.5):.2f})", 12, COL_TEXT_DIM)
            ui_list.append(Slider(VIEW_W + slider_x_prop, ys, slider_w_prop, 12, 1.0, 3.0, 
                                  lambda: get_prop('ir', 1.5), lambda v: set_prop(v, 'ir')))
            ys += 20

            # Dispersion
            lbl(ui_list, 10, ys, lambda: f"Disp. ({get_prop('dispersion', 0.0):.3f})", 12, COL_TEXT_DIM)
            ui_list.append(Slider(VIEW_W + slider_x_prop, ys, slider_w_prop, 12, 0.0, 0.1, 
                                  lambda: get_prop('dispersion', 0.00), lambda v: set_prop(v, 'dispersion'), power=3))
            ys += 20

    # ==================== BLOCK 4 : TEXTURES ====================
    is_light = sel_data.get('mat_type', '') in ('light', 'invisible_light')
    if not is_light and draw_section_header("TEXTURE", "TEXTURE"):
        
        import tkinter as tk_tex
        from tkinter import filedialog as fd_tex
        import os as os_tex

        tex_channels = [
            ("Albedo",    "albedo_map",    (200, 170, 100)),
            ("Roughness", "roughness_map", (140, 140, 140)),
            ("Metallic",  "metallic_map",  (100, 160, 200)),
            ("Normal",    "normal_map",    (130, 130, 220)),
        ]
        
        for label_name, key, color in tex_channels:
            current_path = sel_data.get(key)
            display_name = os_tex.path.basename(current_path) if current_path else "None"
            
            # Label: Channel Name
            lbl(ui_list, 10, ys + 2, label_name, 12, color)
            
            # Label: Current File (truncated)
            if len(display_name) > 20:
                display_name = "..." + display_name[-17:]
            lbl(ui_list, 80, ys + 2, display_name, 11, COL_TEXT_DIM)
            
            # LOAD Button
            def make_load(k):
                def load_tex():
                    root = tk_tex.Tk(); root.withdraw(); root.attributes('-topmost', True)
                    fpath = fd_tex.askopenfilename(
                        title=f"Load {k.replace('_map','').title()} Map",
                        filetypes=[("Images", "*.png *.jpg *.jpeg *.tga *.bmp *.hdr *.exr")],
                        initialdir="."
                    )
                    root.destroy()
                    if not fpath: return
                    d = state.get_selected_info()
                    if d:
                        d[k] = fpath
                        state.push_texture_update(engine)
                        state.needs_ui_rebuild = True
                return load_tex
            
            btn(ui_list, PANEL_W - 80, ys, 35, 20, "Load", make_load(key))
            
            # CLEAR Button  
            def make_clear(k):
                def clear_tex():
                    d = state.get_selected_info()
                    if d:
                        d[k] = None
                        state.push_texture_update(engine)
                        state.needs_ui_rebuild = True
                return clear_tex
            
            btn(ui_list, PANEL_W - 40, ys, 25, 20, "X", make_clear(key), col_ov=(120, 50, 50))
            
            ys += 26
