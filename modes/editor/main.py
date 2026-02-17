"""
================================================================================================
MODULE: EDITOR ENTRY POINT
================================================================================================

DESCRIPTION:
  This is the main loop for the "Modern Editor" (V3).
  It orchestrates the PyGame window, the Renderer Engine, and the UI layout.

ARCHITECTURE:
  - AppState : Central source of truth (See state.py).
  - UI Core  : Immediate/Retained hybrid UI system (See ui_core.py).
  - Panels   : Modular UI layouts (See panels/ directory).
  - Engine   : The C++ path tracer instance.
  
  The loop follows a standard Game Loop pattern:
  1. Handle Inputs (Mouse/Keyboard).
  2. Update State (Camera, Selection, Gizmos).
  3. Render Scene (Progressive Raytracing or Preview).
  4. Draw UI (Overlay).

================================================================================================
"""
import pygame
import time
import math
import numpy as np
import threading
import multiprocessing
import cpp_engine
from modes import renderer
from . import ui_core, state, panels

def render_thread_task(engine, config, app_state):
    print(">>> Starting Offline Render...")
    try: renderer.run(engine, config)
    except Exception as e: print(f"Render Error: {e}")
    finally:
        print(">>> Render Finished.")
        app_state.is_rendering = False
        app_state.scene_dirty = True


# --- GIZMO MATH UTILS ---
def world_to_screen(view_rect, cam_pos, yaw, pitch, fov, point_3d):
    """Projects a 3D point to screen using camera basis vectors."""
    
    # 1. Reconstruire les vecteurs de la caméra (Copie conforme de ta logique de mouvement)
    # Forward (Direction du regard)
    fx = math.sin(yaw) * math.cos(pitch)
    fy = math.sin(pitch)
    fz = math.cos(yaw) * math.cos(pitch)
    fwd = np.array([fx, fy, fz])
    
    # Normalisation de sécurité
    norm_fwd = np.linalg.norm(fwd)
    if norm_fwd == 0: return None
    fwd /= norm_fwd

    # Right (Vecteur droite) -> Produit vectoriel avec le HAUT du monde (0,1,0)
    right = np.cross(fwd, np.array([0.0, 1.0, 0.0]))
    norm_right = np.linalg.norm(right)
    if norm_right == 0: 
        right = np.array([1.0, 0.0, 0.0]) # Cas dégénéré (regarde pile en haut/bas)
    else:
        right /= norm_right

    # Up (Vecteur haut LOCAL caméra) -> Produit vectoriel (Right, Forward)
    up = np.cross(right, fwd)
    up /= np.linalg.norm(up)

    # 2. Vecteur Caméra -> Point Objet
    cam_to_pt = np.array(point_3d) - cam_pos

    # 3. Projection sur les axes de la caméra (Dot Product)
    # Cela nous donne les coordonnées du point dans le référentiel de la caméra
    depth = np.dot(cam_to_pt, fwd)   # Distance en profondeur (Z local)
    x_local = np.dot(cam_to_pt, right) # Distance latérale (X local)
    y_local = np.dot(cam_to_pt, up)    # Distance verticale (Y local)

    # 4. Clipping (Si le point est derrière la caméra)
    if depth <= 0.1: return None

    # 5. Projection Perspective
    aspect = view_rect.width / view_rect.height
    tan_half_fov = math.tan(math.radians(fov) * 0.5)

    # Coordonnées normalisées (-1 à 1)
    # ndc_x = 0 signifie au centre de l'écran
    ndc_x = x_local / (depth * tan_half_fov * aspect)
    ndc_y = y_local / (depth * tan_half_fov)

    # 6. Viewport (Normalisé -> Pixels)
    # Attention: en écran informatique, Y va vers le bas, donc on inverse ndc_y (1.0 - ndc_y)
    # Ou plus simplement : on inverse le signe de y_local virtuel.
    # Formule standard de mapping [-1, 1] vers [0, width]
    px = view_rect.x + (ndc_x + 1.0) * 0.5 * view_rect.width
    py = view_rect.y + (1.0 - ndc_y) * 0.5 * view_rect.height 

    return (px, py)

def draw_gizmo(screen, state, vp_rect):
    """Draws aesthetic axes (Gizmo) with arrows."""
    if state.axis_mode == "NONE" or state.selected_id == -1: return
    
    info = state.get_selected_info()
    if not info: return
    
    # Données Objet
    pos = np.array(info['pos'])
    rot = np.radians(np.array(info['rot'])) 
    
    # Données Caméra
    cam_pos = state.cam_pos
    yaw, pitch = state.yaw, state.pitch
    fov = state.vfov
    
    # 1. Calcul du Centre (Origine)
    p0 = world_to_screen(vp_rect, cam_pos, yaw, pitch, fov, pos)
    if p0 is None: return 

    # Echelle dynamique
    dist = np.linalg.norm(pos - cam_pos)
    gizmo_size = dist * 0.15 
    
    # Couleurs "Pro" (Un peu moins saturées ou plus lumineuses)
    cols = {
        'x': (220, 60, 60),   # Rouge
        'y': (60, 220, 60),   # Vert
        'z': (60, 80, 240)    # Bleu
    }

    # Calcul des vecteurs unitaires (Local ou Global)
    if state.axis_mode == "GLOBAL":
        vx, vy, vz = np.array([1,0,0]), np.array([0,1,0]), np.array([0,0,1])
    else:
        # Rotation Euler basique pour le mode Local
        cx, sx = math.cos(rot[0]), math.sin(rot[0])
        cy, sy = math.cos(rot[1]), math.sin(rot[1])
        cz, sz = math.cos(rot[2]), math.sin(rot[2])
        
        vx = np.array([cy*cz, cy*sz, -sy]) 
        vy = np.array([sx*sy*cz - cx*sz, sx*sy*sz + cx*cz, sx*cy])
        vz = np.array([cx*sy*cz + sx*sz, cx*sy*sz - sx*cz, cx*cy])

    axes = [ (vx, cols['x']), (vy, cols['y']), (vz, cols['z']) ]

    # 2. Dessin des Axes
    # On dessine d'abord le centre
    pygame.draw.circle(screen, (255, 255, 255), (int(p0[0]), int(p0[1])), 4) # Centre blanc
    
    for vec, color in axes:
        pt_3d = pos + vec * gizmo_size
        p_end = world_to_screen(vp_rect, cam_pos, yaw, pitch, fov, pt_3d)
        
        if p_end:
            # Ligne principale (un peu plus épaisse)
            pygame.draw.line(screen, color, p0, p_end, 3)
            
            # --- Dessin de la Flèche (Triangle) ---
            # Vecteur direction 2D sur l'écran
            ux, uy = p_end[0] - p0[0], p_end[1] - p0[1]
            l = math.sqrt(ux*ux + uy*uy)
            if l > 0:
                ux, uy = ux/l, uy/l # Normalisation
                
                # Perpendiculaire (-y, x)
                px, py = -uy, ux
                
                # Taille de la flèche
                arrow_len = 12
                arrow_width = 5
                
                # Base de la flèche (on recule un peu depuis la fin)
                base_x = p_end[0] - ux * arrow_len
                base_y = p_end[1] - uy * arrow_len
                
                # Les 3 points du triangle
                tip = p_end
                c1 = (base_x + px * arrow_width, base_y + py * arrow_width)
                c2 = (base_x - px * arrow_width, base_y - py * arrow_width)
                
                pygame.draw.polygon(screen, color, [tip, c1, c2])


def run(engine, config, builder):
    pygame.init()
    screen = pygame.display.set_mode((ui_core.WIN_W, ui_core.WIN_H))
    pygame.display.set_caption("Raytracer Studio - Interactive Editor")
    clock = pygame.time.Clock()
    fonts = {
        11: pygame.font.SysFont("Arial", 11),
        12: pygame.font.SysFont("Arial", 12),
        13: pygame.font.SysFont("Arial", 13),
        14: pygame.font.SysFont("Arial", 14),
        16: pygame.font.SysFont("Arial", 16),
        18: pygame.font.SysFont("Arial", 18, bold=True)
    }
    
    app_state = state.EditorState(config, builder)
    app_state.calculate_viewport(ui_core.VIEW_W, ui_core.WIN_H)
    
    # Threading config
    render_threads = config.system.threads if config.system.threads > 0 else max(1, multiprocessing.cpu_count() - 2)

    ui_list = []
    
    # Variables for Resolution Hysteresis (Dynamic Quality)
    last_render_dt = 0.03
    
    def start_render():
        if app_state.is_rendering: return
        app_state.is_rendering = True
        # Update config object for renderer
        fx = math.sin(app_state.yaw)*math.cos(app_state.pitch)
        fy = math.sin(app_state.pitch)
        fz = math.cos(app_state.yaw)*math.cos(app_state.pitch)
        
        config.camera.lookfrom = app_state.cam_pos.tolist()
        config.camera.lookat = (app_state.cam_pos + np.array([fx, fy, fz])).tolist()
        config.camera.vfov = app_state.vfov
        config.camera.aperture = app_state.aperture
        config.camera.focus_dist = app_state.focus_dist
        
        # Sync Environment
        config.environment.exposure = app_state.env_exposure
        config.environment.background = app_state.env_background
        config.environment.diffuse = app_state.env_diffuse
        config.environment.specular = app_state.env_specular
        config.environment.rotation = app_state.env_rotation
        
        # Sync Auto Sun
        config.environment.auto_sun = app_state.sun_enabled
        config.environment.sun_intensity = app_state.sun_intensity
        config.environment.sun_radius = app_state.sun_radius
        config.environment.sun_dist = app_state.sun_dist
        config.environment.clipping_multiplier = app_state.env_clipping_multiplier

        config.render.sampler = app_state.render_sampler
        
        threading.Thread(target=render_thread_task, args=(engine, config, app_state)).start()

    # [HELPER] Fonction de reconstruction UI
    def rebuild_ui():
        ui_list.clear()
        content_start_y = panels.layout_global.build_header(ui_list, app_state)
        
        if app_state.active_tab == "SCENE":
            panels.tab_scene.build(ui_list, content_start_y+2, app_state, engine)
        elif app_state.active_tab == "OBJECT":
            panels.tab_object.build(ui_list, content_start_y+2, app_state, engine)
        elif app_state.active_tab == "CREATE":
            panels.tab_create.build(ui_list, content_start_y+2, app_state, engine)
        elif app_state.active_tab == "RENDER":
            panels.tab_render.build(ui_list, content_start_y+2, app_state, engine, start_render)
        
        app_state.needs_ui_rebuild = False

    # Premier build
    rebuild_ui()

    running = True
    last_time = time.time()
    last_render_dt = 0.03 # Init var
    
    # Surface de rendu Viewport (taille fixe ou dynamique ?)
    # On utilise les constantes UI pour l'instant
    view_surf = pygame.Surface((ui_core.VIEW_W, ui_core.VIEW_H))

    while running:
        vx, vy, vw, vh = app_state.viewport_rect
        vp_rect = pygame.Rect(vx, vy, vw, vh)

        clock.tick()
        now = time.time()
        dt = now - last_time
        last_time = now

        # Loading screen if offline render is in progress
        if app_state.is_rendering:
            pygame.event.pump()
            overlay = pygame.Surface((ui_core.WIN_W, ui_core.WIN_H), pygame.SRCALPHA)
            overlay.fill(ui_core.COL_OVERLAY)
            screen.blit(overlay, (0,0))
            txt = fonts.get(18).render("RENDERING IN PROGRESS... PLEASE WAIT", True, ui_core.COL_ACCENT)
            r = txt.get_rect(center=(ui_core.WIN_W//2, ui_core.WIN_H//2))
            screen.blit(txt, r)
            pygame.display.flip()
            continue
        
        # 1. RECONSTRUCTION UI (Seulement si nécessaire !)
        if app_state.needs_ui_rebuild:
            rebuild_ui()

        # 2. GESTION DES INPUTS
        keys = pygame.key.get_pressed()
        mouse_pos = pygame.mouse.get_pos()
        mouse_btns = pygame.mouse.get_pressed()
        
        # Détection Viewport (Est-ce qu'on clique dans l'image ou dans l'UI ?)
        in_viewport = vp_rect.collidepoint(mouse_pos)

        # Coordonnées relatives à l'image (pour le picking)
        mouse_x_rel = mouse_pos[0] - vp_rect.x
        mouse_y_rel = mouse_pos[1] - vp_rect.y
        
        for event in pygame.event.get():
            if event.type == pygame.QUIT: running = False
            
            # A. UI Events
            ui_captured = False
            for widget in ui_list:
                if widget.handle_event(event, app_state):
                    ui_captured = True
                    app_state.needs_repaint = True
                    # app_state.ui_dirty = True # REMOVED: Breaks drag state on sliders
            
            # B. Viewport Interaction (Seulement si l'UI n'a pas capturé l'event)
            if not ui_captured and not app_state.typing_mode:

                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    # 1. Si on est en train de faire un focus -> On annule
                    if app_state.picking_focus:

                        app_state.picking_focus = False
                        app_state.needs_ui_rebuild = True
                    
                    # 2. Sinon, si un objet est sélectionné -> On désélectionne
                    elif app_state.selected_id != -1:
                        app_state.selected_id = -1
                        app_state.set_active_tab("SCENE")
                        app_state.ui_dirty = True
                        app_state.scene_dirty = True
                    # running = False  <-- LIGNE SUPPRIMÉE
                
                # Clic Gauche : Sélection ou Gizmo
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and in_viewport:
                    # On vérifie si la touche F est enfoncée
                    is_focus_key = keys[pygame.K_f]

                    # CAS 1 : PICKING FOCUS (Via Bouton UI actif OU Touche F maintenue)
                    if app_state.picking_focus or is_focus_key:
                        res = engine.pick_focus_distance(vp_rect.width, vp_rect.height, mouse_x_rel, mouse_y_rel)
                        if res[0] > 0:
                            app_state.focus_dist = res[0]
                            app_state.scene_dirty = True
                            
                            # Si c'était le bouton UI qui était actif, on le désactive (coup unique)
                            if app_state.picking_focus:
                                app_state.picking_focus = False
                                app_state.ui_dirty = True
                    
                    # CAS 2 : SÉLECTION NORMALE (Par défaut)
                    else:
                        pid = engine.pick_instance_id(vp_rect.width, vp_rect.height, mouse_x_rel, mouse_y_rel)

                        # --- LOGIQUE "STICKY SELECTION" ---
                        # Objectif : Si on clique sur une superposition contenant l'objet DÉJÀ sélectionné,
                        # on garde la sélection actuelle (pour pouvoir le bouger).

                        should_switch_selection = True
                        current_id = app_state.selected_id
                        
                        # Si on a cliqué sur quelque chose (pid) ET qu'on avait déjà une sélection (current_id)
                        # ET que le moteur nous renvoie un ID différent...
                        if pid != -1 and current_id != -1 and pid != current_id:
                            
                            reg = app_state.builder.registry
                            # On vérifie que les IDs existent bien dans notre registre Python
                            if pid in reg and current_id in reg:
                                pos_new = np.array(reg[pid]['pos'])
                                pos_cur = np.array(reg[current_id]['pos'])

                                # Si la distance est minime (objets superposés), on assume que l'utilisateur
                                # voulait attraper l'objet déjà actif (ex: la copie qu'il vient de faire).
                                if np.linalg.norm(pos_new - pos_cur) < 0.001:
                                    should_switch_selection = False
                                    # On "ment" au système en disant qu'on a cliqué sur l'objet courant
                                    pid = current_id

                        if should_switch_selection and app_state.selected_id != pid:
                            app_state.selected_id = pid
                            app_state.scene_dirty = True
                            app_state.ui_dirty = True 

                            if pid != -1:
                                app_state.set_active_tab("OBJECT")
                                if app_state.accordions["OBJECT"] is None:
                                    app_state.accordions["OBJECT"] = "SELECTION"
                            else:
                                app_state.set_active_tab("SCENE")

                # Clic Droit : Capture souris pour rotation
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 3 and in_viewport:
                     pygame.event.set_grab(True); pygame.mouse.set_visible(False)
                
                elif event.type == pygame.MOUSEBUTTONUP:
                    if event.button == 3:
                        pygame.event.set_grab(False); pygame.mouse.set_visible(True)

                # Mouvements Souris (Rotation / Gizmo)
                elif event.type == pygame.MOUSEMOTION:
                    # Rotation Caméra (Clic Droit maintenu)
                    if mouse_btns[2]:
                        dx, dy = event.rel
                        app_state.yaw -= dx * 0.003
                        app_state.pitch -= dy * 0.003
                        app_state.pitch = max(-1.5, min(1.5, app_state.pitch))
                        app_state.scene_dirty = True
                        app_state.last_interaction_time = time.time()
                    
                    # LIFT (Clic Molette maintenu) - Vertical Pur
                    if mouse_btns[1]:
                         _, dy = event.rel # On ignore dx (géré par clavier)
                         
                         # Vitesse adaptative :
                         lift_speed = app_state.move_speed * 0.005
                         
                         # dy < 0 quand on monte la souris -> on augmente Y (on monte)
                         # Le signe '-' inverse le repère écran (Y vers le bas) pour le repère 3D (Y vers le haut)
                         app_state.cam_pos[1] -= dy * lift_speed
                         
                         app_state.scene_dirty = True
                         app_state.last_interaction_time = time.time()

                    # Gizmo / Interaction Objet (Clic Gauche maintenu)
                    is_focusing = app_state.picking_focus or keys[pygame.K_f]
                    if mouse_btns[0] and in_viewport and app_state.selected_id != -1 and not is_focusing:
                        dx, dy = event.rel
                        data = app_state.get_selected_info()
                        if data:
                            # --- CALCUL DE L'ÉCHELLE DYNAMIQUE ---
                            # 1. Distance réelle entre la caméra et l'objet
                            obj_pos = np.array(data['pos'])
                            dist_to_obj = np.linalg.norm(obj_pos - app_state.cam_pos)

                            # 2. Facteur magique
                            # On veut que le mouvement souris suive le curseur.
                            # La formule approx est : dist * tan(fov) / hauteur_ecran
                            # Empiriquement, 0.0015 * distance fonctionne très bien pour un FOV ~40-60
                            scale_factor = dist_to_obj * 0.0015
                            #scale_factor = 0.01 * (app_state.focus_dist / 5.0)

                            if app_state.gizmo_mode == "MOVE":
                                flat_yaw = app_state.yaw
                                fx, fz = math.sin(flat_yaw), math.cos(flat_yaw)
                                rx, rz = math.cos(flat_yaw), -math.sin(flat_yaw)
                                data['pos'][0] += rx * -dx * scale_factor + fx * -dy * scale_factor
                                data['pos'][2] += rz * -dx * scale_factor + fz * -dy * scale_factor
                            elif app_state.gizmo_mode == "LIFT":
                                data['pos'][1] -= dy * scale_factor 
                            elif app_state.gizmo_mode == "ROT":
                                data['rot'][1] += dx * 0.5 
                            elif app_state.gizmo_mode == "SCALE":
                                s = 1.0 + (dx * 0.01)
                                data['scale'] = [v * s for v in data['scale']]
                            
                            app_state.update_transform(engine)
                            app_state.last_interaction_time = time.time()

                # Zoom (Molette)
                elif event.type == pygame.MOUSEWHEEL and in_viewport:
                    fx = math.sin(app_state.yaw) * math.cos(app_state.pitch)
                    fy = math.sin(app_state.pitch)
                    fz = math.cos(app_state.yaw) * math.cos(app_state.pitch)
                    zoom_step = app_state.move_speed * 0.05
                    app_state.cam_pos += np.array([fx, fy, fz]) * event.y * zoom_step
                    app_state.scene_dirty = True
                    app_state.last_interaction_time = time.time()

        # Clavier (Déplacements ZQSD/Flèches)
        if not app_state.typing_mode: 
            fx = math.sin(app_state.yaw) * math.cos(app_state.pitch)
            fy = math.sin(app_state.pitch)
            fz = math.cos(app_state.yaw) * math.cos(app_state.pitch)
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
                app_state.cam_pos += move * app_state.move_speed * dt
                app_state.scene_dirty = True
                app_state.last_interaction_time = time.time()

        # ---------------------------------------------------------
        # 3. ENGINE UPDATE (Camera)
        # ---------------------------------------------------------
        
        # ---------------------------------------------------------
        # 4. RENDER LOGIC (Optimized)
        # ---------------------------------------------------------

        
        # A. UI Rebuild
        if app_state.needs_ui_rebuild:
            rebuild_ui()
            app_state.needs_ui_rebuild = False
            # Rebuilding UI might change layout, so we definitely want to repaint
            app_state.needs_repaint = True 
            
        # B. Scene Change (Reset Accumulator)
        if app_state.needs_render_reset:
            if hasattr(engine, 'reset_accumulation'): 
                engine.reset_accumulation()
            app_state.accum_spp = 0
            app_state.needs_render_reset = False
            # Render reset implies we need to generate a new image
            app_state.needs_repaint = True 

        # C. HYBRID RENDER STRATEGY
        # ---------------------------
        # 1. Determine State
        INTERACTION_GRACE_PERIOD = 0.2
        time_since_interaction = time.time() - app_state.last_interaction_time
        is_idling = time_since_interaction > INTERACTION_GRACE_PERIOD
        
        # 2. Determine Strategy & Resolution
        strategy_changed = False
        
        # STATE: INTERACTION (Fast, Full Frame, Downscaled)
        if not is_idling:
            # Check if we just entered interaction mode
            if app_state.render_strategy != "INTERACTIVE":
                app_state.render_strategy = "INTERACTIVE"
                strategy_changed = True
                
            # Dynamic Scale (Auto-Scaler Logic applies here)
            # Ensure we don't go below 1 pixel
            base_w = app_state.viewport_rect[2]
            base_h = app_state.viewport_rect[3]
            rw = int(base_w / app_state.res_scale)
            rh = int(base_h / app_state.res_scale)
            rw = max(1, min(4096, rw))
            rh = max(1, min(4096, rh))

        # STATE: IDLE (High Quality, Scanlines, Native)
        else:
             if app_state.render_strategy != "IDLE":
                app_state.render_strategy = "IDLE"
                strategy_changed = True
            
             # Force Native Resolution
             rw = app_state.viewport_rect[2]
             rh = app_state.viewport_rect[3]
             # If resizing window, we might have 0 dimensions briefly
             rw = max(1, rw)
             rh = max(1, rh)

        # 3. Handle Transitions
        if strategy_changed or app_state.needs_render_reset:
            if hasattr(engine, 'reset_accumulation'): 
                engine.reset_accumulation()
            app_state.accum_spp = 0
            app_state.render_scanline_iterator = 0
            app_state.needs_render_reset = False
            # Clear current image to black/background to avoid ghosting
            if app_state.current_image:
                 app_state.current_image.fill((0,0,0))
            app_state.needs_repaint = True

        # 4. Render Execution
        should_render = False
        if app_state.preview_mode == 2: # RAY
             if app_state.render_strategy == "INTERACTIVE":
                 # Render if SPP < Target (usually 1 for interaction, but we can accumulate if user holds still for < 0.2s)
                 # Actually for interaction we usually want continuous updates.
                 # Let's say we render if we haven't hit a modest limit or if we are moving?
                 # If moving, accum_spp is reset constantly anyway.
                 should_render = True
             else:
                 # IDLE: Render until target SPP
                 should_render = (app_state.accum_spp < config.render.spp)
        else:
             # PREVIEW: Only render once
             should_render = (app_state.accum_spp == 0)

        if should_render:
            t0 = time.time()
            
            # Sync Camera
            fx = math.sin(app_state.yaw) * math.cos(app_state.pitch)
            fy = math.sin(app_state.pitch)
            fz = math.cos(app_state.yaw) * math.cos(app_state.pitch)
            lookat = app_state.cam_pos + np.array([fx, fy, fz])
            engine.set_camera(
                 cpp_engine.Vec3(*app_state.cam_pos), 
                 cpp_engine.Vec3(*lookat), 
                 cpp_engine.Vec3(0,1,0),
                 app_state.vfov, 
                 app_state.target_aspect, 
                 app_state.aperture, 
                 app_state.focus_dist
            )
            
            render_threads = config.system.threads
            raw_slice = None
            slice_y_offset = 0 # Where to blit

            # --- CASE A: INTERACTIVE (Full Frame, Accumulate) ---
            if app_state.render_strategy == "INTERACTIVE":
                if app_state.preview_mode == 2: # RAY
                     # Always 1 SPP per frame for responsiveness
                     # We reuse render_accumulate for full frame
                     cur_spp = 1
                     raw_slice = engine.render_accumulate(rw, rh, cur_spp, render_threads, 3, app_state.preview_sampler) # Depth 3, Preview Sampler
                     # Note: We don't increment accum_spp manually here, render_accumulate does NOT increment python counter?
                     # Wait, cpp_engine.accumulate ADDS to internal buffer.
                     # If we are interactive, we reset every frame?
                     # Ideally: input -> reset -> render.
                     # If we are dragging, input events trigger reset. 
                     # If we stop dragging but are < 0.2s, we might accumulate a few frames.
                     pass 
                else:
                     raw_slice = engine.render_preview(rw, rh, app_state.preview_mode, render_threads)
                
                app_state.accum_spp = 1 # Just to mark as done
                slice_y_offset = 0

            # --- CASE B: IDLE (Scanlines) ---
            else: 
                # SCANLINE LOGIC: Only for Raytracing (progressive)
                if app_state.preview_mode == 2:
                    # Chunk size targets ~30-60fps. 
                    chunk_height = max(32, rh // 8) 
                    
                    start_y = app_state.render_scanline_iterator
                    
                    # Render Scanline Slice
                    # Use preview parameters for Editor Idle
                    raw_slice = engine.render_scanlines(rw, rh, 1, start_y, chunk_height, app_state.preview_depth, app_state.preview_sampler)
                    
                    slice_y_offset = start_y
                    
                    # Advance Iterator
                    app_state.render_scanline_iterator += chunk_height
                    if app_state.render_scanline_iterator >= rh:
                        app_state.render_scanline_iterator = 0
                        engine.commit_spp(1) # Signal C++ that 1 full pass is done
                        app_state.accum_spp += 1
                
                # PREVIEW LOGIC (Clay/Normals) in Idle
                else:
                    # Just render full frame once (fast)
                    raw_slice = engine.render_preview(rw, rh, app_state.preview_mode, render_threads)
                    app_state.accum_spp = 1 # Mark as done
                    slice_y_offset = 0

            # --- POST PROCESS & BLIT ---
            if raw_slice is not None:
                # Tone Mapping
                corrected = None
                if app_state.preview_mode == 2:
                    corrected = renderer.apply_tone_mapping(raw_slice)
                elif app_state.preview_mode == 1:
                    corrected = np.power(np.clip(raw_slice, 0, 1), 1.0/2.2)
                else:
                    corrected = raw_slice
                
                # To Surface
                img_uint8 = (np.clip(corrected, 0, 1) * 255).astype(np.uint8)
                img_transposed = np.transpose(img_uint8, (1, 0, 2))
                surf_slice = pygame.surfarray.make_surface(img_transposed)
                
                # Ensure Base Surface Exists and is Correct Size
                target_w = app_state.viewport_rect[2]
                target_h = app_state.viewport_rect[3]
                
                if app_state.current_image is None or \
                   app_state.current_image.get_width() != target_w or \
                   app_state.current_image.get_height() != target_h:
                    app_state.current_image = pygame.Surface((target_w, target_h))
                    app_state.current_image.fill((0,0,0))
                
                # Blit Logic
                if app_state.render_strategy == "INTERACTIVE":
                    # Scale up if needed
                    if surf_slice.get_width() != target_w or surf_slice.get_height() != target_h:
                        surf_slice = pygame.transform.scale(surf_slice, (target_w, target_h))
                    app_state.current_image.blit(surf_slice, (0, 0))
                else:
                    # Direct Blit at Offset (Scanline)
                    # We assume scale is 1:1 in Idle
                    app_state.current_image.blit(surf_slice, (0, slice_y_offset))
                
                last_render_dt = time.time() - t0
                app_state.needs_repaint = True
            # print("DEBUG: Post Process Done")
            

        
        # ---------------------------------------------------------
        # 4. SCALE & BATCH PERFORMANCE LOGIC (Only runs on active render frames)
        # ---------------------------------------------------------
        if should_render and last_render_dt > 0:
            # A. FPS Smoothing
            current_instant_fps = 1.0 / max(0.001, last_render_dt)
            app_state.current_fps = app_state.current_fps * 0.9 + current_instant_fps * 0.1
            
            # B. AUTO SCALER (Legacy Logic + Stability)
            # ONLY RUN IN INTERACTIVE MODE
            if app_state.render_strategy == "INTERACTIVE" and app_state.preview_mode == 2 and app_state.res_auto:
                # LEGACY THRESHOLDS:
                # 10 FPS (0.1s) -> Downscale
                # 35 FPS (0.028s) -> Upscale
                FPS_LOW_DT = 0.100  # 10 FPS
                FPS_HIGH_DT = 0.028 # ~35 FPS
                
                current_dt = last_render_dt
                old_scale = app_state.res_scale
                
                # Discrete steps: Extended for aggressive downscaling
                scales = [0.5, 1.0, 2.0, 4.0, 8.0, 16.0] 
                try:
                    idx = scales.index(old_scale)
                except ValueError:
                    idx = 1 # Default to 1:1
                
                # 1. DOWN-SCALING (Lag)
                if current_dt > FPS_LOW_DT:
                    app_state.res_stability -= 1
                    if app_state.res_stability <= -3: # Faster reaction (was -5)
                        if idx < len(scales) - 1:
                            app_state.res_scale = scales[idx + 1]
                        app_state.res_stability = 0
                
                # 2. UP-SCALING (Headroom)
                elif current_dt < FPS_HIGH_DT:
                    app_state.res_stability += 1
                    if app_state.res_stability >= 10: # Stability check
                        if idx > 0:
                            new_scale = scales[idx - 1]
                            # Special Rule: 0.5 (SuperSampling) only for PREVIEW modes
                            if new_scale == 0.5 and app_state.preview_mode == 2:
                                pass # Stay at 1.0 for Raytracing (too heavy)
                            else:
                                app_state.res_scale = new_scale
                        app_state.res_stability = 0
                else:
                    # Decay
                    if app_state.res_stability > 0: app_state.res_stability -= 1
                    elif app_state.res_stability < 0: app_state.res_stability += 1

                # CRITICAL: If scale changed, force a render reset
                if app_state.res_scale != old_scale:
                    app_state.needs_render_reset = True

            # C. Batch Size Adjustment
            if app_state.preview_mode == 2:
                ideal = app_state.ray_batch_size * (0.033 / last_render_dt)
                app_state.ray_batch_size = max(1, min(32, int(ideal)))
        
        real_fps = app_state.current_fps


        # ---------------------------------------------------------
        # 7. FINAL DRAWING (Consolidated to fix flickering)
        # ---------------------------------------------------------
        screen.fill((40,40,40))

        # A. Viewport
        if app_state.current_image:
             if app_state.current_image.get_width() != vw or app_state.current_image.get_height() != vh:
                final_surf = pygame.transform.scale(app_state.current_image, (vw, vh))
                screen.blit(final_surf, (vx, vy))
             else:
                screen.blit(app_state.current_image, (vx, vy))
        else:
             pygame.draw.rect(screen, (20,20,20), vp_rect)

        # B. Picking Overlay
        if app_state.picking_focus:
            # Semi-transparent background for text
            msg = "PICK FOCUS POINT (CLICK ON SCENE) OR PRESS ESC"
            f_overlay = fonts.get(14)
            txt_surf = f_overlay.render(msg, True, (255, 255, 255))
            
            # On centre le message en haut de la vue 3D
            bg_rect = txt_surf.get_rect(center=(ui_core.VIEW_W // 2, 30))
            bg_rect.inflate_ip(20, 10) # Un peu de marge
            
            pygame.draw.rect(screen, (0, 0, 0), bg_rect, border_radius=4)
            pygame.draw.rect(screen, ui_core.COL_ACCENT, bg_rect, 1, border_radius=4) # Bordure bleue
            
            txt_rect = txt_surf.get_rect(center=bg_rect.center)
            screen.blit(txt_surf, txt_rect)

        # C. Gizmo (Overlay)
        draw_gizmo(screen, app_state, vp_rect)

        # D. UI Panels
        # 1. Panel Background
        pygame.draw.rect(screen, ui_core.COL_PANEL, (ui_core.VIEW_W, 0, ui_core.PANEL_W, ui_core.WIN_H))

        # 2. Header (Top)
        header_height = 91
        pygame.draw.rect(screen, ui_core.COL_HEADER, (ui_core.VIEW_W, 0, ui_core.PANEL_W, header_height))
        pygame.draw.line(screen, ui_core.COL_BORDER, (ui_core.VIEW_W, 0), (ui_core.VIEW_W, ui_core.WIN_H))

        # 3. Widgets
        for w in ui_list: w.draw(screen, fonts)

        # 4. Footer
        panels.layout_global.draw_footer_status(screen, fonts, app_state)

        # E. Final Flip
        pygame.display.flip()
        
        # Reset redraw flag and cap frame rate
        app_state.needs_repaint = False
        clock.tick(60)

    pygame.quit()
    return None