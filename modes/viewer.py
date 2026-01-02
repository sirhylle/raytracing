import cpp_engine
import numpy as np
import cv2
import time
import math

# --- CODES TOUCHES (Windows/OpenCV) ---
KEY_ESC = 27

# Codes Flèches
ARROW_UP    = [2490368, 0x26] 
ARROW_DOWN  = [2621440, 0x28]
ARROW_LEFT  = [2424832, 0x25]
ARROW_RIGHT = [2555904, 0x27]

# Pavé numérique
NUMPAD_0 = [ord('0'), 60]
NUMPAD_1 = [ord('1'), 61]

def normalize(v):
    norm = np.linalg.norm(v)
    return v if norm == 0 else v / norm

class CameraController:
    def __init__(self, conf):
        # Init position depuis la config
        self.pos = np.array(conf.lookfrom, dtype=np.float32)
        target = np.array(conf.lookat, dtype=np.float32)
        
        # Calcul orientation initiale
        direction = target - self.pos
        length = np.linalg.norm(direction)
        direction = direction / length if length > 0 else np.array([0, 0, -1])
        
        self.pitch = math.asin(direction[1])
        self.yaw = math.atan2(direction[0], direction[2])
        
        # Paramètres
        self.vfov = conf.vfov
        self.focus_dist = conf.focus_dist
        self.aperture = 0.0 # Force 0 en preview pour netteté
        
        # Vitesse de déplacement fixe
        self.speed = length * 0.05 
        self.mouse_sensitivity = 0.003

    def update_orientation(self, dx, dy):
        """Tourne la caméra (Souris)"""
        self.yaw += dx * self.mouse_sensitivity
        self.pitch -= dy * self.mouse_sensitivity
        self.pitch = max(-1.5, min(1.5, self.pitch))

    def update_fov(self, delta):
        """Change le FOV (Molette)"""
        self.vfov = max(10.0, min(120.0, self.vfov + delta))

    def update_focus_dist(self, delta):
        """Change la distance de focus"""
        self.focus_dist = max(0.1, self.focus_dist + delta)

    def get_vectors(self):
        """Vecteurs locaux"""
        fx = math.sin(self.yaw) * math.cos(self.pitch)
        fy = math.sin(self.pitch)
        fz = math.cos(self.yaw) * math.cos(self.pitch)
        
        forward = normalize(np.array([fx, fy, fz], dtype=np.float32))
        global_up = np.array([0, 1, 0], dtype=np.float32)
        right = normalize(np.cross(forward, global_up))
        up = normalize(np.cross(right, forward))
        
        return forward, right, up

    def move(self, forward_amount, right_amount, up_amount):
        fwd, right, up = self.get_vectors()
        
        # Déplacement
        self.pos += fwd * forward_amount * self.speed
        self.pos += right * right_amount * self.speed
        # Déplacement vertical absolu (Ascenseur)
        self.pos += np.array([0, 1, 0]) * up_amount * self.speed

    def apply_to_engine(self, engine, aspect_ratio):
        fwd, _, _ = self.get_vectors()
        lookat = self.pos + fwd 
        
        orig_cpp = cpp_engine.Vec3(self.pos[0], self.pos[1], self.pos[2])
        targ_cpp = cpp_engine.Vec3(lookat[0], lookat[1], lookat[2])
        up_cpp   = cpp_engine.Vec3(0, 1, 0)
        
        engine.set_camera(orig_cpp, targ_cpp, up_cpp, 
                          self.vfov, aspect_ratio, self.aperture, self.focus_dist)

    def get_final_params(self):
        fwd, _, _ = self.get_vectors()
        lookat = self.pos + fwd 
        return {
            'lookfrom': self.pos.tolist(),
            'lookat': lookat.tolist(),
            'vfov': self.vfov,
            'focus_dist': self.focus_dist
        }

def run(engine, config):
    """
    Lance la boucle de preview interactive OpenCV.
    Retourne un dictionnaire des paramètres finaux de caméra ou None.
    """
    W, H = 800, 450 # Résolution fixe pour la preview fluide
    print(f"[Viewer] Starting Interactive Preview {W}x{H}...")
    
    # En mode Preview, on force certains réglages légers
    cam = CameraController(config)
    
    print("\n--- PREVIEW MODE ---")
    print("[Souris]       : Orienter la caméra")
    print("[Molette]      : Zoomer / Dézoomer (FOV)")
    print("[Flèches]      : Se déplacer (Avant/Arrière/Gauche/Droite)")
    print("[Pavé Num 1]   : Monter")
    print("[Pavé Num 0]   : Descendre")
    print("[U / J]        : Focus Distance (+/-)")
    print("[Clic Droit]   : Auto-Focus sur l'objet pointé")
    print("[ESC / Croix]  : Quitter et générer la commande")

    print("[U / J]        : Focus Distance (+/-)")
    print("[Clic Droit]   : Auto-Focus sur l'objet pointé")
    print("[ESC / Croix]  : Quitter et générer la commande")

    win_name = "Raytracer Preview"
    # WINDOW_AUTOSIZE pour éviter que le user n'étire la fenêtre et casse le mapping souris <-> pixels
    cv2.namedWindow(win_name, cv2.WINDOW_AUTOSIZE) 
    
    mouse_down = False
    last_x, last_y = 0, 0

    def mouse_callback(event, x, y, flags, param):
        nonlocal mouse_down, last_x, last_y
        if event == cv2.EVENT_LBUTTONDOWN:
            mouse_down = True
            last_x, last_y = x, y
        elif event == cv2.EVENT_LBUTTONUP:
            mouse_down = False
        elif event == cv2.EVENT_MOUSEMOVE:
            if mouse_down:
                dx = x - last_x
                dy = y - last_y
                cam.update_orientation(dx, dy)
                last_x, last_y = x, y
        elif event == cv2.EVENT_MOUSEWHEEL:
            if flags > 0: 
                cam.update_fov(-2.0) 
            else: 
                cam.update_fov(2.0)
        elif event == cv2.EVENT_RBUTTONDOWN:
            # CLICK-TO-FOCUS
            try:
                print(f"[Debug] Click at ({x}, {y}) for Resolution {W}x{H}")
                cam.apply_to_engine(engine, W/H)
                
                # Le C++ retourne (dist, hit_x, hit_y, hit_z)
                result = engine.pick_focus_distance(W, H, x, y)
                dist = result[0]
                
                if dist > 0:
                    px, py, pz = result[1], result[2], result[3]
                    print(f"[Auto-Focus] Dist (Real): {dist:.2f} | Hit Point: ({px:.2f}, {py:.2f}, {pz:.2f})")
                    cam.focus_dist = dist
                else:
                    print("[Auto-Focus] Miss (Sky/Void).")
            except Exception as e:
                print(f"[Error] Auto-focus failed: {e}")


    cv2.setMouseCallback(win_name, mouse_callback)
    
    # Touches pour le focus
    KEY_U = ord('u')
    KEY_J = ord('j')

    while True:
        t0 = time.time()
        
        # --- 1. GESTION FENETRE & INPUTS ---
        key_full = cv2.waitKeyEx(1)
        
        try:
            if cv2.getWindowProperty(win_name, cv2.WND_PROP_VISIBLE) < 1:
                break
        except:
            break
            
        key = key_full 
        if key == KEY_ESC:
            break
            
        # --- 2. MOUVEMENTS & PARAMETRES ---
        move_fwd = 0
        move_side = 0
        move_up = 0
        
        if key in ARROW_UP:    move_fwd = 1
        if key in ARROW_DOWN:  move_fwd = -1
        if key in ARROW_LEFT:  move_side = -1
        if key in ARROW_RIGHT: move_side = 1
        if key in NUMPAD_1:    move_up = 1
        if key in NUMPAD_0:    move_up = -1
        
        if move_fwd or move_side or move_up:
            cam.move(move_fwd, move_side, move_up)
            
        # Focus
        if key == KEY_U: cam.update_focus_dist(0.5)
        if key == KEY_J: cam.update_focus_dist(-0.5)

        # --- 3. RENDU ---
        cam.apply_to_engine(engine, W/H)
        img_rgb = engine.render_preview(W, H, 0)
        img_bgr = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2BGR)
        
        # Overlay
        dt = time.time() - t0
        fps = 1.0 / dt if dt > 0 else 0
        
        # Info Soleil (Si activé)
        sun_info = ""
        if config.auto_sun:
            sun_info = f" | Sun: {config.auto_sun_intensity:.0f}"

        cv2.putText(img_bgr, f"FPS: {fps:.0f} | FOV: {cam.vfov:.1f} | FOC: {cam.focus_dist:.1f}{sun_info}", 
                    (10, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        
        # --- 4. AFFICHAGE ---
        if cv2.getWindowProperty(win_name, cv2.WND_PROP_VISIBLE) >= 1:
            cv2.imshow(win_name, img_bgr)
        else:
            break

    # CLEANUP REFERENCE CYCLES FOR NANOBIND
    # On désactive le callback avant de détruire la fenêtre pour casser le cycle de ref
    try:
        cv2.setMouseCallback(win_name, lambda *a: None)
    except Exception:
        pass # La fenêtre est peut-être déjà fermée par l'utilisateur

    cv2.destroyAllWindows()
    return cam.get_final_params()
