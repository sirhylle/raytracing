import numpy as np
import math
import transforms as tf
import cpp_engine
import tkinter as tk
from tkinter import filedialog
import loader
from .ui_core import VIEW_W, VIEW_H

class EditorState:
    def __init__(self, conf, builder):
        self.builder = builder 
        self.res_scale = 1 
        self.res_auto = False
        self.preview_mode = 0 

        # --- VIEWPORT LOGIC ---
        self.target_aspect = conf.width / conf.height
        self.viewport_rect = None
        
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
        
        # UI State
        self.tool_mode = "CAM"
        self.selected_id = -1
        self.gizmo_mode = "MOVE"
        self.active_tab = "SCENE"
        self.typing_mode = False 
        self.needs_ui_rebuild = True
        
        # --- GESTION ACCORDÉONS EXCLUSIFS ---
        # Stocke le nom de la section ouverte pour chaque onglet. None si tout est fermé.
        self.accordions = {
            "SCENE": "CAMERA", # Par défaut : Camera ouvert
            "OBJECT": None     # Par défaut : Tout fermé
        }

        # Rendering State
        self.dirty = True
        self.accum_spp = 0
        self.is_rendering = False
        self.ray_batch_size = 2 
        self.current_image = None

        # --- ENVIRONMENT & SUN ---
        self.env_rotation = 0.0
        self.env_light_level = conf.env_light_level
        self.env_direct_level = conf.env_direct_level
        self.env_indirect_level = conf.env_indirect_level
        
        self.sun_id = -1
        self.sun_enabled = conf.auto_sun
        self.auto_sun_env_level = conf.auto_sun_env_level
        self.sun_intensity = conf.auto_sun_intensity
        self.sun_radius = conf.auto_sun_radius
        self.sun_dist = conf.auto_sun_dist
        self.sun_initial_dir = np.array([0.0, 1.0, 0.0]) 
        self.sun_base_color = np.array([1.0, 1.0, 1.0])

        # Init du soleil existant via le registre
        for oid, info in builder.registry.items():
            if info['type'] == 'light_sun':
                self.sun_id = oid
                self.sun_enabled = True
                pos = np.array(info['pos'])
                dist = np.linalg.norm(pos)
                if dist > 0:
                    self.sun_dist = dist
                    self.sun_initial_dir = pos / dist
                self.sun_radius = info['scale'][0]
                self.sun_base_color = np.array(info['raw_color'])
                break

    # --- LOGIQUE MÉTIER ---

    def set_active_tab(self, tab_name):
        """Change l'onglet et demande une reconstruction UI"""
        if self.active_tab != tab_name:
            self.active_tab = tab_name
            self.needs_ui_rebuild = True

    def toggle_accordion(self, tab, section_name):
        """Ouvre 'section_name' dans l'onglet 'tab' et ferme les autres. Si déjà ouvert, le ferme."""
        if self.accordions[tab] == section_name:
            self.accordions[tab] = None
        else:
            self.accordions[tab] = section_name
        self.needs_ui_rebuild = True

    def is_accordion_open(self, tab, section_name):
        return self.accordions.get(tab) == section_name

    def get_selected_info(self):
        if self.selected_id != -1 and self.selected_id in self.builder.registry:
            return self.builder.registry[self.selected_id]
        return None

    def calculate_viewport(self, win_w, win_h):
        """Calcule le rectangle d'affichage (Letterbox/Pillarbox)"""
        window_ratio = win_w / win_h
        target_ratio = self.target_aspect
        
        if window_ratio > target_ratio:
            # Bandes verticales
            h = win_h
            w = int(h * target_ratio)
            x = (win_w - w) // 2
            y = 0
        else:
            # Bandes horizontales
            w = win_w
            h = int(w / target_ratio)
            x = 0
            y = (win_h - h) // 2
            
        # On utilise pygame.Rect ici (nécessite import pygame ou juste structure compatible)
        # Comme on est dans state.py sans pygame importé, on peut renvoyer un tuple ou importer pygame.
        # Pour faire simple, importons pygame en haut ou utilisons un objet simple.
        # Ici on suppose que le caller (main.py) utilisera ces valeurs.
        self.viewport_rect = (x, y, w, h)

    def update_transform(self, engine):
        data = self.get_selected_info()
        if not data: return
        pos, rot, scl = data['pos'], data['rot'], data['scale']
        M = tf.translate(pos[0], pos[1], pos[2]) @ \
            tf.rotate_y(rot[1]) @ tf.rotate_x(rot[0]) @ tf.rotate_z(rot[2]) @ \
            tf.scale(scl[0], scl[1], scl[2])
        InvM = np.linalg.inv(M)
        engine.update_instance_transform(self.selected_id, 
                                         np.ascontiguousarray(M, dtype=np.float32), 
                                         np.ascontiguousarray(InvM, dtype=np.float32))
        self.dirty = True

    def push_material_update(self, engine):
        d = self.get_selected_info()
        if not d: return
        ctype = d.get('mat_type', 'lambertian')
        ccol  = d.get('color', [0.8, 0.8, 0.8])
        cfuzz = d.get('fuzz', 0.0)
        cir   = d.get('ir', 1.5)
        engine.update_instance_material(self.selected_id, ctype, cpp_engine.Vec3(*ccol), cfuzz, cir)
        self.dirty = True

    def load_new_env_map(self, engine):
        root = tk.Tk(); root.withdraw(); root.attributes('-topmost', True)
        file_path = filedialog.askopenfilename(title="Load Environment Map", filetypes=[("HDR/IMG", "*.hdr *.exr *.jpg *.png")], initialdir="./env-maps")
        root.destroy()
        if not file_path: return
        
        # Nettoyage ancien soleil
        if self.sun_id != -1:
            engine.remove_instance(self.sun_id)
            if self.sun_id in self.builder.registry: del self.builder.registry[self.sun_id]
            self.sun_id = -1
            self.sun_enabled = False

        # Chargement via Loader
        loader.load_environment(
            self.builder, file_path,
            env_direct_level=self.env_direct_level, env_light_level=self.env_light_level, env_indirect_level=self.env_indirect_level,
            auto_sun=True, auto_sun_intensity=self.sun_intensity, auto_sun_radius=self.sun_radius,
            auto_sun_dist=self.sun_dist, auto_sun_env_level=self.auto_sun_env_level
        )
        
        # Reconnexion ID Soleil
        for oid, info in self.builder.registry.items():
            if info['type'] == 'light_sun':
                self.sun_id = oid
                pos = np.array(info['pos'])
                dist = np.linalg.norm(pos)
                if dist > 0: self.sun_initial_dir = pos / dist
                self.sun_base_color = info['raw_color']
                break
        
        self.sun_enabled = (self.sun_id != -1)
        self.env_rotation = 0.0
        self.update_environment(engine)
        if hasattr(engine, 'reset_accumulation'): engine.reset_accumulation()
        self.accum_spp = 0

    def update_environment(self, engine):
        lighting_level = self.auto_sun_env_level if (self.sun_enabled and self.sun_id != -1) else self.env_light_level
        engine.set_env_rotation(self.env_rotation)
        engine.set_env_levels(self.env_direct_level, lighting_level, self.env_indirect_level)
        
        # CREATE
        if self.sun_enabled and self.sun_id == -1:
            engine.set_env_rotation(0.0)
            new_id, dir_arr, raw_col_arr = loader.create_auto_sun(
                self.builder, self.sun_intensity, self.sun_radius, self.sun_dist
            )
            self.sun_id = new_id
            self.sun_initial_dir = dir_arr
            self.sun_base_color = raw_col_arr
            engine.set_env_rotation(self.env_rotation)

        # DESTROY
        elif not self.sun_enabled and self.sun_id != -1:
            engine.remove_instance(self.sun_id)
            if self.sun_id in self.builder.registry: del self.builder.registry[self.sun_id]
            self.sun_id = -1

        # UPDATE
        if self.sun_id != -1:
            rad = math.radians(self.env_rotation) 
            c, s = math.cos(rad), math.sin(rad)
            x0, z0 = self.sun_initial_dir[0], self.sun_initial_dir[2]
            new_x, new_z = x0 * c - z0 * s, x0 * s + z0 * c
            new_y = self.sun_initial_dir[1]
            final_pos = np.array([new_x, new_y, new_z]) * self.sun_dist
            
            rad_scale = self.sun_radius
            M = tf.translate(final_pos[0], final_pos[1], final_pos[2]) @ tf.scale(rad_scale, rad_scale, rad_scale)
            InvM = np.linalg.inv(M)
            engine.update_instance_transform(self.sun_id, np.ascontiguousarray(M, dtype=np.float32), np.ascontiguousarray(InvM, dtype=np.float32))
            
            raw_intensity = max(self.sun_base_color[0], max(self.sun_base_color[1], self.sun_base_color[2]))
            if raw_intensity <= 0: raw_intensity = 1.0
            scale = self.sun_intensity / raw_intensity
            r, g, b = self.sun_base_color[0] * scale, self.sun_base_color[1] * scale, self.sun_base_color[2] * scale
            engine.update_instance_material(self.sun_id, "invisible_light", cpp_engine.Vec3(r, g, b), 0.0, 1.0)
            
        self.dirty = True