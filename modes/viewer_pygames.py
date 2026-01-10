import pygame
import numpy as np
import time
import math
import cpp_engine

# --- HELPER UI : TEXTE AVEC CONTOUR (Style OpenCV) ---
def draw_text_outlined(surface, text, font, pos, color, outline_col=(0,0,0)):
    x, y = pos
    # On dessine le contour (noir) en décalé
    for dx, dy in [(-1,-1), (-1,1), (1,-1), (1,1), (0,2)]: # Contour épais
        outline = font.render(text, True, outline_col)
        surface.blit(outline, (x + dx, y + dy))
    
    # On dessine le texte principal par dessus
    txt_surf = font.render(text, True, color)
    surface.blit(txt_surf, (x, y))

# --- LOGIQUE CAMÉRA ---
class CameraController:
    def __init__(self, conf):
        # 1. Initialisation Position & Orientation
        self.pos = np.array(conf.lookfrom, dtype=np.float32)
        target = np.array(conf.lookat, dtype=np.float32)
        
        direction = target - self.pos
        length = np.linalg.norm(direction)
        direction = direction / length if length > 0 else np.array([0, 0, -1])
        
        self.pitch = math.asin(direction[1])
        self.yaw = math.atan2(direction[0], direction[2])
        
        # 2. Paramètres Optiques
        self.vfov = conf.vfov
        self.focus_dist = conf.focus_dist
        self.aperture = getattr(conf, 'aperture', 0.0) or 0.0
        
        # 3. Vitesse de base
        self.initial_speed = length * 0.5 if length > 0 else 5.0
        self.base_speed = self.initial_speed
        self.mouse_sensitivity = 0.003
        
        self.dirty = True 

    def handle_input(self, keys, mouse_dx, mouse_dy, dt):
        # --- A. ORIENTATION (Si Clic Gauche maintenu) ---
        if mouse_dx != 0 or mouse_dy != 0:
            self.yaw -= mouse_dx * self.mouse_sensitivity 
            self.pitch -= mouse_dy * self.mouse_sensitivity
            self.pitch = max(-1.5, min(1.5, self.pitch))
            self.dirty = True

        # --- B. CALCUL VECTEURS LOCAUX ---
        fx = math.sin(self.yaw) * math.cos(self.pitch)
        fy = math.sin(self.pitch)
        fz = math.cos(self.yaw) * math.cos(self.pitch)
        fwd = np.array([fx, fy, fz], dtype=np.float32)
        
        global_up = np.array([0, 1, 0], dtype=np.float32)
        right = np.cross(fwd, global_up)
        nm = np.linalg.norm(right)
        if nm > 0: right /= nm
        
        # --- C. DÉPLACEMENT (Flèches) ---
        move = np.array([0.0, 0.0, 0.0])
        
        if keys[pygame.K_UP]:    move += fwd
        if keys[pygame.K_DOWN]:  move -= fwd
        if keys[pygame.K_LEFT]:  move -= right
        if keys[pygame.K_RIGHT]: move += right
        
        # --- D. ALTITUDE (Pavé Numérique) ---
        if keys[pygame.K_KP1]:   move += np.array([0, 1, 0])
        if keys[pygame.K_KP0]:   move -= np.array([0, 1, 0])

        # --- E. FOCUS / APERTURE ---
        if keys[pygame.K_u]: self.focus_dist += 5.0 * dt; self.dirty = True
        if keys[pygame.K_j]: self.focus_dist = max(0.1, self.focus_dist - 5.0 * dt); self.dirty = True
        if keys[pygame.K_o]: self.aperture += 0.5 * dt; self.dirty = True
        if keys[pygame.K_p]: self.aperture = max(0.0, self.aperture - 0.5 * dt); self.dirty = True

        # Application
        if np.linalg.norm(move) > 0:
            self.pos += move * self.base_speed * dt
            self.dirty = True

    def apply_to_engine(self, engine, aspect_ratio):
        if self.dirty:
            fx = math.sin(self.yaw) * math.cos(self.pitch)
            fy = math.sin(self.pitch)
            fz = math.cos(self.yaw) * math.cos(self.pitch)
            lookat = self.pos + np.array([fx, fy, fz], dtype=np.float32)
            
            orig_cpp = cpp_engine.Vec3(self.pos[0], self.pos[1], self.pos[2])
            targ_cpp = cpp_engine.Vec3(lookat[0], lookat[1], lookat[2])
            up_cpp   = cpp_engine.Vec3(0, 1, 0)
            
            engine.set_camera(orig_cpp, targ_cpp, up_cpp, 
                              self.vfov, aspect_ratio, self.aperture, self.focus_dist)
            self.dirty = False
            return True
        return False

    def get_final_params(self):
        fx = math.sin(self.yaw) * math.cos(self.pitch)
        fy = math.sin(self.pitch)
        fz = math.cos(self.yaw) * math.cos(self.pitch)
        lookat = self.pos + np.array([fx, fy, fz])
        return {
            'lookfrom': self.pos.tolist(),
            'lookat': lookat.tolist(),
            'vfov': self.vfov,
            'focus_dist': self.focus_dist,
            'aperture': self.aperture
        }

# --- BOUCLE PRINCIPALE ---
def run(engine, config):
    pygame.init()
    W, H = 800, 600
    screen = pygame.display.set_mode((W, H))
    pygame.display.set_caption("Raytracer Viewer")
    clock = pygame.time.Clock()
    
    # Police système "Gras" pour imiter le look technique
    font = pygame.font.SysFont("Arial", 16, bold=True)
    
    cam = CameraController(config)
    
    running = True
    pygame.mouse.set_visible(True)
    pygame.event.set_grab(False)
    
    mouse_down = False
    current_scale = 1
    preview_mode = 0
    locked_preview = False
    
    last_interaction_time = time.time()
    PT_DELAY = 0.5 

    while running:
        dt = clock.tick(60) / 1000.0
        current_time = time.time()
        
        # --- 1. EVENTS ---
        mouse_dx, mouse_dy = 0, 0
        
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE: running = False
                elif event.key == pygame.K_m:
                    preview_mode = (preview_mode + 1) % 2
                    last_interaction_time = current_time
                elif event.key == pygame.K_l:
                    locked_preview = not locked_preview
                    last_interaction_time = current_time
                elif event.key == pygame.K_KP_PLUS or event.key == pygame.K_PLUS:
                    cam.base_speed *= 1.5
                    print(f"Speed UP: {cam.base_speed:.2f}")
                elif event.key == pygame.K_KP_MINUS or event.key == pygame.K_MINUS:
                    cam.base_speed /= 1.5
                    print(f"Speed DOWN: {cam.base_speed:.2f}")
                elif event.key == pygame.K_p: 
                    print(cam.get_final_params())

            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1: # Clic Gauche
                    mouse_down = True
                    pygame.event.set_grab(True)
                    pygame.mouse.set_visible(False)
                elif event.button == 3: # Clic Droit (Auto-Focus)
                    mx, my = event.pos
                    cam.apply_to_engine(engine, W/H)
                    res = engine.pick_focus_distance(W, H, mx, my)
                    if res[0] > 0:
                        cam.focus_dist = res[0]
                        cam.dirty = True
                        last_interaction_time = current_time

            elif event.type == pygame.MOUSEBUTTONUP:
                if event.button == 1:
                    mouse_down = False
                    pygame.event.set_grab(False)
                    pygame.mouse.set_visible(True)

            elif event.type == pygame.MOUSEMOTION:
                if mouse_down:
                    mouse_dx, mouse_dy = event.rel
                    
            elif event.type == pygame.MOUSEWHEEL:
                cam.vfov -= event.y * 2.0
                cam.vfov = max(5.0, min(160.0, cam.vfov))
                cam.dirty = True
                last_interaction_time = current_time

        # --- 2. UPDATE ---
        keys = pygame.key.get_pressed()
        cam.handle_input(keys, mouse_dx, mouse_dy, dt)
        
        scene_changed = cam.apply_to_engine(engine, W/H)
        if scene_changed:
            if hasattr(engine, 'reset_accumulation'): engine.reset_accumulation()
            last_interaction_time = current_time

        # --- 3. RENDER ---
        time_since = current_time - last_interaction_time
        accumulate = (time_since > PT_DELAY) and (not locked_preview)
        
        img_surface = None
        status_text = ""
        status_color = (255, 255, 255)

        if not accumulate:
            # === PREVIEW ===
            pW, pH = max(1, W // current_scale), max(1, H // current_scale)
            t0 = time.time()
            raw = engine.render_preview(pW, pH, preview_mode, 4)
            render_dt = time.time() - t0
            
            # Hystérésis
            if render_dt > 0.05: current_scale = min(16, current_scale * 2) 
            elif render_dt < 0.020: current_scale = max(1, current_scale // 2)

            img = (np.clip(raw,0,1)*255).astype(np.uint8)
            surf = pygame.surfarray.make_surface(np.transpose(img, (1,0,2)))
            
            if current_scale > 1:
                img_surface = pygame.transform.scale(surf, (W, H))
            else:
                img_surface = surf
                
            mode_str = "CLAY" if preview_mode == 1 else "NORMALS"
            if locked_preview:
                status_text = f"LOCKED ({mode_str})"
                status_color = (0, 150, 255)
            else:
                status_text = f"PREVIEW ({mode_str})"
        else:
            # === PATH TRACING ===
            current_scale = 1 
            if hasattr(engine, 'render_accumulate'):
                raw = engine.render_accumulate(W, H, 4)
                img = (np.clip(raw,0,1)*255).astype(np.uint8)
                img_surface = pygame.surfarray.make_surface(np.transpose(img, (1,0,2)))
                status_text = "PATH TRACING"
                status_color = (0, 255, 0)

        # --- 4. DRAW ---
        if img_surface: screen.blit(img_surface, (0,0))
        
        # Ligne de Statut (Haut Gauche)
        draw_text_outlined(screen, status_text, font, (10, 10), status_color)
        
        # Ligne d'Infos Techniques (Bas Gauche) - Identique à l'ancien viewer
        real_fps = 1.0 / dt if dt > 0 else 0
        speed_mult = cam.base_speed / cam.initial_speed
        
        info_line = f"FPS: {real_fps:.0f} | SCL: 1/{current_scale} | SPD: {speed_mult:.2f}x | FOC: {cam.focus_dist:.1f}m | AP: {cam.aperture:.2f} | FOV: {cam.vfov:.1f}"
        
        # Positionnement dynamique en bas (H - 25px)
        draw_text_outlined(screen, info_line, font, (10, H - 25), (220, 220, 220))
        
        pygame.display.flip()

    pygame.quit()
    return cam.get_final_params()