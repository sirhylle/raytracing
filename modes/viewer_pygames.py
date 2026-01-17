import pygame
import numpy as np
import time
import math
import threading
import multiprocessing
import cpp_engine
import transforms as tf
from modes import renderer

# ===============================================================================================
# CONFIGURATION UI (STYLE "DARK PRO")
# ===============================================================================================

COL_BG      = (43, 43, 43)
COL_PANEL   = (50, 50, 50)
COL_HEADER  = (30, 30, 30) # Fond sombre pour les titres de section
COL_TEXT    = (220, 220, 220)
COL_TEXT_DIM= (150, 150, 150)

COL_BTN     = (70, 70, 70)
COL_BTN_HOV = (90, 90, 90)
COL_BTN_ACT = (58, 110, 165) # Bleu Acier
COL_BTN_DIS = (40, 40, 40)
COL_TAB_ACT = (60, 60, 60)   
COL_TAB_INA = (35, 35, 35)   

COL_FIELD   = (30, 30, 30)   
COL_FIELD_ACT= (0, 100, 150) 
COL_BORDER  = (30, 30, 30)
COL_ACCENT  = (255, 165, 0) # Orange pour les titres
COL_OVERLAY = (0, 0, 0, 180) 

VIEW_W, VIEW_H = 800, 600
PANEL_W = 320
WIN_W = VIEW_W + PANEL_W
WIN_H = VIEW_H

# ===============================================================================================
# UI FRAMEWORK
# ===============================================================================================

class UIElement:
    def draw(self, screen, fonts): pass
    def handle_event(self, event, state): return False

class Button(UIElement):
    def __init__(self, x, y, w, h, text, callback=None, data=None, toggle=False, group=None, color_override=None):
        self.rect = pygame.Rect(x, y, w, h)
        self.text = text
        self.callback = callback
        self.data = data
        self.hover = False
        self.active = False
        self.toggle = toggle
        self.group = group 
        self.enabled = True
        self.color_override = color_override

    def draw(self, screen, fonts):
        if self.color_override:
            col = self.color_override if not self.active else COL_BTN_ACT
        else:
            col = COL_BTN_DIS if not self.enabled else (COL_BTN_ACT if self.active else (COL_BTN_HOV if self.hover else COL_BTN))
        
        pygame.draw.rect(screen, col, self.rect, border_radius=4)
        pygame.draw.rect(screen, COL_BORDER, self.rect, 1, border_radius=4)
        
        txt_col = COL_TEXT_DIM if not self.enabled else COL_TEXT
        f = fonts.get(13) # Légèrement plus petit pour tout faire rentrer
        txt_surf = f.render(self.text, True, txt_col)
        txt_rect = txt_surf.get_rect(center=self.rect.center)
        screen.blit(txt_surf, txt_rect)

    def handle_event(self, event, state):
        if not self.enabled: return False
        
        if event.type == pygame.MOUSEMOTION:
            self.hover = self.rect.collidepoint(event.pos)
            
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.hover:
                if self.toggle:
                    if self.group is not None:
                        for btn in self.group: btn.active = False
                    self.active = True
                else:
                    self.active = True
                
                if self.callback:
                    if self.data is not None: self.callback(self.data)
                    else: self.callback()
                return True
                
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if not self.toggle: self.active = False
            
        return False

class Label(UIElement):
    def __init__(self, x, y, text, font_size=16, color=COL_TEXT, align="left", width=0):
        self.pos = (x, y)
        self.text = text
        self.color = color
        self.font_size = font_size
        self.align = align 
        self.width = width 
        self.enabled = True 

    def draw(self, screen, fonts):
        f = fonts.get(self.font_size)
        surf = f.render(self.text, True, self.color)
        draw_pos = list(self.pos)
        if self.align == "center" and self.width > 0:
            txt_w = surf.get_width()
            draw_pos[0] = self.pos[0] + (self.width // 2) - (txt_w // 2)
        screen.blit(surf, draw_pos)

class NumberField(UIElement):
    def __init__(self, x, y, w, h, get_cb, set_cb):
        self.rect = pygame.Rect(x, y, w, h)
        self.get_cb = get_cb 
        self.set_cb = set_cb 
        self.active = False
        self.text_buffer = ""
        self.enabled = True
        self.cursor_pos = 0 # Position du curseur (index dans la string)

    def draw(self, screen, fonts):
        if not self.enabled: return 
        
        col = COL_FIELD_ACT if self.active else COL_FIELD
        pygame.draw.rect(screen, col, self.rect, border_radius=4)
        pygame.draw.rect(screen, COL_BORDER, self.rect, 1, border_radius=4)
        
        if self.active:
            display_txt = self.text_buffer
        else:
            val = self.get_cb()
            display_txt = f"{val:.2f}"
            
        f = fonts.get(14)
        surf = f.render(display_txt, True, COL_TEXT)
        
        txt_x = self.rect.x + 5
        txt_y = self.rect.centery - surf.get_height() // 2
        screen.blit(surf, (txt_x, txt_y))
        
        # --- DESSIN DU CURSEUR INTELLIGENT ---
        if self.active:
            if time.time() % 1 > 0.5:
                # On mesure la largeur du texte AVANT le curseur pour savoir où dessiner la ligne
                txt_before_cursor = self.text_buffer[:self.cursor_pos]
                width_before = f.size(txt_before_cursor)[0]
                
                cursor_x = txt_x + width_before
                pygame.draw.line(screen, COL_TEXT, 
                                 (cursor_x, self.rect.y + 4), 
                                 (cursor_x, self.rect.bottom - 4), 1)

    def handle_event(self, event, state):
        if not self.enabled: return False

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                self.active = True
                
                # Formatage propre (arrondi)
                val = self.get_cb()
                self.text_buffer = str(round(val, 5)) 
                
                # Par défaut, on place le curseur à la fin au clic
                self.cursor_pos = len(self.text_buffer)
                
                state.typing_mode = True 
                return True
            else:
                if self.active: self.confirm(state) 
                return False
                
        elif event.type == pygame.KEYDOWN and self.active:
            if event.key == pygame.K_RETURN or event.key == pygame.K_KP_ENTER:
                self.confirm(state)
            elif event.key == pygame.K_ESCAPE:
                self.active = False
                state.typing_mode = False
            
            # --- NAVIGATION GAUCHE / DROITE ---
            elif event.key == pygame.K_LEFT:
                if self.cursor_pos > 0:
                    self.cursor_pos -= 1
            elif event.key == pygame.K_RIGHT:
                if self.cursor_pos < len(self.text_buffer):
                    self.cursor_pos += 1
            
            # --- BACKSPACE INTELLIGENT (Supprime avant le curseur) ---
            elif event.key == pygame.K_BACKSPACE:
                if self.cursor_pos > 0:
                    # On garde tout sauf le caractère juste avant le curseur
                    self.text_buffer = self.text_buffer[:self.cursor_pos-1] + self.text_buffer[self.cursor_pos:]
                    self.cursor_pos -= 1
            
            # --- SAISIE DE TEXTE (Insertion au curseur) ---
            else:
                if event.unicode in "0123456789.-":
                    char = event.unicode
                    # On insère le caractère à la position du curseur
                    self.text_buffer = self.text_buffer[:self.cursor_pos] + char + self.text_buffer[self.cursor_pos:]
                    self.cursor_pos += 1
            
            return True
        return False

    def confirm(self, state):
        try:
            val = float(self.text_buffer)
            self.set_cb(val)
            state.dirty = True
        except ValueError:
            pass 
        self.active = False
        state.typing_mode = False

class Slider(UIElement):
    def __init__(self, x, y, w, h, min_v, max_v, get_cb, set_cb, color_track=COL_BTN):
        self.rect = pygame.Rect(x, y, w, h)
        self.min_v = min_v
        self.max_v = max_v
        self.get_cb = get_cb
        self.set_cb = set_cb
        self.dragging = False
        self.color_track = color_track
        self.enabled = True

    def draw(self, screen, fonts):
        if not self.enabled: return
        
        # Fond du slider (Track)
        pygame.draw.rect(screen, COL_PANEL, self.rect, border_radius=4)
        pygame.draw.rect(screen, COL_BORDER, self.rect, 1, border_radius=4)
        
        # Partie remplie (Active Track)
        val = self.get_cb()
        # Clamp pour sécurité
        val = max(self.min_v, min(self.max_v, val))
        ratio = (val - self.min_v) / (self.max_v - self.min_v) if (self.max_v > self.min_v) else 0
        
        fill_rect = pygame.Rect(self.rect.x, self.rect.y, int(self.rect.width * ratio), self.rect.height)
        pygame.draw.rect(screen, self.color_track, fill_rect, border_radius=4)
        
        # Handle (Le petit curseur)
        handle_x = self.rect.x + int(self.rect.width * ratio)
        pygame.draw.circle(screen, COL_TEXT, (handle_x, self.rect.centery), 6)
        
        # Affichage de la valeur par dessus (pour info)
        # On affiche en noir ou blanc selon le remplissage pour le contraste, c'est du luxe
        txt_col = (255,255,255) if ratio < 0.5 else (0,0,0)
        f = fonts.get(12)
        surf = f.render(f"{val:.2f}", True, txt_col)
        # screen.blit(surf, (self.rect.x + 5, self.rect.centery - surf.get_height()//2))

    def handle_event(self, event, state):
        if not self.enabled: return False
        
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                self.dragging = True
                self.update_value(event.pos[0], state)
                return True
                
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if self.dragging:
                self.dragging = False
                return True
                
        elif event.type == pygame.MOUSEMOTION:
            if self.dragging:
                self.update_value(event.pos[0], state)
                return True
        
        return False

    def update_value(self, mouse_x, state):
        # Conversion Pixel -> Valeur
        relative_x = mouse_x - self.rect.x
        ratio = max(0.0, min(1.0, relative_x / self.rect.width))
        new_val = self.min_v + ratio * (self.max_v - self.min_v)
        self.set_cb(new_val)
        state.dirty = True

# ===============================================================================================
# ÉTAT DE L'ÉDITEUR
# ===============================================================================================

class EditorState:
    def __init__(self, conf, builder):
        self.builder = builder 
        self.res_scale = 1 
        self.res_auto = False
        self.preview_mode = 0 

        # --- VIEWPORT LOGIC ---
        # On calcule le ratio cible (ex: 16/9)
        self.target_aspect = conf.width / conf.height
        self.viewport_rect = pygame.Rect(0, 0, VIEW_W, VIEW_H) # Sera mis à jour
        
        # Camera
        self.cam_pos = np.array(conf.lookfrom, dtype=np.float32)
        target = np.array(conf.lookat, dtype=np.float32)
        direction = target - self.cam_pos
        length = np.linalg.norm(direction)
        direction = direction / length if length > 0 else np.array([0, 0, -1])
        self.pitch = math.asin(np.clip(direction[1], -0.99, 0.99))
        self.yaw = math.atan2(direction[0], direction[2])
        self.vfov = conf.vfov
        self.aperture = conf.aperture
        self.focus_dist = conf.focus_dist
        self.move_speed = 5.0 # TODO permettre de le modifier via l'UI
        
        # Tools & Tabs
        self.tool_mode = "CAM"
        self.selected_id = -1
        self.gizmo_mode = "MOVE"
        self.active_tab = "SCENE" # "SCENE" ou "OBJECT"
        self.typing_mode = False 

        # États des accordéons
        self.show_trans_details = False  # Fermé par défaut
        self.show_mat_details = False    # Fermé par défaut
        
        # Rendering State
        self.dirty = True
        self.accum_spp = 0
        self.is_rendering = False
        self.ray_batch_size = 2 

    def get_selected_info(self):
        if self.selected_id != -1 and self.selected_id in self.builder.registry:
            return self.builder.registry[self.selected_id]
        return None

# ===============================================================================================
# HELPER: VIEWPORT CALCULATION (Letterboxing)
# ===============================================================================================

def calculate_viewport(state):
    """Calcule le rectangle d'affichage pour respecter le ratio cible."""
    window_ratio = VIEW_W / VIEW_H
    target_ratio = state.target_aspect
    
    if window_ratio > target_ratio:
        # La fenêtre est plus large que l'image -> Bandes verticales (Pillarbox)
        # (Rare avec 800x600 et du 16:9, mais possible si image verticale)
        h = VIEW_H
        w = int(h * target_ratio)
        x = (VIEW_W - w) // 2
        y = 0
    else:
        # La fenêtre est plus haute que l'image -> Bandes horizontales (Letterbox)
        # Cas classique 16:9 dans 4:3
        w = VIEW_W
        h = int(w / target_ratio)
        x = 0
        y = (VIEW_H - h) // 2
        
    state.viewport_rect = pygame.Rect(x, y, w, h)

# ===============================================================================================
# MAIN
# ===============================================================================================

def update_transform(engine, state):
    data = state.get_selected_info()
    if not data: return

    pos = data['pos']
    rot = data['rot']
    scl = data['scale']

    M = tf.translate(pos[0], pos[1], pos[2]) @ \
        tf.rotate_y(rot[1]) @ \
        tf.rotate_x(rot[0]) @ \
        tf.rotate_z(rot[2]) @ \
        tf.scale(scl[0], scl[1], scl[2])
    InvM = np.linalg.inv(M)
    
    engine.update_instance_transform(state.selected_id, 
                                     np.ascontiguousarray(M, dtype=np.float32), 
                                     np.ascontiguousarray(InvM, dtype=np.float32))
    state.dirty = True

def render_thread_task(engine, config, state):
    print(">>> Starting Offline Render...")
    try:
        renderer.run(engine, config)
    except Exception as e:
        print(f"Render Error: {e}")
    finally:
        print(">>> Render Finished.")
        state.is_rendering = False
        state.dirty = True 

def run(engine, config, builder):
    pygame.init()
    screen = pygame.display.set_mode((WIN_W, WIN_H))
    pygame.display.set_caption("Raytracer Studio - Interactive Editor")
    clock = pygame.time.Clock()
    
    fonts = { 12: pygame.font.SysFont("Arial", 12), 13: pygame.font.SysFont("Arial", 13), 14: pygame.font.SysFont("Arial", 14), 18: pygame.font.SysFont("Arial", 18, bold=True) }
    state = EditorState(config, builder)

    # Calcul initial du viewport
    calculate_viewport(state)

    # --- CLI THREADS ---
    render_threads = config.threads
    if render_threads <= 0:
        total_cores = multiprocessing.cpu_count()
        leave = getattr(config, 'leave_cores', 2) 
        render_threads = max(1, total_cores - leave)

    print(f"[Viewer] Using {render_threads} threads for interactive rendering.")
    
    # --- UI CONTAINERS ---
    ui_header = [] 
    ui_scene = [] 
    ui_object = [] 
    ui_footer = [] 
    
    def btn(target_list, x, y, w, h, txt, cb, data=None, toggle=False, grp=None, active=False, col_ov=None):
        b = Button(VIEW_W + x, y, w, h, txt, cb, data, toggle, grp, col_ov)
        if active: b.active = True
        if grp is not None: grp.append(b) 
        target_list.append(b)
        return b
    
    def lbl(target_list, x, y, txt, sz=16, col=COL_TEXT, align="left", width=0):
        target_list.append(Label(VIEW_W + x, y, txt, sz, col, align, width))

    # ================= UI LAYOUT DEFINITION =================

    # --- 1. MONITORING (Tout en haut) ---
    y = 10
    l_fps = Label(VIEW_W + 10, y, "FPS: --", 14, COL_TEXT_DIM); ui_header.append(l_fps)
    l_spp = Label(VIEW_W + 100, y, "SPP: --", 14, COL_TEXT_DIM); ui_header.append(l_spp)
    y += 25

    # --- 2. RENDER SETTINGS ---
    # Fond sombre pour le titre
    # lbl(ui_header, 10, y, "RENDER SETTINGS", 14, COL_ACCENT)
    # y += 20
    
    # Ligne 1 : Quality
    def set_res(v): 
        if v == 'AUTO': state.res_auto = True
        else: state.res_auto = False; state.res_scale = v
        state.dirty = True
    grp_res = []
    
    lbl(ui_header, 10, y+3, "Qual", 12, COL_TEXT_DIM)
    btn(ui_header, 50, y, 45, 20, "Auto", set_res, 'AUTO', True, grp_res, False)
    btn(ui_header, 100, y, 35, 20, "1:1", set_res, 1, True, grp_res, True)
    btn(ui_header, 140, y, 35, 20, "1:2", set_res, 2, True, grp_res)
    btn(ui_header, 180, y, 35, 20, "1:4", set_res, 4, True, grp_res)
    y += 26

    # Ligne 2 : Mode (Retour du bouton Normals !)
    def set_mode(m): state.preview_mode = m; state.dirty = True
    grp_mode = []
    
    lbl(ui_header, 10, y+3, "Mode", 12, COL_TEXT_DIM)
    btn(ui_header, 50, y, 60, 20, "Normals", set_mode, 0, True, grp_mode, True)
    btn(ui_header, 115, y, 60, 20, "Clay", set_mode, 1, True, grp_mode)
    btn(ui_header, 180, y, 60, 20, "Ray", set_mode, 2, True, grp_mode)
    y += 45

    # --- 3. TOOLS (Cam/Select/Focus) ---
    lbl(ui_header, 10, y, "INTERACTION TOOLS", 14, COL_ACCENT)
    y += 20
    
    def set_tool(t): state.tool_mode = t
    grp_tool = []
    # On met tout sur une ligne
    b_cam = btn(ui_header, 10, y, 95, 30, "CAMERA", set_tool, "CAM", True, grp_tool, True)
    b_sel = btn(ui_header, 110, y, 95, 30, "SELECT", set_tool, "SEL", True, grp_tool)
    b_foc = btn(ui_header, 210, y, 95, 30, "FOCUS", set_tool, "FOCUS", True, grp_tool)
    y += 45

    # --- 4. TABS (Zone Onglets) ---
    def set_tab(t): state.active_tab = t
    grp_tabs = []
    
    # Boutons collés pour effet onglet
    btn_scene = btn(ui_header, 10, y, 150, 28, "SCENE GLOBAL", set_tab, "SCENE", True, grp_tabs, True, COL_TAB_INA)
    btn_object = btn(ui_header, 160, y, 150, 28, "OBJECT DATA", set_tab, "OBJECT", True, grp_tabs, False, COL_TAB_INA)
    
    y += 40 # Marge après les onglets

    # --- CONTENT: TAB SCENE ---
    ys = y
    lbl(ui_scene, 10, ys, "CAMERA", 14, COL_ACCENT)
    ys += 20
    
    def adj_cam(data):
        attr, d = data 
        setattr(state, attr, getattr(state, attr) + d)
        state.dirty = True
    
    # FOV
    lbl(ui_scene, 10, ys+4, "FOV", 12, COL_TEXT)
    btn(ui_scene, 80, ys, 30, 20, "-", adj_cam, ('vfov', -5)); 
    l_fov = Label(VIEW_W+115, ys+2, "40", 12, align="center", width=40); ui_scene.append(l_fov)
    btn(ui_scene, 160, ys, 30, 20, "+", adj_cam, ('vfov', 5))
    ys += 26
    
    # Aperture
    lbl(ui_scene, 10, ys+4, "Aperture", 12, COL_TEXT)
    btn(ui_scene, 80, ys, 30, 20, "-", adj_cam, ('aperture', -0.05)); 
    l_apt = Label(VIEW_W+115, ys+2, "0.00", 12, align="center", width=40); ui_scene.append(l_apt)
    btn(ui_scene, 160, ys, 30, 20, "+", adj_cam, ('aperture', 0.05))
    ys += 26

    # Focus Dist
    lbl(ui_scene, 10, ys+4, "Focus Dist", 12, COL_TEXT)
    btn(ui_scene, 80, ys, 30, 20, "-", adj_cam, ('focus_dist', -0.5)); 
    l_foc = Label(VIEW_W+115, ys+2, "10.0", 12, align="center", width=40); ui_scene.append(l_foc)
    btn(ui_scene, 160, ys, 30, 20, "+", adj_cam, ('focus_dist', 0.5))
    ys += 35
    
    # Environment (Placeholder)
    lbl(ui_scene, 10, ys, "ENVIRONMENT", 14, COL_ACCENT)
    ys += 20
    lbl(ui_scene, 10, ys, "(Coming Soon: Sun & HDR)", 12, COL_TEXT_DIM)

    # --- CONTENT: TAB OBJECT (Dynamique) ---
    
    # Cette fonction reconstruit l'interface de l'onglet objet selon l'état des accordéons
    def build_object_ui():
        ui_object.clear() # On vide la liste existante
        
        # Si pas de sélection, message simple
        if state.selected_id == -1:
            lbl(ui_object, 10, 80, "No Selection", 14, COL_TEXT_DIM)
            return

        yo = y # Position Y de départ (juste sous les onglets)
        
        # Header (Nom + ID)
        sel_data = state.get_selected_info()
        obj_name = sel_data.get('name', sel_data.get('type', 'Unknown'))
        lbl(ui_object, 10, yo, f"ID {state.selected_id}: {obj_name}", 14, COL_ACCENT)
        yo += 30

        # ==================== SECTION TRANSFORM ====================
        lbl(ui_object, 10, yo+4, "TRANSFORMS", 12, COL_TEXT_DIM)
        yo += 20

        # Ligne de boutons Transform + Toggle Accordéon
        def set_gizmo(g): state.gizmo_mode = g
        grp_gizmo = []
        
        # On réduit un peu la largeur des boutons pour faire de la place au [+]
        # Largeur dispo = 300px. 4 boutons + 1 toggle.
        bw = 58 
        gap = 5
        x = 10
        
        b_move = btn(ui_object, x, yo, bw, 24, "MOVE", set_gizmo, "MOVE", True, grp_gizmo, state.gizmo_mode=="MOVE")
        x += bw + gap
        b_lift = btn(ui_object, x, yo, bw, 24, "LIFT", set_gizmo, "LIFT", True, grp_gizmo, state.gizmo_mode=="LIFT") 
        x += bw + gap
        b_rot  = btn(ui_object, x, yo, bw, 24, "ROT", set_gizmo, "ROT", True, grp_gizmo, state.gizmo_mode=="ROT")
        x += bw + gap
        b_scl  = btn(ui_object, x, yo, bw, 24, "SCALE", set_gizmo, "SCALE", True, grp_gizmo, state.gizmo_mode=="SCALE")
        x += bw + gap + 5
        
        # BOUTON TOGGLE [+] / [-]
        def toggle_trans():
            state.show_trans_details = not state.show_trans_details
            build_object_ui() # RECONSTRUCTION IMMEDIATE
        
        txt_toggle = "-" if state.show_trans_details else "+"
        btn(ui_object, x, yo, 24, 24, txt_toggle, toggle_trans)
        
        yo += 30

        # CONTENU COLLAPSABLE (Champs numériques)
        if state.show_trans_details:
            # Helpers d'accès données (inchangés)
            def get_v(idx_name, idx_axis):
                d = state.get_selected_info()
                return d[idx_name][idx_axis] if d else 0.0
            def set_v(val, idx_name, idx_axis):
                d = state.get_selected_info()
                if d: d[idx_name][idx_axis] = val; update_transform(engine, state)

            props = ["pos", "rot", "scale"]
            prop_names = ["Pos", "Rot", "Scl"]
            field_w = 60
            field_gap = 40
            start_x = 50
            
            for i, prop in enumerate(props):
                lbl(ui_object, 10, yo+4, prop_names[i], 12, COL_TEXT_DIM)
                for j in range(3):
                    f = NumberField(VIEW_W + start_x + j*(field_w+field_gap), yo, field_w, 22,
                                    lambda p=prop, axis=j: get_v(p, axis),
                                    lambda v, p=prop, axis=j: set_v(v, p, axis))
                    ui_object.append(f)
                yo += 26
            yo += 10 # Marge bas du bloc

        # ==================== SECTION MATERIAL ====================
        lbl(ui_object, 10, yo, "MATERIAL", 14, COL_ACCENT)
        yo += 25

        # Helpers Material (inchangés)
        def push_material_update(state):
            d = state.get_selected_info()
            if not d: return
            ctype = d.get('mat_type', 'lambertian')
            ccol  = d.get('color', [0.8, 0.8, 0.8])
            cfuzz = d.get('fuzz', 0.0)
            cir   = d.get('ir', 1.5)
            engine.update_instance_material(state.selected_id, ctype, cpp_engine.Vec3(*ccol), cfuzz, cir)
            state.dirty = True

        def set_mat_type(t):
            d = state.get_selected_info(); 
            if d: 
                d['mat_type'] = t 
                if 'color' not in d: d['color'] = [0.8, 0.8, 0.8]
                push_material_update(state)
                # On force la mise à jour visuelle des boutons
                build_object_ui() 

        # Ligne de boutons Types + Toggle
        current_mat = sel_data.get('mat_type', 'lambertian')
        grp_mat = []
        
        # On fait des boutons plus petits pour tout caser sur une ligne + le toggle
        bw_mat = 48
        gap_mat = 4
        x_mat = 10
        
        # Liste des types supportés
        mat_types = [("MATTE", "lambertian"), ("METAL", "metal"), ("GLASS", "dielectric"), 
                     ("PLAST", "plastic"), ("LIGHT", "light")]
        
        for label, val in mat_types:
            is_act = (current_mat == val)
            btn(ui_object, x_mat, yo, bw_mat, 24, label, set_mat_type, val, True, grp_mat, is_act)
            x_mat += bw_mat + gap_mat

        # BOUTON TOGGLE MATERIAU [+]
        def toggle_mat():
            state.show_mat_details = not state.show_mat_details
            build_object_ui() # RECONSTRUCTION
            
        txt_toggle_mat = "-" if state.show_mat_details else "+"
        btn(ui_object, x_mat + 5, yo, 24, 24, txt_toggle_mat, toggle_mat)
        
        yo += 30

        # CONTENU COLLAPSABLE (Sliders)
        if state.show_mat_details:
            def get_col(idx):
                d = state.get_selected_info(); return d.get('color', [0.8,0.8,0.8])[idx] if d else 0.0
            def set_col(val, idx):
                d = state.get_selected_info()
                if d: 
                    if 'color' not in d: d['color'] = [0.8, 0.8, 0.8]
                    d['color'][idx] = val
                    push_material_update(state)

            def get_prop(name, def_val):
                d = state.get_selected_info(); return d.get(name, def_val) if d else def_val
            def set_prop(val, name):
                d = state.get_selected_info(); 
                if d: 
                    d[name] = val
                    if 'color' not in d: d['color'] = [0.8, 0.8, 0.8]
                    push_material_update(state)

            # Sliders RGB (Compactés)
            lbl(ui_object, 10, yo, "Color", 12, COL_TEXT_DIM)
            
            # On met les 3 sliders couleur très proches
            # R
            ui_object.append(Slider(VIEW_W+60, yo, 240, 12, 0.0, 1.0, 
                                    lambda: get_col(0), lambda v: set_col(v, 0), color_track=(180, 50, 50)))
            yo += 16
            # G
            ui_object.append(Slider(VIEW_W+60, yo, 240, 12, 0.0, 1.0, 
                                    lambda: get_col(1), lambda v: set_col(v, 1), color_track=(50, 180, 50)))
            yo += 16
            # B
            ui_object.append(Slider(VIEW_W+60, yo, 240, 12, 0.0, 1.0, 
                                    lambda: get_col(2), lambda v: set_col(v, 2), color_track=(50, 50, 180)))
            yo += 25

            # Properties
            lbl(ui_object, 10, yo, "Rough", 12, COL_TEXT_DIM)
            ui_object.append(Slider(VIEW_W+60, yo, 240, 14, 0.0, 1.0, 
                                    lambda: get_prop('fuzz', 0.0), lambda v: set_prop(v, 'fuzz')))
            yo += 20
            
            lbl(ui_object, 10, yo, "IOR", 12, COL_TEXT_DIM)
            ui_object.append(Slider(VIEW_W+60, yo, 240, 14, 1.0, 3.0, 
                                    lambda: get_prop('ir', 1.5), lambda v: set_prop(v, 'ir')))

        # --- LOGIQUE UPDATE C++ ---

        def push_material_update(state):
            d = state.get_selected_info()
            if not d: return
            
            # Valeurs par défaut si manquantes dans le dictionnaire
            ctype = d.get('mat_type', 'lambertian')
            ccol  = d.get('color', [0.8, 0.8, 0.8])
            cfuzz = d.get('fuzz', 0.0)
            cir   = d.get('ir', 1.5)
            
            # Appel C++
            engine.update_instance_material(state.selected_id, ctype, cpp_engine.Vec3(*ccol), cfuzz, cir)
            state.dirty = True

        # Getters/Setters pour l'UI
        def get_mat_type():
            d = state.get_selected_info(); return d.get('mat_type', 'lambertian') if d else 'lambertian'

        def set_mat_type(t):
            d = state.get_selected_info(); 
            if d: 
                d['mat_type'] = t 
                if 'color' not in d: d['color'] = [0.8, 0.8, 0.8]
                push_material_update(state)

        def get_col(idx):
            d = state.get_selected_info(); return d.get('color', [0.8,0.8,0.8])[idx] if d else 0.0

        def set_col(val, idx):
            d = state.get_selected_info()
            if d: 
                if 'color' not in d:
                    d['color'] = [0.8, 0.8, 0.8] # Gris par défaut
                d['color'][idx] = val
                push_material_update(state)

        def get_prop(name, def_val):
            d = state.get_selected_info(); return d.get(name, def_val) if d else def_val

        def set_prop(val, name):
            d = state.get_selected_info(); 
            if d: 
                d[name] = val
                if 'color' not in d: d['color'] = [0.8, 0.8, 0.8] # Sécurité
                push_material_update(state)

        

    # --- FOOTER ---
    def start_full_render():
        if state.is_rendering: return
        state.is_rendering = True
        config.lookfrom = state.cam_pos.tolist()
        fx = math.sin(state.yaw) * math.cos(state.pitch)
        fy = math.sin(state.pitch)
        fz = math.cos(state.yaw) * math.cos(state.pitch)
        config.lookat = (state.cam_pos + np.array([fx, fy, fz])).tolist()
        config.vfov = state.vfov
        config.aperture = state.aperture
        config.focus_dist = state.focus_dist
        t = threading.Thread(target=render_thread_task, args=(engine, config, state))
        t.start()

    btn(ui_footer, 10, WIN_H - 45, 300, 35, "RENDER FINAL IMAGE", start_full_render)

    # ===========================================================================================
    # LOOP
    # ===========================================================================================
    
    running = True
    last_time = time.time()

    # Surface de rendu temporaire (sera redimensionnée à chaque frame selon le viewport)
    # On ne l'initialise pas ici car sa taille dépend du viewport
    #surface = pygame.Surface((VIEW_W, VIEW_H))
    #surface.fill((0,0,0))

    last_render_dt = 0.03

    # Init UI
    build_object_ui()
    
    while running:
        clock.tick() 
        now = time.time()
        
        if state.is_rendering:
            pygame.event.pump() 
            overlay = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
            overlay.fill(COL_OVERLAY)
            screen.blit(overlay, (0,0))
            txt = fonts.get(18).render("RENDERING IN PROGRESS... PLEASE WAIT", True, COL_ACCENT)
            r = txt.get_rect(center=(WIN_W//2, WIN_H//2))
            screen.blit(txt, r)
            pygame.display.flip()
            last_time = now 
            continue

        dt = now - last_time
        last_time = now
        
        # --- Gestion de l'UI active ---
        active_ui_elements = ui_header + ui_footer
        if state.active_tab == "SCENE": active_ui_elements += ui_scene
        elif state.active_tab == "OBJECT": active_ui_elements += ui_object
        
        # Gestion des couleurs d'onglet
        if state.active_tab == "SCENE":
            btn_scene.color_override = COL_BTN_ACT
            btn_object.color_override = COL_BTN
        else:
            btn_scene.color_override = COL_BTN
            btn_object.color_override = COL_BTN_ACT
        
        keys = pygame.key.get_pressed()
        mouse_pos = pygame.mouse.get_pos()
        mouse_btns = pygame.mouse.get_pressed()

        # --- CORRECTION SOURIS ---
        # On vérifie si la souris est DANS le viewport (l'image) ou dans les bandes noires
        vp = state.viewport_rect
        in_viewport = vp.collidepoint(mouse_pos)

        # Coordonnées souris relatives à l'image (0,0 = coin haut-gauche de l'image, pas de la fenêtre)
        mouse_x_rel = mouse_pos[0] - vp.x
        mouse_y_rel = mouse_pos[1] - vp.y
        
        is_shift = keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]
        is_ctrl  = keys[pygame.K_LCTRL] or keys[pygame.K_RCTRL]
        
        for event in pygame.event.get():
            if event.type == pygame.QUIT: running = False
            elif event.type == pygame.KEYDOWN:
                ui_captured = False
                for widget in active_ui_elements:
                    if widget.handle_event(event, state):
                        ui_captured = True
                        state.dirty = True 
                
                if not state.typing_mode and not ui_captured:
                    if event.key == pygame.K_ESCAPE: running = False

            elif event.type == pygame.MOUSEBUTTONDOWN:
                ui_hit = False
                if mouse_pos[0] > VIEW_W:
                    for widget in active_ui_elements:
                        if widget.handle_event(event, state):
                            ui_hit = True
                            state.dirty = True
                
                else: 
                    if in_viewport and event.button == 1 and not ui_hit:
                        if state.tool_mode == "SEL" or (state.tool_mode == "CAM" and is_shift):
                            pid = engine.pick_instance_id(vp.width, vp.height, mouse_x_rel, mouse_y_rel)
                            state.selected_id = pid
                            state.dirty = True
                            
                            # AUTO SWITCH TAB
                            if pid != -1:
                                state.active_tab = "OBJECT"
                                state.tool_mode = "SEL"
                                b_cam.active = False; b_sel.active = True; b_foc.active = False; btn_scene.active = False
                                # [IMPORTANT] On reconstruit l'UI pour afficher les infos du nouvel objet
                                build_object_ui()
                            else:
                                state.active_tab = "SCENE"
                                build_object_ui()
                        
                        elif state.tool_mode == "FOCUS":
                            res = engine.pick_focus_distance(vp.width, vp.height, mouse_x_rel, mouse_y_rel)
                            if res[0] > 0:
                                state.focus_dist = res[0]; state.dirty = True;
                        
                    elif in_viewport and event.button == 3:
                        if is_shift:
                            res = engine.pick_focus_distance(vp.width, vp.height, mouse_x_rel, mouse_y_rel)
                            if res[0] > 0: state.focus_dist = res[0]; state.dirty = True
                        else:
                            pygame.event.set_grab(True); pygame.mouse.set_visible(False)
                    
                    elif in_viewport and event.button == 2:
                        pygame.event.set_grab(True); pygame.mouse.set_visible(False)

            elif event.type == pygame.MOUSEBUTTONUP:
                if event.button == 1:
                    for widget in active_ui_elements: widget.handle_event(event, state) 
                elif event.button == 3 or event.button == 2:
                    pygame.event.set_grab(False); pygame.mouse.set_visible(True)

            elif event.type == pygame.MOUSEMOTION:
                if not in_viewport:
                    for widget in active_ui_elements: widget.handle_event(event, state)
                
                if mouse_btns[2] and not is_shift:
                    dx, dy = event.rel
                    state.yaw -= dx * 0.003
                    state.pitch -= dy * 0.003
                    state.pitch = max(-1.5, min(1.5, state.pitch))
                    state.dirty = True
                
                if mouse_btns[1]:
                    dx, dy = event.rel
                    state.cam_pos[1] -= dy * 0.05 
                    state.dirty = True

                elif mouse_btns[0] and in_viewport and state.selected_id != -1:
                    # Logic GIZMO 3D (inchangée)
                    if state.tool_mode != "CAM" or is_ctrl:
                         dx, dy = event.rel
                         data = state.get_selected_info()
                         if data:
                             scale_factor = 0.01 * (state.focus_dist / 5.0)
                             if state.gizmo_mode == "MOVE":
                                 flat_yaw = state.yaw
                                 fx = math.sin(flat_yaw); fz = math.cos(flat_yaw)
                                 rx = math.cos(flat_yaw); rz = -math.sin(flat_yaw)
                                 data['pos'][0] += rx * -dx * scale_factor + fx * -dy * scale_factor
                                 data['pos'][2] += rz * -dx * scale_factor + fz * -dy * scale_factor
                             elif state.gizmo_mode == "LIFT":
                                 data['pos'][1] -= dy * scale_factor 
                             elif state.gizmo_mode == "ROT":
                                 data['rot'][1] += dx * 0.5 
                             elif state.gizmo_mode == "SCALE":
                                 s = 1.0 + (dx * 0.01)
                                 data['scale'] = [v * s for v in data['scale']]
                             update_transform(engine, state)

            elif event.type == pygame.MOUSEWHEEL:
                if in_viewport:
                    fx = math.sin(state.yaw) * math.cos(state.pitch)
                    fy = math.sin(state.pitch)
                    fz = math.cos(state.yaw) * math.cos(state.pitch)
                    state.cam_pos += np.array([fx, fy, fz]) * event.y * 1.0
                    state.dirty = True

        # Keyboard Move
        if not state.typing_mode: 
            fx = math.sin(state.yaw) * math.cos(state.pitch)
            fy = math.sin(state.pitch)
            fz = math.cos(state.yaw) * math.cos(state.pitch)
            fwd = np.array([fx, fy, fz])
            right = np.cross(fwd, np.array([0,1,0]))
            if np.linalg.norm(right) > 0: right /= np.linalg.norm(right)
            move = np.array([0.0,0.0,0.0])
            if keys[pygame.K_UP]:    move += fwd
            if keys[pygame.K_DOWN]:  move -= fwd
            if keys[pygame.K_LEFT]:  move -= right
            if keys[pygame.K_RIGHT]: move += right
            if keys[pygame.K_PAGEUP]:   move[1] += 1.0
            if keys[pygame.K_PAGEDOWN]: move[1] -= 1.0
            if np.linalg.norm(move) > 0:
                state.cam_pos += move * state.move_speed * dt
                state.dirty = True
        
        # --- ENGINE UPDATE ---
        scene_changed = state.dirty
        if state.dirty:
            fx = math.sin(state.yaw) * math.cos(state.pitch)
            fy = math.sin(state.pitch)
            fz = math.cos(state.yaw) * math.cos(state.pitch)
            lookat = state.cam_pos + np.array([fx, fy, fz])
            engine.set_camera(cpp_engine.Vec3(*state.cam_pos), cpp_engine.Vec3(*lookat), cpp_engine.Vec3(0,1,0),
                              state.vfov, state.target_aspect, state.aperture, state.focus_dist)
            if hasattr(engine, 'reset_accumulation'): engine.reset_accumulation()
            state.accum_spp = 0; state.dirty = False

        # --- RENDU ---
        vp = state.viewport_rect
        render_w = vp.width
        render_h = vp.height
        should_render = False
        if state.preview_mode == 2: # RAY
            if scene_changed or state.accum_spp < config.spp: should_render = True
        else: # CLAY / NORMALS
            if scene_changed: should_render = True
        
        if should_render:
            render_start = time.time()
            
            # Hysteresis Scale
            scale = state.res_scale
            if state.res_auto:
                if scale == 1 and last_render_dt > 0.06: scale = 2
                elif scale == 2 and last_render_dt > 0.06: scale = 4
                elif scale == 4 and last_render_dt < 0.016: scale = 2
                elif scale == 2 and last_render_dt < 0.016: scale = 1
                else: scale = 1
            rw = max(1, render_w // scale)
            rh = max(1, render_h // scale)
                
            if state.preview_mode == 2: # RAY
                batch = state.ray_batch_size
                raw = engine.render_accumulate(render_w, render_h, batch, render_threads)
                state.accum_spp += batch
            else: # CLAY / NORMALS
                pW, pH = max(1, VIEW_W//scale), max(1, VIEW_H//scale)
                raw = engine.render_preview(rw, rh, state.preview_mode, render_threads)
                state.accum_spp = 0
            
            # Post-Process
            if state.preview_mode == 0: corrected = raw # Normals (Raw)
            elif state.preview_mode == 1: corrected = np.power(np.clip(raw, 0, 1), 1.0/2.2) # Clay (Gamma Only)
            else: corrected = renderer.apply_tone_mapping(raw) # Ray (ACES+Gamma)

            img_uint8 = (np.clip(corrected, 0, 1) * 255).astype(np.uint8)
            img_transposed = np.transpose(img_uint8, (1, 0, 2))

            # Surface Temporaire pour l'image
            # Note : On recrée/resize une surface à chaque frame si scale change, 
            # mais blit_array nécessite une surface de taille exacte.
            # Vu qu'on a optimisé ailleurs, c'est acceptable ici.
            img_surf = pygame.surfarray.make_surface(img_transposed)

            if scale > 1:
                img_surf = pygame.transform.scale(img_surf, (render_w, render_h))

            # On stocke l'image finale prête à afficher
            state.current_image = img_surf

            # Metrics
            current_dt = time.time() - render_start
            last_render_dt = current_dt 
            if state.preview_mode == 2: 
                target_dt = 0.033 
                if current_dt > 0.001:
                    ideal_batch = state.ray_batch_size * (target_dt / current_dt)
                    state.ray_batch_size = max(1, min(32, int(ideal_batch)))
            
            l_fps.text = f"FPS: {1.0/max(0.001, last_render_dt):.0f}"
        
        # --- DRAW ---
        # 1. Fond Noir (Bandes noires)
        screen.fill((0,0,0))

        # 2. Blit de l'image centrée (si elle existe)
        if hasattr(state, 'current_image'):
            screen.blit(state.current_image, (vp.x, vp.y))

        # 3. UI Panels
        pygame.draw.rect(screen, COL_PANEL, (VIEW_W, 0, PANEL_W, WIN_H))
        pygame.draw.line(screen, COL_BORDER, (VIEW_W, 0), (VIEW_W, WIN_H))
        
        # Update Labels
        l_spp.text = f"SPP: {state.accum_spp}"
        l_fov.text = f"{state.vfov:.0f}"
        l_apt.text = f"{state.aperture:.2f}"
        l_foc.text = f"{state.focus_dist:.1f}"
            
        pygame.draw.rect(screen, COL_HEADER, (VIEW_W, 0, PANEL_W, 100))
        pygame.draw.line(screen, COL_BORDER, (VIEW_W, 100), (WIN_W, 100))
        
        # Draw Active UI
        for w in active_ui_elements: w.draw(screen, fonts)

        pygame.display.flip()

    pygame.quit()
    return {
        'lookfrom': state.cam_pos.tolist(),
        'lookat': (state.cam_pos + np.array([math.sin(state.yaw), math.sin(state.pitch), math.cos(state.yaw)])).tolist(),
        'vfov': state.vfov,
        'aperture': state.aperture,
        'focus_dist': state.focus_dist
    }