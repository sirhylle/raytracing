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
        app_state.dirty = True

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
        18: pygame.font.SysFont("Arial", 18, bold=True)
    }
    
    app_state = state.EditorState(config, builder)
    app_state.calculate_viewport(ui_core.VIEW_W, ui_core.WIN_H)

    # On convertit le tuple viewport en Rect Pygame pour être tranquille
    vx, vy, vw, vh = app_state.viewport_rect
    vp_rect = pygame.Rect(vx, vy, vw, vh)
    
    # Threading config
    render_threads = config.threads if config.threads > 0 else max(1, multiprocessing.cpu_count() - 2)

    ui_list = []
    
    # Variables pour l'hysteresis de résolution (Qualité dynamique)
    last_render_dt = 0.03
    
    def start_render():
        if app_state.is_rendering: return
        app_state.is_rendering = True
        # Update config object for renderer
        config.lookfrom = app_state.cam_pos.tolist()
        fx, fy, fz = math.sin(app_state.yaw)*math.cos(app_state.pitch), math.sin(app_state.pitch), math.cos(app_state.yaw)*math.cos(app_state.pitch)
        config.lookat = (app_state.cam_pos + np.array([fx, fy, fz])).tolist()
        config.vfov, config.aperture, config.focus_dist = app_state.vfov, app_state.aperture, app_state.focus_dist
        threading.Thread(target=render_thread_task, args=(engine, config, app_state)).start()

    # [HELPER] Fonction de reconstruction UI
    def rebuild_ui():
        ui_list.clear()
        content_start_y = panels.layout_global.build_global_layout(ui_list, app_state, engine, start_render)
        
        if app_state.active_tab == "SCENE":
            panels.tab_scene.build(ui_list, content_start_y+2, app_state, engine)
        elif app_state.active_tab == "OBJECT":
            panels.tab_object.build(ui_list, content_start_y+2, app_state, engine)
        
        app_state.needs_ui_rebuild = False

    # Premier build
    rebuild_ui()

    running = True
    last_time = time.time()
    last_render_dt = 0.03 # Init var

    while running:
        clock.tick()
        now = time.time()
        dt = now - last_time
        last_time = now

        # Écran de chargement si rendu offline en cours
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
                    app_state.dirty = True
            
            # B. Viewport Interaction (Seulement si l'UI n'a pas capturé l'event)
            if not ui_captured and not app_state.typing_mode:
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE: running = False
                
                # Clic Gauche : Sélection ou Gizmo
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and in_viewport:
                    is_shift = keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]
                    # Mode Selection ou Shift+Click
                    if app_state.tool_mode == "SEL" or (app_state.tool_mode == "CAM" and is_shift):
                        pid = engine.pick_instance_id(vp_rect.width, vp_rect.height, mouse_x_rel, mouse_y_rel)
                        app_state.selected_id = pid
                        app_state.dirty = True
                        app_state.needs_ui_rebuild = True
                        if pid != -1:
                            app_state.set_active_tab("OBJECT")
                            app_state.tool_mode = "SEL"
                        else:
                            app_state.set_active_tab("SCENE")
                    
                    # Mode Focus
                    elif app_state.tool_mode == "FOCUS":
                        res = engine.pick_focus_distance(vp_rect.width, vp_rect.height, mouse_x_rel, mouse_y_rel)
                        if res[0] > 0:
                            app_state.focus_dist = res[0]
                            app_state.dirty = True

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
                        app_state.dirty = True
                    
                    # Panoramique (Molette maintenue)
                    if mouse_btns[1]:
                         dx, dy = event.rel
                         app_state.cam_pos[1] -= dy * 0.05
                         app_state.dirty = True

                    # Gizmo / Interaction Objet (Clic Gauche maintenu)
                    if mouse_btns[0] and in_viewport and app_state.selected_id != -1 and app_state.tool_mode != "CAM":
                        dx, dy = event.rel
                        data = app_state.get_selected_info()
                        if data:
                            scale_factor = 0.01 * (app_state.focus_dist / 5.0)
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

                # Zoom (Molette)
                elif event.type == pygame.MOUSEWHEEL and in_viewport:
                    fx = math.sin(app_state.yaw) * math.cos(app_state.pitch)
                    fy = math.sin(app_state.pitch)
                    fz = math.cos(app_state.yaw) * math.cos(app_state.pitch)
                    app_state.cam_pos += np.array([fx, fy, fz]) * event.y * 1.0
                    app_state.dirty = True

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
                app_state.dirty = True

        # 3. ENGINE UPDATE (Camera)
        scene_changed = app_state.dirty
        if app_state.dirty:
            fx = math.sin(app_state.yaw) * math.cos(app_state.pitch)
            fy = math.sin(app_state.pitch)
            fz = math.cos(app_state.yaw) * math.cos(app_state.pitch)
            lookat = app_state.cam_pos + np.array([fx, fy, fz])
            engine.set_camera(cpp_engine.Vec3(*app_state.cam_pos), cpp_engine.Vec3(*lookat), cpp_engine.Vec3(0,1,0),
                              app_state.vfov, app_state.target_aspect, app_state.aperture, app_state.focus_dist)
            if hasattr(engine, 'reset_accumulation'): engine.reset_accumulation()
            app_state.accum_spp = 0; app_state.dirty = False

        # 4. RENDER & DRAW
        screen.fill((0,0,0))
        
        # A. Render Logic
        should_render = False
        if app_state.preview_mode == 2: # RAY
            # En Raytracing : On rend si ça a bougé OU si l'image n'est pas finie (SPP < Max)
            if scene_changed or app_state.accum_spp < config.spp: 
                should_render = True
        else: # CLAY / NORMALS
            # En Preview : On rend SEULEMENT si ça a bougé (ou si on n'a pas encore d'image du tout)
            if scene_changed or app_state.current_image is None: 
                should_render = True
            
        render_w, render_h = vp_rect.width, vp_rect.height
        
        if should_render:
            t0 = time.time()
            
            # Hysteresis Scale (Adaptation dynamique qualité)
            scale = app_state.res_scale
            if app_state.res_auto:
                if scale == 1 and last_render_dt > 0.06: scale = 2
                elif scale == 2 and last_render_dt > 0.06: scale = 4
                elif scale == 4 and last_render_dt < 0.016: scale = 2
                elif scale == 2 and last_render_dt < 0.016: scale = 1
                else: scale = 1
            
            rw, rh = max(1, render_w // scale), max(1, render_h // scale)

            if app_state.preview_mode == 2: # RAY
                batch = app_state.ray_batch_size
                raw = engine.render_accumulate(render_w, render_h, batch, render_threads)
                app_state.accum_spp += batch
            else: # PREVIEW
                raw = engine.render_preview(rw, rh, app_state.preview_mode, render_threads)
                app_state.accum_spp = 0 # Pas d'accumulation en preview
            
            # Tone Mapping & Post Process
            if app_state.preview_mode == 2:
                corrected = renderer.apply_tone_mapping(raw)
            elif app_state.preview_mode == 1: # Clay
                corrected = np.power(np.clip(raw, 0, 1), 1.0/2.2)
            else: # Normals
                corrected = raw

            # Conversion Surface Pygame
            img_uint8 = (np.clip(corrected, 0, 1) * 255).astype(np.uint8)
            img_transposed = np.transpose(img_uint8, (1, 0, 2))
            surf = pygame.surfarray.make_surface(img_transposed)
            
            if scale > 1:
                surf = pygame.transform.scale(surf, (render_w, render_h))
            
            app_state.current_image = surf
            last_render_dt = time.time() - t0

            # On met à jour le FPS seulement quand on calcule une image
            # On calcule le FPS basé sur le temps de rendu (Render FPS) et non le Loop FPS
            real_fps = 1.0 / max(0.001, last_render_dt)
            if len(ui_list) > 0 and isinstance(ui_list[0], ui_core.Label):
                ui_list[0].text = f"FPS: {real_fps:.0f}"
            
            # Ajustement auto batch size pour le Raytracing
            if app_state.preview_mode == 2 and last_render_dt > 0.001:
                ideal = app_state.ray_batch_size * (0.033 / last_render_dt)
                app_state.ray_batch_size = max(1, min(32, int(ideal)))

        # B. Blit Image
        if app_state.current_image:
            screen.blit(app_state.current_image, (vp_rect.x, vp_rect.y))

        # C. Draw UI Panel
        # 1. Fond Panel (Gris moyen - Remplissage total)
        pygame.draw.rect(screen, ui_core.COL_PANEL, (ui_core.VIEW_W, 0, ui_core.PANEL_W, ui_core.WIN_H))

        # 2. Header (Haut)
        header_height = 200
        pygame.draw.rect(screen, ui_core.COL_HEADER, (ui_core.VIEW_W, 0, ui_core.PANEL_W, header_height))
        pygame.draw.line(screen, ui_core.COL_BORDER, (ui_core.VIEW_W, 0), (ui_core.VIEW_W, ui_core.WIN_H))
        #pygame.draw.line(screen, ui_core.COL_BORDER, (ui_core.VIEW_W, header_height), (ui_core.WIN_W, header_height))

        # 3. Footer (Bas)
        footer_h = 50 # Hauteur fixe pour le footer
        footer_y = ui_core.WIN_H - footer_h
        # Fond sombre
        pygame.draw.rect(screen, ui_core.COL_HEADER, (ui_core.VIEW_W, footer_y, ui_core.PANEL_W, footer_h))
        # Ligne de séparation (Bordure du haut du footer)
        pygame.draw.line(screen, ui_core.COL_BORDER, (ui_core.VIEW_W, footer_y), (ui_core.WIN_W, footer_y))

        
        
        for w in ui_list: w.draw(screen, fonts)
        
        pygame.display.flip()

    pygame.quit()
    # Retour pour le mode replay
    return {
        'lookfrom': app_state.cam_pos.tolist(),
        'lookat': (app_state.cam_pos + np.array([math.sin(app_state.yaw), math.sin(app_state.pitch), math.cos(app_state.yaw)])).tolist(),
        'vfov': app_state.vfov,
        'aperture': app_state.aperture,
        'focus_dist': app_state.focus_dist
    }