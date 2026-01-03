import cpp_engine
import numpy as np
import cv2
import time
import math

# --- CODES TOUCHES (Windows/OpenCV) ---
KEY_ESC = 27
KEY_O = ord('o')
KEY_P = ord('p')
KEY_U = ord('u')
KEY_J = ord('j')
KEY_L = ord('l')  # Touche de verrouillage

# Codes Flèches (Compatible waitKeyEx)
# On garde vos codes spécifiques + les standards
ARROW_UP    = [2490368, 0x26, ord('w'), ord('z')] 
ARROW_DOWN  = [2621440, 0x28, ord('s')]
ARROW_LEFT  = [2424832, 0x25, ord('a'), ord('q')]
ARROW_RIGHT = [2555904, 0x27, ord('d')]

# Pavé numérique
NUMPAD_0 = [ord('0'), 60]
NUMPAD_1 = [ord('1'), 61]

def normalize(v):
    norm = np.linalg.norm(v)
    return v if norm == 0 else v / norm

# --- HELPER UI : Texte avec contour ---
def draw_text(img, text, pos, color, scale=0.5, thickness=1):
    x, y = pos
    # 1. Contour Noir (Plus épais)
    cv2.putText(img, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0), thickness + 2, cv2.LINE_AA)
    # 2. Texte Principal (Plus fin)
    cv2.putText(img, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, scale, color, thickness, cv2.LINE_AA)

class CameraController:
    def __init__(self, conf):
        self.pos = np.array(conf.lookfrom, dtype=np.float32)
        target = np.array(conf.lookat, dtype=np.float32)
        
        direction = target - self.pos
        length = np.linalg.norm(direction)
        direction = direction / length if length > 0 else np.array([0, 0, -1])
        
        self.pitch = math.asin(direction[1])
        self.yaw = math.atan2(direction[0], direction[2])
        
        self.vfov = conf.vfov
        self.focus_dist = conf.focus_dist
        self.aperture = getattr(conf, 'aperture', 0.0) 
        if self.aperture is None: self.aperture = 0.0
        
        self.base_speed = length * 0.5 
        self.mouse_sensitivity = 0.003
        
        # Flag pour savoir si la caméra a changé depuis le dernier update moteur
        self.dirty = True 

    def update_orientation(self, dx, dy):
        self.yaw += dx * self.mouse_sensitivity
        self.pitch -= dy * self.mouse_sensitivity
        self.pitch = max(-1.5, min(1.5, self.pitch))
        self.dirty = True

    def update_fov(self, delta):
        self.vfov = max(10.0, min(120.0, self.vfov + delta))
        self.dirty = True

    def update_focus_dist(self, delta):
        self.focus_dist = max(0.1, self.focus_dist + delta)
        self.dirty = True
    
    def update_aperture(self, delta):
        self.aperture = max(0.0, self.aperture + delta)
        self.dirty = True

    def get_vectors(self):
        fx = math.sin(self.yaw) * math.cos(self.pitch)
        fy = math.sin(self.pitch)
        fz = math.cos(self.yaw) * math.cos(self.pitch)
        
        forward = normalize(np.array([fx, fy, fz], dtype=np.float32))
        global_up = np.array([0, 1, 0], dtype=np.float32)
        right = normalize(np.cross(forward, global_up))
        up = normalize(np.cross(right, forward))
        
        return forward, right, up

    def move(self, fwd_val, side_val, up_val, dt):
        fwd, right, up = self.get_vectors()
        step = self.base_speed * dt
        
        if fwd_val != 0 or side_val != 0 or up_val != 0:
            self.pos += fwd * fwd_val * step
            self.pos += right * side_val * step
            self.pos += np.array([0, 1, 0]) * up_val * step
            self.dirty = True

    def apply_to_engine(self, engine, aspect_ratio):
        # On n'envoie au C++ que si nécessaire
        if self.dirty:
            fwd, _, _ = self.get_vectors()
            lookat = self.pos + fwd 
            
            orig_cpp = cpp_engine.Vec3(self.pos[0], self.pos[1], self.pos[2])
            targ_cpp = cpp_engine.Vec3(lookat[0], lookat[1], lookat[2])
            up_cpp   = cpp_engine.Vec3(0, 1, 0)
            
            engine.set_camera(orig_cpp, targ_cpp, up_cpp, 
                              self.vfov, aspect_ratio, self.aperture, self.focus_dist)
            self.dirty = False
            return True # Indique qu'un changement a eu lieu
        return False

    def get_final_params(self):
        fwd, _, _ = self.get_vectors()
        lookat = self.pos + fwd 
        return {
            'lookfrom': self.pos.tolist(),
            'lookat': lookat.tolist(),
            'vfov': self.vfov,
            'focus_dist': self.focus_dist,
            'aperture': self.aperture
        }

def run(engine, config):
    # Résolution cible
    W, H = 800, 450 
    
    # --- CONFIGURATION ADAPTATIVE ---
    current_scale = 1
    PT_DELAY = 1.0 
    
    print(f"[Viewer] Starting Adaptive Preview {W}x{H}...")
    
    # --- RÉAFFICHAGE DES CONTRÔLES ---
    print("\n" + "="*40)
    print("      HYBRID VIEWER CONTROLS      ")
    print("="*40)
    print(" [Souris]      : Orienter la caméra")
    print(" [Molette]     : Zoomer / Dézoomer (FOV)")
    print(" [Flèches/ZQS] : Se déplacer (Maintenir)")
    print(" [Pavé 1 / 0]  : Monter / Descendre")
    print(" [U / J]       : Focus Distance (+/-)")
    print(" [O / P]       : Aperture (Flou) (+/-)")
    print(" [L]           : LOCK Preview (Mode rapide forcé)")
    print(" [Clic Droit]  : Auto-Focus sur l'objet")
    print(" [ESC]         : Quitter")
    print("="*40 + "\n")
    
    cam = CameraController(config)
    
    win_name = "Raytracer Hybrid Preview"
    cv2.namedWindow(win_name, cv2.WINDOW_AUTOSIZE) 
    
    # État Souris
    mouse_down = False
    last_x, last_y = 0, 0
    
    # État Système
    last_interaction_time = time.time() 
    locked_preview = False
    
    # --- INPUT SMOOTHING ---
    # On garde l'état des touches en mémoire
    move_state = { 'fwd': 0, 'side': 0, 'up': 0 }
    last_key_time = 0
    # Timeout un peu plus long (200ms) pour absorber les micro-coupures de l'OS
    KEY_TIMEOUT = 0.2 

    def mouse_callback(event, x, y, flags, param):
        nonlocal mouse_down, last_x, last_y, last_interaction_time
        
        # Note : On update last_interaction_time ici pour empêcher le Path Tracing
        # de se déclencher pendant qu'on bouge la souris
        
        if event == cv2.EVENT_LBUTTONDOWN:
            mouse_down = True
            last_x, last_y = x, y
            last_interaction_time = time.time()
            
        elif event == cv2.EVENT_LBUTTONUP:
            mouse_down = False
            last_interaction_time = time.time()
            
        elif event == cv2.EVENT_MOUSEMOVE:
            if mouse_down:
                dx = x - last_x
                dy = y - last_y
                cam.update_orientation(dx, dy) # Marque cam.dirty = True
                last_x, last_y = x, y
                last_interaction_time = time.time()
                
        elif event == cv2.EVENT_MOUSEWHEEL:
            last_interaction_time = time.time()
            if flags > 0: cam.update_fov(-2.0) 
            else: cam.update_fov(2.0)
            
        elif event == cv2.EVENT_RBUTTONDOWN:
            try:
                # Force update immédiat pour le rayon
                cam.dirty = True 
                cam.apply_to_engine(engine, W/H)
                
                result = engine.pick_focus_distance(W, H, x, y)
                dist = result[0]
                if dist > 0:
                    print(f"[Focus] Set to {dist:.2f} m")
                    cam.focus_dist = dist
                    cam.dirty = True # Important pour refresh
                    last_interaction_time = time.time()
            except Exception as e:
                print(f"[Error] Auto-focus: {e}")

    cv2.setMouseCallback(win_name, mouse_callback)
    
    last_loop_time = time.time()

    while True:
        current_time = time.time()
        dt = current_time - last_loop_time
        last_loop_time = current_time
        
        # --- 1. GESTION INPUTS ---
        # UTILISATION DE waitKeyEx (Important pour les flèches étendues)
        key = cv2.waitKeyEx(1)
        
        try:
            if cv2.getWindowProperty(win_name, cv2.WND_PROP_VISIBLE) < 1: break
        except: break
            
        if key == KEY_ESC: break
        if key == KEY_L: 
            locked_preview = not locked_preview
            last_interaction_time = current_time
        
        # A. Détection des Touches (Met à jour l'intention)
        if key != -1:
            last_key_time = current_time
            last_interaction_time = current_time
            
            # Reset intention pour cette frame (sera remplie si touche active)
            # On ne reset pas à 0 tout de suite, on met à jour selon la touche pressée
            # Si on change de direction instantanément, ça le prendra.
            
            if key in ARROW_UP:    move_state['fwd'] = 1
            elif key in ARROW_DOWN:  move_state['fwd'] = -1
            
            if key in ARROW_LEFT:  move_state['side'] = -1
            elif key in ARROW_RIGHT: move_state['side'] = 1
            
            if key in NUMPAD_1:    move_state['up'] = 1
            elif key in NUMPAD_0:    move_state['up'] = -1
            
            # Paramètres ponctuels
            if key == KEY_U: cam.update_focus_dist(0.5)
            if key == KEY_J: cam.update_focus_dist(-0.5)
            if key == KEY_O: cam.update_aperture(0.05)
            if key == KEY_P: cam.update_aperture(-0.05)
        
        # B. Gestion du Timeout (Relâchement des touches)
        # Si aucune touche détectée depuis KEY_TIMEOUT, on arrête le mouvement
        if current_time - last_key_time > KEY_TIMEOUT:
            move_state['fwd'] = 0
            move_state['side'] = 0
            move_state['up'] = 0
            
        # C. Application Physique (Indépendant du FPS ou du Repeat Rate)
        # Tant que move_state est non nul, on applique le mouvement chaque frame
        if move_state['fwd'] != 0 or move_state['side'] != 0 or move_state['up'] != 0:
            cam.move(move_state['fwd'], move_state['side'], move_state['up'], dt)
            last_interaction_time = current_time

        # --- 2. UPDATE MOTEUR ---
        # Si la caméra a bougé (Souris ou Clavier), cam.dirty sera True.
        # apply_to_engine renvoie True si une modif a été faite.
        camera_changed = cam.apply_to_engine(engine, W/H)
        
        if camera_changed:
            # Si la caméra a bougé, on doit reset l'accumulation
            if hasattr(engine, 'reset_accumulation'):
                engine.reset_accumulation()
            # On s'assure que le timer d'interaction est à jour pour empêcher le Path Tracing immédiat
            last_interaction_time = current_time


        # --- 3. RENDU ---
        
        time_since_action = current_time - last_interaction_time
        should_accumulate = (time_since_action > PT_DELAY) and (not locked_preview)
        
        img_bgr = None
        status_text = ""
        status_color = (255, 255, 255)
        
        if not should_accumulate:
            # === MODE PREVIEW (MOUVEMENT) ===
            
            # Calcul Scale Adaptatif
            pW = max(1, W // current_scale)
            pH = max(1, H // current_scale)
            
            t_start = time.time()
            img_rgb = engine.render_preview(pW, pH, 0)
            render_duration = time.time() - t_start
            
            # Logique d'hystérésis simple
            if render_duration > 0.05: # < 20 FPS
                current_scale = min(16, current_scale * 2) 
            elif render_duration < 0.015: # > 60 FPS
                current_scale = max(1, current_scale // 2)
                
            img_small_bgr = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2BGR)
            img_bgr = cv2.resize(img_small_bgr, (W, H), interpolation=cv2.INTER_NEAREST)
            
            if locked_preview:
                status_text = "LOCKED PREVIEW"
                status_color = (0, 165, 255)
            elif time_since_action <= PT_DELAY:
                percent = time_since_action / PT_DELAY
                status_text = f"STABILIZING... {int(percent*100)}%"
                status_color = (0, 255, 255)
                
        else:
            # === MODE PATH TRACING ===
            if hasattr(engine, 'render_accumulate'):
                img_rgb = engine.render_accumulate(W, H, 0)
                img_bgr = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2BGR)
                status_text = "PATH TRACING" 
                status_color = (0, 255, 0)
            else:
                img_bgr = np.zeros((H, W, 3), dtype=np.uint8)
                status_text = "ERR: NO ACCUMULATE"

        # --- 4. OVERLAYS ---
        real_fps = 1.0 / dt if dt > 0 else 0
        info_line = f"FPS: {real_fps:.0f} | SCL: 1/{current_scale} | FOC: {cam.focus_dist:.1f}m | AP: {cam.aperture:.2f}"
        draw_text(img_bgr, info_line, (10, H - 15), (220, 220, 220), scale=0.5, thickness=1)
        draw_text(img_bgr, status_text, (10, 30), status_color, scale=0.6, thickness=2)

        if cv2.getWindowProperty(win_name, cv2.WND_PROP_VISIBLE) >= 1:
            cv2.imshow(win_name, img_bgr)
        else:
            break

    try:
        cv2.setMouseCallback(win_name, lambda *a: None)
    except:
        pass
    cv2.destroyAllWindows()
    
    return cam.get_final_params()