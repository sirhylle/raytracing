from ..ui_core import *

def build(ui_list, start_y, state, engine):
    if state.selected_id == -1:
        lbl(ui_list, 10, start_y, "No Selection", 14, COL_TEXT_DIM)
        return

    ys = start_y
    sel_data = state.get_selected_info()
    obj_name = sel_data.get('name', sel_data.get('type', 'Unknown'))
    lbl(ui_list, 10, ys, f"ID {state.selected_id}: {obj_name}", 14, COL_ACCENT)
    ys += 30

    # TRANSFORMS
    lbl(ui_list, 10, ys+4, "TRANSFORMS", 12, COL_TEXT_DIM)
    ys += 20
    
    def set_gizmo(g): state.gizmo_mode = g
    grp_gizmo = []
    bw, gap, x = 58, 5, 10
    
    # Boutons Gizmo
    modes = ["MOVE", "LIFT", "ROT", "SCALE"]
    for m in modes:
        btn(ui_list, x, ys, bw, 24, m, set_gizmo, m, True, grp_gizmo, state.gizmo_mode==m)
        x += bw + gap
    
    # Toggle Accordéon TRANSFORMS
    def toggle_trans(): state.toggle_accordion("OBJECT", "TRANSFORMS")
    is_open = state.is_accordion_open("OBJECT", "TRANSFORMS")
    btn(ui_list, x, ys, 24, 24, "-" if is_open else "+", toggle_trans)
    ys += 30

    if is_open:
        def get_v(prop, axis): d=state.get_selected_info(); return d[prop][axis] if d else 0.0
        def set_v(val, prop, axis): 
            d=state.get_selected_info(); 
            if d: d[prop][axis]=val; state.update_transform(engine)
        
        props = ["pos", "rot", "scale"]
        names = ["Pos", "Rot", "Scl"]
        for i, p in enumerate(props):
            lbl(ui_list, 10, ys+4, names[i], 12, COL_TEXT_DIM)
            for j in range(3):
                # TODO: create a helper function for NumberField in ui_core.py
                ui_list.append(NumberField(VIEW_W+50+j*100, ys, 60, 22, lambda pr=p, ax=j: get_v(pr, ax), lambda v, pr=p, ax=j: set_v(v, pr, ax)))
            ys += 26
        ys += 10

    # DELETE BUTTON
    def delete_obj():
        oid = state.selected_id
        engine.remove_instance(oid)
        if oid in state.builder.registry: del state.builder.registry[oid]
        state.selected_id = -1
        state.tool_mode = "CAM"
    btn(ui_list, 10, ys, 300, 24, "DELETE OBJECT", delete_obj, col_ov=(180, 60, 60))
    ys += 30

    # MATERIAL
    lbl(ui_list, 10, ys, "MATERIAL", 14, COL_ACCENT)
    ys += 25
    
    def set_mat(t):
        d=state.get_selected_info()
        if d: d['mat_type']=t; state.push_material_update(engine)
    
    grp_mat = []
    x_mat = 10
    mat_types = [("MATTE", "lambertian"), ("METAL", "metal"), ("GLASS", "dielectric"), ("PLAST", "plastic"), ("LIGHT", "light")]
    curr = sel_data.get('mat_type', 'lambertian')
    
    for mat_label, val in mat_types:
        btn(ui_list, x_mat, ys, 48, 24, mat_label, set_mat, val, True, grp_mat, curr==val)
        x_mat += 52
    
    def toggle_mat(): state.toggle_accordion("OBJECT", "MATERIAL")
    is_mat_open = state.is_accordion_open("OBJECT", "MATERIAL")
    btn(ui_list, x_mat+5, ys, 24, 24, "-" if is_mat_open else "+", toggle_mat)
    ys += 30

    if is_mat_open:
        # Sliders RGB + Props (Simplifié pour l'exemple)
        def get_col(i): d=state.get_selected_info(); return d.get('color', [0.8]*3)[i] if d else 0.0
        def set_col(v, i): 
            d=state.get_selected_info()
            if d: 
                if 'color' not in d: d['color']=[0.8]*3
                d['color'][i]=v; state.push_material_update(engine)
        
        cols = [(180,50,50), (50,180,50), (50,50,180)]
        for i in range(3):
            ui_list.append(Slider(VIEW_W+80, ys, 220, 12, 0.0, 1.0, lambda idx=i: get_col(idx), lambda v, idx=i: set_col(v, idx), cols[i]))
            ys += 16
        ys += 10
        # Fuzz / IOR ...