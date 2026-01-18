from ..ui_core import *

def build(ui_list, start_y, state, engine):
    # --- 1. GESTION DE LA SÉLECTION VIDE ---
    if state.selected_id == -1:
        lbl(ui_list, 10, start_y, "No Selection", 14, COL_TEXT_DIM)
        return

    ys = start_y
    sel_data = state.get_selected_info()
    obj_name = sel_data.get('name', sel_data.get('type', 'Unknown'))

    # --- 2. HEADER : IDENTITÉ ---
    # Juste le nom et l'ID, sobre.
    lbl(ui_list, 10, ys, f"ID {state.selected_id}: {obj_name}", 14, COL_ACCENT)
    ys += 30

    # --- HELPER DE SECTION ---
    def draw_section_header(title, accord_key):
        """Dessine une barre de titre avec le toggle inclus."""
        nonlocal ys
        
        # État d'ouverture
        is_open = state.is_accordion_open("OBJECT", accord_key)
        
        # 1. Fond Sombre
        ui_list.append(HeaderBar(VIEW_W + 5, ys, PANEL_W - 10, 26, COL_HEADER))
        
        # 2. Titre
        lbl(ui_list, 15, ys + 4, title, 12, COL_TEXT)
        
        # 3. Bouton Toggle (dans la barre, à droite)
        def toggle():
            state.toggle_accordion("OBJECT", accord_key)
            # Le rebuild est géré par la boucle principale via needs_ui_rebuild=True dans toggle_accordion
        
        txt = "-" if is_open else "+"
        # On utilise un petit bouton transparent ou discret
        btn(ui_list, PANEL_W - 35, ys + 2, 24, 22, txt, toggle, col_ov=None)
        
        ys += 30 # Hauteur header + marge
        return is_open

    # ==================== BLOC 1 : GEOMETRY (TRANSFORMS) ====================
    if draw_section_header("TRANSFORMS", "TRANSFORMS"):
        
        # A. Outils Visuels (GIZMOS)
        # On les met DANS le panneau déplié, car ce sont des outils liés à la transfo
        lbl(ui_list, 10, ys, "Gizmo Tool", 11, COL_TEXT_DIM)
        ys += 18
        
        def set_gizmo(g): state.gizmo_mode = g
        grp_gizmo = []
        bw, gap, x = 58, 5, 10
        
        modes = ["MOVE", "LIFT", "ROT", "SCALE"]
        for m in modes:
            btn(ui_list, x, ys, bw, 24, m, set_gizmo, m, True, grp_gizmo, state.gizmo_mode==m)
            x += bw + gap
        ys += 35

        # B. Données Numériques (PRECISION)
        def get_v(prop, axis): d=state.get_selected_info(); return d[prop][axis] if d else 0.0
        def set_v(val, prop, axis): 
            d=state.get_selected_info(); 
            if d: d[prop][axis]=val; state.update_transform(engine)
        
        props = ["pos", "rot", "scale"]
        names = ["Position", "Rotation", "Scale"] # Noms complets plus propres
        
        for i, p in enumerate(props):
            lbl(ui_list, 10, ys+4, names[i], 12, COL_TEXT_DIM)
            # Champs alignés à droite
            start_x = 80
            field_w = 65
            for j in range(3):
                # TODO: Créer un helper num_field dans ui_core pour simplifier cette ligne
                ui_list.append(NumberField(VIEW_W+start_x+j*(field_w+5), ys, field_w, 22, 
                                           lambda pr=p, ax=j: get_v(pr, ax), 
                                           lambda v, pr=p, ax=j: set_v(v, pr, ax)))
            ys += 28
        
        ys += 10 # Marge fin de section

    # ==================== BLOC 2 : APPEARANCE (MATERIAL) ====================
    if draw_section_header("MATERIAL", "MATERIAL"):
        
        # A. Type de Matériau (Macro)
        lbl(ui_list, 10, ys, "Type", 11, COL_TEXT_DIM)
        ys += 18
        
        def set_mat(t):
            d=state.get_selected_info()
            if d: d['mat_type']=t; state.push_material_update(engine)
            # Pas besoin de rebuild explicite ici car push_material_update set dirty=True, 
            # mais pour l'UI "radio button" il faut que l'état change.
            # L'architecture actuelle redessine à la frame suivante, donc ça va.
        
        grp_mat = []
        x_mat = 10
        # On compacte un peu les noms pour que ça rentre mieux
        mat_types = [("MATTE", "lambertian"), ("METAL", "metal"), ("GLASS", "dielectric"), ("PLAST", "plastic"), ("LIGHT", "light")]
        curr = sel_data.get('mat_type', 'lambertian')
        
        for label, val in mat_types:
            btn(ui_list, x_mat, ys, 48, 24, label, set_mat, val, True, grp_mat, curr==val)
            x_mat += 52
        ys += 35

        # B. Paramètres (Micro)
        # Sliders RGB
        def get_col(i): d=state.get_selected_info(); return d.get('color', [0.8]*3)[i] if d else 0.0
        def set_col(v, i): 
            d=state.get_selected_info()
            if d: 
                if 'color' not in d: d['color']=[0.8]*3
                d['color'][i]=v; state.push_material_update(engine)

        # On fait des barres de couleur fines pour faire "Color Picker"
        cols = [(180,50,50), (50,180,50), (50,50,180)]
        labels = ["R", "G", "B"]
        
        for i in range(3):
            # Petit label R/G/B
            lbl(ui_list, 10, ys, labels[i], 12, COL_TEXT_DIM)
            ui_list.append(Slider(VIEW_W+30, ys, 270, 14, 0.0, 1.0, 
                                  lambda idx=i: get_col(idx), 
                                  lambda v, idx=i: set_col(v, idx), 
                                  cols[i]))
            ys += 20
        ys += 10
        
        # Autres propriétés
        def get_prop(k, d_val): d=state.get_selected_info(); return d.get(k, d_val) if d else d_val
        def set_prop(v, k): 
            d=state.get_selected_info(); 
            if d: d[k]=v; state.push_material_update(engine)

        lbl(ui_list, 10, ys, "Roughness", 12, COL_TEXT_DIM)
        ui_list.append(Slider(VIEW_W+80, ys, 220, 14, 0.0, 1.0, 
                              lambda: get_prop('fuzz', 0.0), lambda v: set_prop(v, 'fuzz')))
        ys += 25
        
        lbl(ui_list, 10, ys, "IOR", 12, COL_TEXT_DIM)
        ui_list.append(Slider(VIEW_W+80, ys, 220, 14, 1.0, 3.0, 
                              lambda: get_prop('ir', 1.5), lambda v: set_prop(v, 'ir')))
        ys += 10 # Marge fin section

    # ==================== BLOC 3 : DANGER ZONE (FOOTER) ====================
    # On pousse ça tout en bas, ou au moins avec une bonne marge
    ys += 20 
    
    def delete_obj():
        oid = state.selected_id
        engine.remove_instance(oid)
        if oid in state.builder.registry: del state.builder.registry[oid]
        state.selected_id = -1
        state.tool_mode = "CAM"
        # On force un rebuild via active_tab qui va détecter le changement d'état via la main loop
        # ou on laisse la main loop gérer le désélection
        
    # Un bouton rouge bien large mais en bas
    btn(ui_list, 10, ys, 300, 28, "DELETE OBJECT", delete_obj, col_ov=(160, 50, 50))
    ys += 40