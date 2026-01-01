import cpp_engine
import scenes
import numpy as np
import cv2
import time
import math
from dataclasses import asdict
import os
import imageio.v3 as iio

# --- CODES TOUCHES (Windows/OpenCV) ---
KEY_ESC = 27

# Codes Flèches (peuvent varier selon l'OS, on met plusieurs variantes)
# Windows extended codes
ARROW_UP    = [2490368, 0x26] 
ARROW_DOWN  = [2621440, 0x28]
ARROW_LEFT  = [2424832, 0x25]
ARROW_RIGHT = [2555904, 0x27]

# Pavé numérique (si Verr Num activé, ce sont les char '0' et '1')
NUMPAD_0 = [ord('0'), 60]
NUMPAD_1 = [ord('1'), 61]

def normalize(v):
    norm = np.linalg.norm(v)
    return v if norm == 0 else v / norm

class CameraController:
    def __init__(self, conf):
        # Init position depuis la scène
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
        self.aperture = 0.0 
        
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
        # On limite le FOV entre 10° (Zoom) et 120° (Grand angle)
        self.vfov = max(10.0, min(120.0, self.vfov + delta))

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

def main():
    W, H = 800, 450 
    
    engine = cpp_engine.Engine()
    
    scene_name = 'cornell' 
    print(f"Loading Scene: {scene_name}...")
    scene_obj = scenes.AVAILABLE_SCENES[scene_name]
    initial_conf = scene_obj.setup(engine)

    # --- CHARGEMENT DE L'ENVIRONNEMENT (HDRI) ---
    if initial_conf.env_map and os.path.exists(initial_conf.env_map):
        print(f"Loading Environment: {initial_conf.env_map}...")
        try:
            # 1. Lecture du fichier (EXR ou HDR ou JPG)
            img = iio.imread(initial_conf.env_map)
            
            # 2. Nettoyage format (H, W, 3)
            # Si c'est du N&B (H, W), on duplique les canaux
            if img.ndim == 2: 
                img = np.stack((img,)*3, axis=-1)
            # Si c'est du RGBA (H, W, 4), on garde RGB
            if img.ndim == 3 and img.shape[2] > 3: 
                img = img[:, :, :3]
            
            # 3. Conversion en Float32 (0.0 -> 1.0)
            env_data = img.astype(np.float32)
            if img.dtype == np.uint8: 
                env_data /= 255.0
            
            # 4. Envoi au C++ (Important: ascontiguousarray pour éviter les bugs mémoire)
            env_data = np.ascontiguousarray(env_data)
            engine.set_environment(env_data)
            
            # 5. Application des niveaux (Brightnes)
            # On met des valeurs par défaut si None
            bg_lvl = initial_conf.env_background_level if initial_conf.env_background_level is not None else 2.0
            engine.set_env_levels(bg_lvl, 0.0, 0.0) # On s'en fiche du direct/indirect en preview
            
            print("Environment loaded successfully.")
            
        except Exception as e:
            print(f"Failed to load environment: {e}")
    else:
        print("No environment map found in scene config.")

    
    cam = CameraController(initial_conf)
    
    print("\n--- PREVIEW MODE ---")
    print("[Souris]       : Orienter la caméra")
    print("[Molette]      : Zoomer / Dézoomer (FOV)")
    print("[Flèches]      : Se déplacer (Avant/Arrière/Gauche/Droite)")
    print("[Pavé Num 1]   : Monter")
    print("[Pavé Num 0]   : Descendre")
    print("[ESC / Croix]  : Quitter")

    win_name = "Raytracer Preview"
    cv2.namedWindow(win_name)
    
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
            # Molette : getMouseWheelDelta n'est pas toujours dispo en Python pur
            # flags > 0 signifie souvent scroll UP, < 0 scroll DOWN
            # Sur Windows flags renvoie une valeur signée.
            if flags > 0: 
                cam.update_fov(-2.0) # Zoom In (réduit FOV)
            else: 
                cam.update_fov(2.0)  # Zoom Out (augmente FOV)

    cv2.setMouseCallback(win_name, mouse_callback)

    while True:
        t0 = time.time()
        
        # --- 1. GESTION FENETRE & INPUTS ---
        # On lit les touches AVANT de décider de continuer
        key_full = cv2.waitKeyEx(1)
        
        # Vérification immédiate si la fenêtre est fermée (Croix)
        try:
            if cv2.getWindowProperty(win_name, cv2.WND_PROP_VISIBLE) < 1:
                break
        except:
            break
            
        key = key_full # OpenCV renvoie parfois le code complet direct
        
        if key == KEY_ESC:
            break
            
        # --- 2. MOUVEMENTS ---
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

        # --- 3. RENDU ---
        cam.apply_to_engine(engine, W/H)
        img_rgb = engine.render_preview(W, H, 0)
        img_bgr = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2BGR)
        
        # Overlay
        dt = time.time() - t0
        fps = 1.0 / dt if dt > 0 else 0
        cv2.putText(img_bgr, f"FPS: {fps:.0f} | FOV: {cam.vfov:.1f}", (10, 20), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        
        # --- 4. AFFICHAGE (Uniquement si fenêtre ouverte) ---
        # Double sécurité pour éviter le respawn
        if cv2.getWindowProperty(win_name, cv2.WND_PROP_VISIBLE) >= 1:
            cv2.imshow(win_name, img_bgr)
        else:
            break

    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()