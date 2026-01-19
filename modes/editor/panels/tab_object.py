from ..ui_core import *

def build(ui_list, start_y, state, engine):
    # --- 1. GESTION DE LA SÉLECTION VIDE ---
    if state.selected_id == -1:
        lbl(ui_list, 10, start_y, "No Selection, Left Click on an object", 14, COL_TEXT_DIM)
        return

    ys = start_y
    sel_data = state.get_selected_info()
    obj_name = sel_data.get('name', sel_data.get('type', 'Unknown'))

    # --- HELPER DE SECTION (Déplacé au début pour être utilisé tout de suite) ---
    def draw_section_header(title, accord_key):
        """Dessine une barre de titre avec le toggle inclus."""
        nonlocal ys
        is_open = state.is_accordion_open("OBJECT", accord_key)
        
        def toggle():
            state.toggle_accordion("OBJECT", accord_key)

        # 1. Fond Sombre
        ui_list.append(HeaderBar(VIEW_W + 5, ys-4, PANEL_W - 10, 26, COL_HEADER, callback=toggle))
        
        # 2. Titre
        lbl(ui_list, 15, ys, title, 14, COL_ACCENT)
        
        # 3. Bouton Toggle (dans la barre)        
        lbl(ui_list, PANEL_W - 25, ys-2, "-", 16, COL_TEXT_DIM) if is_open else lbl(ui_list, PANEL_W - 26, ys-1, "+", 16, COL_TEXT_DIM)
        
        ys += 30 
        return is_open

    # ==================== BLOC 1 : SELECTION (Info, Axes, Actions) ====================
    if draw_section_header("SELECTION", "SELECTION"):
        
        # A. Ligne 1 : Nom de l'objet (Gauche) & Axes (Droite)
        
        # 1. Nom
        lbl(ui_list, 10, ys, f"ID {state.selected_id}: {obj_name}", 14, COL_TEXT)

        # 2. Sélecteur d'Axes
        def set_axis(m): state.axis_mode = m
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
        
        ys += 30 # Saut de ligne après Identity/Axes

        # B. Ligne 2 : Actions (Delete, et futur Duplicate)
        
        def duplicate_obj():
            state.duplicate_selection(engine)
            
        # Bouton Duplicate
        btn(ui_list, 10, ys, 300, 28, "DUPLICATE OBJECT", duplicate_obj)

        ys += 30

        # 1. Delete
        def delete_obj():
            oid = state.selected_id
            engine.remove_instance(oid)
            if oid in state.builder.registry: del state.builder.registry[oid]
            state.selected_id = -1
            state.set_active_tab("SCENE") # Retour scène après suppression
            
        # Bouton Delete (Rouge)
        # On le fait un peu moins large pour laisser de la place au futur Duplicate si besoin,
        # ou on garde pleine largeur pour l'instant. Gardons 300px (full).
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

    # ==================== BLOC 2 : TRANSFORMS ====================
    if draw_section_header("TRANSFORMS", "TRANSFORMS"):
        
        # A. Gizmos
        def set_gizmo(g): state.gizmo_mode = g
        grp_gizmo = []
        bw, gap = 58, 5
        total_w = (4 * bw) + (3 * gap)
        x = (PANEL_W - total_w) // 2
        
        modes = ["MOVE", "LIFT", "ROT", "SCALE"]
        for m in modes:
            btn(ui_list, x, ys, bw, 24, m, set_gizmo, m, True, grp_gizmo, state.gizmo_mode==m)
            x += bw + gap
        ys += 35

        # B. Champs Numériques
        def get_v(prop, axis): d=state.get_selected_info(); return d[prop][axis] if d else 0.0
        def set_v(val, prop, axis): 
            d=state.get_selected_info(); 
            if d: d[prop][axis]=val; state.update_transform(engine)
        
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

    # ==================== BLOC 3 : MATERIAL ====================
    if draw_section_header("MATERIAL", "MATERIAL"):
        
        def set_mat(t):
            d=state.get_selected_info()
            if d: d['mat_type']=t; state.push_material_update(engine)
        
        grp_mat = []
        bw_mat, gap_mat = 48, 4
        total_w_mat = (5 * bw_mat) + (4 * gap_mat)
        x_mat = (PANEL_W - total_w_mat) // 2
        
        mat_types = [("MATTE", "lambertian"), ("METAL", "metal"), ("GLASS", "dielectric"), 
                     ("PLAST", "plastic"), ("LIGHT", "light")]
        curr = sel_data.get('mat_type', 'lambertian')
        
        for label, val in mat_types:
            btn(ui_list, x_mat, ys, bw_mat, 24, label, set_mat, val, True, grp_mat, curr==val)
            x_mat += bw_mat + gap_mat
        ys += 35

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
        
        slider_x_prop = 75
        slider_w_prop = PANEL_W - slider_x_prop - 10
        
        lbl(ui_list, 10, ys, lambda: f"Fuzz ({get_prop('fuzz', 0.0):.2f})", 12, COL_TEXT_DIM)
        ui_list.append(Slider(VIEW_W + slider_x_prop, ys, slider_w_prop, 12, 0.0, 1.0, 
                              lambda: get_prop('fuzz', 0.0), lambda v: set_prop(v, 'fuzz'), power=2.0))
        ys += 20
        
        lbl(ui_list, 10, ys, lambda: f"IoR ({get_prop('ir', 1.5):.2f})", 12, COL_TEXT_DIM)
        ui_list.append(Slider(VIEW_W + slider_x_prop, ys, slider_w_prop, 12, 1.0, 3.0, 
                              lambda: get_prop('ir', 1.5), lambda v: set_prop(v, 'ir')))
        ys += 20