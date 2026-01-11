import pygame
import numpy as np
import time
import math
import threading # Pour le rendu en arrière-plan
import cpp_engine
import transforms as tf
from modes import renderer # On importe le moteur de rendu offline

# ===============================================================================================
# CONFIGURATION UI (STYLE "DARK PRO")
# ===============================================================================================

COL_BG      = (43, 43, 43)
COL_PANEL   = (50, 50, 50)
COL_HEADER  = (30, 30, 30)
COL_TEXT    = (220, 220, 220)
COL_TEXT_DIM= (150, 150, 150)

COL_BTN     = (70, 70, 70)
COL_BTN_HOV = (90, 90, 90)
COL_BTN_ACT = (58, 110, 165) # Bleu Acier
COL_BTN_DIS = (40, 40, 40)
COL_FIELD   = (30, 30, 30)   
COL_FIELD_ACT= (0, 100, 150) 
COL_BORDER  = (30, 30, 30)
COL_ACCENT  = (255, 165, 0)
COL_OVERLAY = (0, 0, 0, 180) # Fond semi-transparent pour l'overlay de rendu

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
    def __init__(self, x, y, w, h, text, callback=None, data=None, toggle=False, group=None):
        self.rect = pygame.Rect(x, y, w, h)
        self.text = text
        self.callback = callback
        self.data = data
        self.hover = False
        self.active = False
        self.toggle = toggle
        self.group = group 
        self.enabled = True 

    def draw(self, screen, fonts):
        col = COL_BTN_DIS if not self.enabled else (COL_BTN_ACT if self.active else (COL_BTN_HOV if self.hover else COL_BTN))
        pygame.draw.rect(screen, col, self.rect, border_radius=4)
        pygame.draw.rect(screen, COL_BORDER, self.rect, 1, border_radius=4)
        
        txt_col = COL_TEXT_DIM if not self.enabled else COL_TEXT
        f = fonts.get(14)
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
        screen.blit(surf, (self.rect.x + 5, self.rect.centery - surf.get_height()//2))

    def handle_event(self, event, state):
        if not self.enabled: return False

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                self.active = True
                self.text_buffer = str(self.get_cb()) 
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
            elif event.key == pygame.K_BACKSPACE:
                self.text_buffer = self.text_buffer[:-1]
            else:
                if event.unicode in "0123456789.-":
                    self.text_buffer += event.unicode
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

# ===============================================================================================
# ÉTAT DE L'ÉDITEUR
# ===============================================================================================

class EditorState:
    def __init__(self, conf, builder):
        self.builder = builder 
        self.res_scale = 1 
        self.res_auto = False
        self.preview_mode = 0 
        
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
        self.move_speed = 5.0
        
        # Tools
        self.tool_mode = "CAM"
        self.selected_id = -1
        self.gizmo_mode = "MOVE"
        self.typing_mode = False 
        
        # Rendering State
        self.dirty = True
        self.accum_spp = 0
        self.is_rendering = False # True quand le rendu offline tourne
        

    def get_selected_info(self):
        if self.selected_id != -1 and self.selected_id in self.builder.registry:
            return self.builder.registry[self.selected_id]
        return None

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

# Thread de rendu pour ne pas freezer l'UI
def render_thread_task(engine, config, state):
    print(">>> Starting Offline Render...")
    try:
        # On lance le rendu classique (qui sauvegarde l'image)
        renderer.run(engine, config)
    except Exception as e:
        print(f"Render Error: {e}")
    finally:
        print(">>> Render Finished.")
        state.is_rendering = False
        state.dirty = True # Pour rafraichir la vue au retour

def run(engine, config, builder):
    pygame.init()
    screen = pygame.display.set_mode((WIN_W, WIN_H))
    pygame.display.set_caption("Raytracer Studio - Interactive Editor")
    clock = pygame.time.Clock()
    
    fonts = { 12: pygame.font.SysFont("Arial", 12), 14: pygame.font.SysFont("Arial", 14), 18: pygame.font.SysFont("Arial", 18, bold=True) }
    state = EditorState(config, builder)
    
    ui = [] 
    
    def btn(x, y, w, h, txt, cb, data=None, toggle=False, grp=None, active=False):
        b = Button(VIEW_W + x, y, w, h, txt, cb, data, toggle, grp)
        if active: b.active = True
        if grp is not None: grp.append(b) 
        ui.append(b)
        return b
    
    def lbl(x, y, txt, sz=16, col=COL_TEXT, align="left", width=0):
        ui.append(Label(VIEW_W + x, y, txt, sz, col, align, width))

    # --- FONCTION START RENDER (Définie ici pour capturer le scope) ---
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

    # HEADER COMPACT
    y = 12
    l_fps = Label(VIEW_W + 10, y, "FPS: --", 14, COL_TEXT_DIM); ui.append(l_fps)
    l_spp = Label(VIEW_W + 100, y, "SPP: --", 14, COL_TEXT_DIM); ui.append(l_spp)
    y += 35 
    
    # PREVIEW
    lbl(10, y, "PREVIEW QUALITY", 18, COL_ACCENT)
    y += 25
    def set_res(v): 
        if v == 'AUTO': state.res_auto = True
        else: state.res_auto = False; state.res_scale = v
        state.dirty = True
    grp_res = []
    btn(10, y, 50, 24, "AUTO", set_res, 'AUTO', True, grp_res, False)
    btn(65, y, 40, 24, "1:1", set_res, 1, True, grp_res, True)
    btn(110, y, 40, 24, "1:2", set_res, 2, True, grp_res)
    btn(155, y, 40, 24, "1:4", set_res, 4, True, grp_res)
    y += 30
    
    def set_mode(m): state.preview_mode = m; state.dirty = True
    grp_mode = []
    btn(10, y, 90, 24, "NORMALS", set_mode, 0, True, grp_mode, True)
    btn(105, y, 70, 24, "CLAY", set_mode, 1, True, grp_mode)
    btn(180, y, 70, 24, "RAY", set_mode, 2, True, grp_mode)
    y += 35
    
    # TOOLS
    lbl(10, y, "MAIN TOOLS", 18, COL_ACCENT)
    y += 25
    def set_tool(t): state.tool_mode = t
    grp_tool = []
    b_cam = btn(10, y, 90, 40, "CAMERA", set_tool, "CAM", True, grp_tool, True)
    b_sel = btn(105, y, 90, 40, "SELECT", set_tool, "SEL", True, grp_tool)
    b_foc = btn(200, y, 90, 40, "FOCUS", set_tool, "FOCUS", True, grp_tool)
    y += 50
    
    # CAMERA SETTINGS
    lbl(10, y, "CAMERA SETTINGS", 18, COL_ACCENT)
    y += 25
    def adj_cam(data):
        attr, d = data 
        setattr(state, attr, getattr(state, attr) + d)
        state.dirty = True
    
    l_fov = Label(VIEW_W+10, y, "FOV", 12, align="center", width=90); ui.append(l_fov)
    l_apt = Label(VIEW_W+115, y, "Ap", 12, align="center", width=90); ui.append(l_apt)
    l_foc = Label(VIEW_W+220, y, "Dist", 12, align="center", width=90); ui.append(l_foc)
    y += 15 
    
    wb, hb, gb = 42, 24, 5
    btn(10, y, wb, hb, "-", adj_cam, ('vfov', -5)); btn(10+wb+gb, y, wb, hb, "+", adj_cam, ('vfov', 5))
    btn(115, y, wb, hb, "-", adj_cam, ('aperture', -0.05)); btn(115+wb+gb, y, wb, hb, "+", adj_cam, ('aperture', 0.05))
    btn(220, y, wb, hb, "-", adj_cam, ('focus_dist', -0.5)); btn(220+wb+gb, y, wb, hb, "+", adj_cam, ('focus_dist', 0.5))
    y += 40
    
    # INSPECTOR
    lbl(10, y, "OBJECT INSPECTOR", 18, COL_ACCENT); y += 25
    l_name = Label(VIEW_W+10, y, "No Selection", 14, COL_TEXT_DIM); ui.append(l_name); y += 25
    
    def set_gizmo(g): 
        state.gizmo_mode = g
        if state.tool_mode != "SEL":
            state.tool_mode = "SEL"
            b_cam.active = False
            b_sel.active = True
            b_foc.active = False

    grp_gizmo = []
    b_move = btn(10, y, 65, 24, "MOVE", set_gizmo, "MOVE", True, grp_gizmo, True)
    b_lift = btn(80, y, 65, 24, "LIFT", set_gizmo, "LIFT", True, grp_gizmo) 
    b_rot  = btn(150, y, 65, 24, "ROT", set_gizmo, "ROT", True, grp_gizmo)
    b_scl  = btn(220, y, 65, 24, "SCALE", set_gizmo, "SCALE", True, grp_gizmo)
    y += 35
    
    def get_v(idx_name, idx_axis):
        d = state.get_selected_info()
        return d[idx_name][idx_axis] if d else 0.0
    def set_v(val, idx_name, idx_axis):
        d = state.get_selected_info()
        if d: d[idx_name][idx_axis] = val; update_transform(engine, state)

    fields = []
    props = ["pos", "rot", "scale"]
    prop_names = ["Pos", "Rot", "Scl"]
    
    field_w = 60
    gap = 40
    start_x = 50
    
    for i, prop in enumerate(props):
        lbl(10, y+4, prop_names[i], 14, COL_TEXT_DIM)
        for j in range(3):
            f = NumberField(VIEW_W + start_x + j*(field_w+gap), y, field_w, 22,
                            lambda p=prop, axis=j: get_v(p, axis),
                            lambda v, p=prop, axis=j: set_v(v, p, axis))
            ui.append(f); fields.append(f)
        y += 26

    y += 5 
    lbl(10, y, "CONTROLS", 18, COL_ACCENT); y += 25
    lbl(10, y, "Arrows: Move Cam | R-Click: Rotate Cam", 12, COL_TEXT_DIM); y+=15
    lbl(10, y, "Mid-Click: Elevate Cam | Wheel: Zoom", 12, COL_TEXT_DIM); y+=15
    lbl(10, y, "Shift+LeftClick: Select Obj", 12, COL_TEXT_DIM); y+=15
    lbl(10, y, "Ctrl+LeftClick: Move Obj | Shift+RClick: Focus", 12, COL_TEXT_DIM); y+=15

    # BOUTON RENDER FINAL (Fixe en bas)
    # On le place manuellement à WIN_H - 45px
    btn(10, WIN_H - 45, 300, 35, "RENDER FINAL IMAGE", start_full_render)

    # ===========================================================================================
    # LOOP
    # ===========================================================================================
    
    running = True
    last_time = time.time()
    
    # Initialisation de la surface de rendu (noire au début)
    surface = pygame.Surface((VIEW_W, VIEW_H))
    surface.fill((0,0,0))
    
    # Variable pour stocker le dt du DERNIER rendu effectif (pour l'hystérésis)
    last_render_dt = 0.03
    
    gizmo_buttons = [b_move, b_lift, b_rot, b_scl]
    
    while running:
        clock.tick() # Limite FPS si besoin (ex 60), évite CPU 100%
        now = time.time()
        
        # Si un rendu offline est en cours, on bloque les events et on dessine un overlay
        if state.is_rendering:
            pygame.event.pump() # Garde la fenêtre vivante
            
            # Dessin Overlay
            overlay = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
            overlay.fill(COL_OVERLAY)
            screen.blit(overlay, (0,0))
            
            # Texte Loading
            txt = fonts.get(18).render("RENDERING IN PROGRESS... PLEASE WAIT", True, COL_ACCENT)
            r = txt.get_rect(center=(WIN_W//2, WIN_H//2))
            screen.blit(txt, r)
            pygame.display.flip()
            
            # Skip le reste de la boucle
            last_time = now # Pour éviter un saut temporel géant au retour
            continue

        # --- BOUCLE NORMALE ---
        
        # Calcul du dt réel pour les mouvements de caméra
        dt = now - last_time
        last_time = now
        
        keys = pygame.key.get_pressed()
        mouse_pos = pygame.mouse.get_pos()
        mouse_btns = pygame.mouse.get_pressed()
        in_viewport = mouse_pos[0] < VIEW_W
        
        is_shift = keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]
        is_ctrl  = keys[pygame.K_LCTRL] or keys[pygame.K_RCTRL]
        
        mouse_dx, mouse_dy = 0, 0
        
        for event in pygame.event.get():
            if event.type == pygame.QUIT: running = False
            elif event.type == pygame.KEYDOWN:
                ui_captured = False
                for widget in ui:
                    if widget.handle_event(event, state):
                        ui_captured = True
                        state.dirty = True 
                
                if not state.typing_mode and not ui_captured:
                    if event.key == pygame.K_ESCAPE: running = False

            elif event.type == pygame.MOUSEBUTTONDOWN:
                ui_hit = False
                if not in_viewport:
                    for widget in ui:
                        if widget in fields and state.selected_id == -1: continue
                        if widget in gizmo_buttons and state.selected_id == -1: continue
                        
                        if widget.handle_event(event, state):
                            ui_hit = True
                            state.dirty = True 
                
                else: 
                    if event.button == 1 and not ui_hit:
                        if state.tool_mode == "SEL" or (state.tool_mode == "CAM" and is_shift):
                            pid = engine.pick_instance_id(VIEW_W, VIEW_H, mouse_pos[0], mouse_pos[1])
                            state.selected_id = pid
                            state.dirty = True
                        elif state.tool_mode == "FOCUS":
                            res = engine.pick_focus_distance(VIEW_W, VIEW_H, mouse_pos[0], mouse_pos[1])
                            if res[0] > 0:
                                state.focus_dist = res[0]; state.dirty = True;
                        
                    elif event.button == 3:
                        if is_shift:
                            res = engine.pick_focus_distance(VIEW_W, VIEW_H, mouse_pos[0], mouse_pos[1])
                            if res[0] > 0: state.focus_dist = res[0]; state.dirty = True
                        else:
                            pygame.event.set_grab(True); pygame.mouse.set_visible(False)
                    
                    elif event.button == 2:
                        pygame.event.set_grab(True); pygame.mouse.set_visible(False)

            elif event.type == pygame.MOUSEBUTTONUP:
                if event.button == 1:
                    for widget in ui: widget.handle_event(event, state) 
                elif event.button == 3 or event.button == 2:
                    pygame.event.set_grab(False); pygame.mouse.set_visible(True)

            elif event.type == pygame.MOUSEMOTION:
                if not in_viewport:
                    for widget in ui: widget.handle_event(event, state)
                
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
        
        scene_changed = state.dirty
        if state.dirty:
            fx = math.sin(state.yaw) * math.cos(state.pitch)
            fy = math.sin(state.pitch)
            fz = math.cos(state.yaw) * math.cos(state.pitch)
            lookat = state.cam_pos + np.array([fx, fy, fz])
            engine.set_camera(cpp_engine.Vec3(*state.cam_pos), cpp_engine.Vec3(*lookat), cpp_engine.Vec3(0,1,0),
                              state.vfov, VIEW_W/VIEW_H, state.aperture, state.focus_dist)
            if hasattr(engine, 'reset_accumulation'): engine.reset_accumulation()
            state.accum_spp = 0; state.dirty = False

        # --- LOGIQUE DE RENDU OPTIMISÉE ---
        
        should_render = False
        
        # 1. Vérification si on doit rendre
        if state.preview_mode == 2: # RAY
            # On continue tant que SPP < config ou si ça a bougé
            # Note: accumulation par passes de 4 samples (d'où le *4 possible, mais on simplifie)
            if scene_changed or state.accum_spp < config.spp:
                should_render = True
        else: # CLAY / NORMALS
            if scene_changed:
                should_render = True
        
        # 2. Rendu conditionnel
        if should_render:
            render_start = time.time()
            
            scale = state.res_scale
            if state.res_auto:
                # Hystérésis basé sur le dernier temps de rendu CONNU
                if scale == 1 and last_render_dt > 0.06: scale = 2
                elif scale == 2 and last_render_dt > 0.06: scale = 4
                elif scale == 4 and last_render_dt < 0.016: scale = 2
                elif scale == 2 and last_render_dt < 0.016: scale = 1
                else: scale = 1
                
            if state.preview_mode == 2:
                # On passe config.depth ici si on veut (ex: 50)
                # Mais tu as dit "je ne vais pas implémenter l'ajout du paramètre depth"
                # Donc on laisse l'appel standard (qui utilisera le defaut=6 du C++)
                raw = engine.render_accumulate(VIEW_W, VIEW_H, 4)
                state.accum_spp += 4 # On compte 4 par 4 car le C++ fait 4 passes
            else:
                pW, pH = max(1, VIEW_W//scale), max(1, VIEW_H//scale)
                raw = engine.render_preview(pW, pH, state.preview_mode, 4)
                state.accum_spp = 0
            
            # Tone mapping
            if state.preview_mode == 0: # NORMALS
                # PAS de Gamma, PAS de Tone Mapping. On veut les données brutes.
                # (Si tes normales sortent en -1..1 du moteur, décommente la ligne suivante)
                # corrected = (raw + 1.0) * 0.5
                corrected = raw
            elif state.preview_mode == 1: # CLAY
                # Clay = Lumière simple. 
                # On applique juste le Gamma 2.2 pour que ce ne soit pas trop sombre,
                # mais on évite le ACES qui peut donner cet aspect "délavé" sur du gris.
                corrected = np.power(np.clip(raw, 0, 1), 1.0/2.2)
            else: # RAY (2)
                # Ray = Photoréalisme HDR.
                # Ici on veut la totale : ACES (gestion des hautes lumières) + Gamma.
                corrected = renderer.apply_tone_mapping(raw)

            # Conversion Uint8
            img_uint8 = (np.clip(corrected, 0, 1) * 255).astype(np.uint8)
            # On transpose pour PyGame: (H, W, 3) -> (W, H, 3)
            img_transposed = np.transpose(img_uint8, (1, 0, 2))

            if scale > 1:
                # Si on est en basse résolution, on doit scaler
                # Pour scaler, on est obligé de créer une surface temporaire, 
                # mais c'est beaucoup plus léger car l'image source est petite.
                temp_surf = pygame.surfarray.make_surface(img_transposed)
                pygame.transform.scale(temp_surf, (VIEW_W, VIEW_H), surface)
            else:
                # En pleine résolution, on écrit directement dans la mémoire vidéo
                # C'est l'optimisation ultime : 0 allocation mémoire.
                pygame.surfarray.blit_array(surface, img_transposed)

            # Mise à jour du temps de rendu pour l'hystérésis
            last_render_dt = time.time() - render_start
            
            # Mise à jour FPS UI seulement quand on rend
            l_fps.text = f"FPS: {1.0/max(0.001, last_render_dt):.0f}"
        
        # Si on ne rend pas, on garde 'surface' telle quelle (dernière image connue)
        # et on ne met PAS à jour l_fps.text (il garde sa dernière valeur)

        # --- DRAW ---
        screen.blit(surface, (0,0))
        pygame.draw.rect(screen, COL_PANEL, (VIEW_W, 0, PANEL_W, WIN_H))
        pygame.draw.line(screen, COL_BORDER, (VIEW_W, 0), (VIEW_W, WIN_H))
        
        # Labels dynamiques
        l_spp.text = f"SPP: {state.accum_spp}"
        l_fov.text = f"FOV: {state.vfov:.0f}"
        l_apt.text = f"Ap: {state.aperture:.2f}"
        l_foc.text = f"Dist: {state.focus_dist:.1f}"
        
        sel_data = state.get_selected_info()
        has_sel = (sel_data is not None)
        
        for b in gizmo_buttons: b.enabled = has_sel
        for f in fields: f.enabled = has_sel

        if has_sel:
            name = sel_data.get('name', sel_data.get('type', 'Unknown'))
            l_name.text = f"ID {state.selected_id}: {name}"
        else:
            l_name.text = "No Selection"
            
        pygame.draw.rect(screen, COL_HEADER, (VIEW_W, 0, PANEL_W, 40))
        
        for w in ui: w.draw(screen, fonts)

        pygame.display.flip()

    pygame.quit()
    return {
        'lookfrom': state.cam_pos.tolist(),
        'lookat': (state.cam_pos + np.array([math.sin(state.yaw), math.sin(state.pitch), math.cos(state.yaw)])).tolist(),
        'vfov': state.vfov,
        'aperture': state.aperture,
        'focus_dist': state.focus_dist
    }