"""
================================================================================================
MODULE: EDITOR STATE
================================================================================================

DESCRIPTION:
  Holds the entire state of the Editor application.
  This class acts as a central repository for:
  - Camera parameters (Pos, Yaw, Pitch).
  - Selection state (Which object is selected?).
  - UI state (Which tab is open?).
  - Rendering state (Resolution, SPP progress).
  - Interaction state (Gizmo modes, Typing in fields).

  It also provides helper methods for:
  - Viewport calculations (Aspect Ratio handling).
  - Serializing/Deserializing the scene (Save/Load JSON).
  - Syncing Python state with the C++ Engine (update_transform, etc.).

================================================================================================
"""
import numpy as np
import math
import transforms as tf
import cpp_engine
import copy
import tkinter as tk
from tkinter import filedialog
import loader
import os
import json
import copy
from .ui_core import VIEW_W, VIEW_H

class EditorState:
    def __init__(self, conf, builder):
        self.conf = conf
        self.builder = builder 
        self.res_scale = 1
        self.current_fps = 0.0
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
        # --- ADAPTIVE MOVE SPEED ---
        # Règle du pouce : traverser la distance initiale en ~1 à 2 secondes.
        self.move_speed = max(1.0, length * 0.8)
        #self.move_speed = 5.0 
        direction = direction / length if length > 0 else np.array([0, 0, -1])
        self.pitch = math.asin(np.clip(direction[1], -0.99, 0.99))
        self.yaw = math.atan2(direction[0], direction[2])
        self.vfov = conf.vfov
        self.aperture = conf.aperture
        self.focus_dist = conf.focus_dist
        
        # UI State
        self.picking_focus = False
        self.selected_id = -1
        self.gizmo_mode = "MOVE"
        self.active_tab = "SCENE"
        self.typing_mode = False 
        self.needs_ui_rebuild = True
        self.axis_mode = "LOCAL" # "NONE", "LOCAL", "GLOBAL"
        
        # --- GESTION ACCORDÉONS EXCLUSIFS ---
        # Stocke le nom de la section ouverte pour chaque onglet. None si tout est fermé.
        self.accordions = {
            "SCENE": "CAMERA", # Par défaut : Camera ouvert
            "OBJECT": None,     # Par défaut : Tout fermé
            "CREATE": "PRIMITIVES", # Par défaut : Primitives ouvert
            "RENDER": "OUTPUT" # On ouvre "Output" par défaut
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
        self.env_clipping_multiplier = conf.clipping_multiplier if hasattr(conf, 'clipping_multiplier') else 20.0
        self.env_clipping_enabled = True # Remplacé par True par défaut pour l'instant
        self.env_median_luminance = 0.0 
        
        # Tentative de récupération de la médiane depuis le setup initial du moteur
        init_thresh = builder.engine.get_env_clipping_threshold()
        if init_thresh > 0 and init_thresh < float('inf') and self.env_clipping_multiplier > 0:
            self.env_median_luminance = init_thresh / self.env_clipping_multiplier

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

    def update_resolution(self, w, h):
        """Change la résolution et recalcule le viewport dynamique."""
        self.conf.width = int(w)
        self.conf.height = int(h)
        self.target_aspect = self.conf.width / self.conf.height
        
        # On recalcule le rectangle d'affichage (Letterboxing)
        # Note: On a besoin de VIEW_W/H. Ils sont importés depuis ui_core.
        self.calculate_viewport(VIEW_W, VIEW_H)
        
        # On force la mise à jour caméra (pour le nouvel aspect ratio)
        self.dirty = True
        self.accum_spp = 0
        if hasattr(self.builder.engine, 'reset_accumulation'): 
            self.builder.engine.reset_accumulation()

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
        median = loader.load_environment(
            self.builder, file_path,
            env_direct_level=self.env_direct_level, env_light_level=self.env_light_level, env_indirect_level=self.env_indirect_level,
            auto_sun=True, auto_sun_intensity=self.sun_intensity, auto_sun_radius=self.sun_radius,
            auto_sun_dist=self.sun_dist, auto_sun_env_level=self.auto_sun_env_level,
            clipping_multiplier=self.env_clipping_multiplier
        )
        self.env_median_luminance = median
        
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
        
        # Mise à jour directe du clipping (via API Engine)
        if hasattr(engine, 'get_env_clipping_threshold'): # Safety check
            thresh = float('inf')
            
            # Application si activé explicitement
            if self.env_clipping_enabled:
                 # Si le soleil est actif OU qu'on a un multiplicateur explicite (même 0)
                 if self.sun_enabled:
                      thresh = self.env_median_luminance * self.env_clipping_multiplier
            
            # Optimisation: On ne set que si ça change vraiment pour éviter le rebuild_cdf coûteux
            current_thresh = engine.get_env_clipping_threshold()
            # Si thresh est infini et current aussi, pas de chgt
            # Si diff > epsilon, on change
            if abs(current_thresh - thresh) > 1e-3:
                 engine.set_env_clipping_threshold(thresh)

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

    def duplicate_selection(self, engine):
        """Duplique l'objet sélectionné en passant par le Builder."""
        if self.selected_id == -1: return

        # 1. Copie des données sources
        src_data = self.get_selected_info()
        if not src_data: return
        
        # Deepcopy pour éviter les références partagées
        data = copy.deepcopy(src_data)
        
        # 2. Préparation des arguments communs
        otype = data['type']
        pos = data['pos']
        rot = data.get('rot', [0.0, 0.0, 0.0]) # Le loader stocke ça en degrés
        scale = data['scale']
        col = data.get('color', [0.8, 0.8, 0.8])
        mat = data.get('mat_type', 'lambertian')
        fuzz = data.get('fuzz', 0.0)
        ir = data.get('ir', 1.5)

        new_id = -1

        # 3. Appel au Builder (Logique miroir de loader.py)
        # Le builder va créer l'objet C++ ET remplir le registre pour nous.
        
        if otype == 'sphere':
            # add_sphere(center, radius, mat_type, color, fuzz, ir)
            # Le loader gère la conversion liste -> Vec3
            new_id = self.builder.add_sphere(pos, scale[0], mat, col, fuzz, ir)

        elif otype == 'mesh':
            # add_mesh_instance(mesh_name, pos, rot, scale)
            # Les Cubes sont gérés ici s'ils sont des meshes
            name = data.get('name', 'Unknown')
            new_id = self.builder.add_mesh_instance(name, pos, rot, scale)
            
        elif otype == 'light_sun':
             # add_invisible_sphere_light(center, radius, color, raw_color)
             raw = data.get('raw_color', col)
             new_id = self.builder.add_invisible_sphere_light(pos, scale[0], col, raw)

        elif otype == 'checker_sphere':
            # add_checker_sphere(center, radius, c1, c2, scale)
            c2 = data.get('color2', [0.0, 0.0, 0.0])
            tex_scale = data.get('texture_scale', 4.0)
            new_id = self.builder.add_checker_sphere(pos, scale[0], col, c2, tex_scale)

        elif otype == 'quad':
            # add_quad(Q, u, v, mat_type, color, fuzz, ir)
            # Grâce à ta modif, on passe les listes u/v direct !
            u_vec = data.get('u', [1,0,0])
            v_vec = data.get('v', [0,1,0])
            new_id = self.builder.add_quad(pos, u_vec, v_vec, mat, col, fuzz, ir)
             
        # 4. Finalisation UX
        if new_id != -1:
            # On ne change pas le nom pour l'instant car il sert à retrouver les meshes
            if 'name' in self.builder.registry[new_id]:
                pass
                #self.builder.registry[new_id]['name'] = f"{self.builder.registry[new_id]['name']}_copy"

            # On sélectionne le nouvel objet et on active le mode MOVE
            self.selected_id = new_id
            self.gizmo_mode = "MOVE"
            
            # On force une mise à jour visuelle
            self.needs_ui_rebuild = True
            self.dirty = True
            print(f"Duplicate: ID {self.selected_id} created.")

    def add_primitive(self, type_key):
        """Crée un objet devant la caméra."""
        
        # 1. Calcul de la position de spawn (devant la caméra)
        # On recrée le vecteur forward
        fx = math.sin(self.yaw) * math.cos(self.pitch)
        fy = math.sin(self.pitch)
        fz = math.cos(self.yaw) * math.cos(self.pitch)
        fwd = np.array([fx, fy, fz])
        
        spawn_pos = self.cam_pos + (fwd * 5.0) # 5 unités devant
        spawn_pos_list = spawn_pos.tolist()

        new_id = -1
        
        # 2. Création selon le type
        if type_key == "sphere":
            new_id = self.builder.add_sphere(spawn_pos_list, 1.0, "lambertian", [0.8, 0.8, 0.8])
            
        elif type_key == "cube":
             # Le cube n'est pas une primitive native C++, on utilise add_mesh_instance 
             # (Il faut que 'cube.obj' existe dans assets/ ou soit généré procéduralement... 
             # Pour l'instant, disons qu'on fait une sphère carrée si tu n'as pas de cube loaded :D 
             # Ou mieux : On triche en ajoutant un mesh cube par défaut dans le moteur C++ ?)
             # SI tu n'as pas de cube.obj, utilise une sphere pour tester.
             pass 

        elif type_key == "light_sphere":
            new_id = self.builder.add_invisible_sphere_light(spawn_pos_list, 1.0, [10,10,10], [10,10,10])
            
        elif type_key == "quad_floor":
             # Un quad plat au sol (XZ)
             center = spawn_pos_list
             y = center[1]
             s = 5.0 # taille
             Q = [center[0]-s, y, center[2]-s]
             u = [2*s, 0, 0]
             v = [0, 0, 2*s]
             new_id = self.builder.add_quad(Q, u, v, "lambertian", [0.5, 0.5, 0.5])

        elif type_key == "quad_wall":
             # Un quad vertical (XY)
             center = spawn_pos_list
             z = center[2]
             s = 5.0
             Q = [center[0]-s, center[1]-s, z]
             u = [2*s, 0, 0]
             v = [0, 2*s, 0]
             new_id = self.builder.add_quad(Q, u, v, "lambertian", [0.8, 0.2, 0.2])

        # 3. Sélection automatique
        if new_id != -1:
            self.selected_id = new_id
            self.gizmo_mode = "MOVE"
            self.set_active_tab("OBJECT") # On switch sur l'onglet objet pour l'éditer direct
            self.dirty = True
            self.needs_ui_rebuild = True
            
    # --- SYSTÈME DE SAUVEGARDE / CHARGEMENT ---

    def save_scene(self, filepath):
        """Sérialise la scène complète en JSON, incluant la config de rendu."""
        
        # 1. Calcul du LookAt actuel (depuis yaw/pitch)
        fx = math.sin(self.yaw) * math.cos(self.pitch)
        fy = math.sin(self.pitch)
        fz = math.cos(self.yaw) * math.cos(self.pitch)
        target = self.cam_pos + np.array([fx, fy, fz])

        # 2. Construction du Dictionnaire
        data = {
            "version": "1.1", # On incrémente légèrement
            
            # A. Paramètres Globaux (Render, System, Animation) [MIS A JOUR]
            "render_settings": {
                # Render
                "width": self.conf.width,
                "height": self.conf.height,
                "spp": self.conf.spp,
                "depth": self.conf.depth,
                
                # System
                "param_stamp": getattr(self.conf, 'param_stamp', False),
                "save_raw": getattr(self.conf, 'save_raw', False),
                
                # Animation
                "animate": getattr(self.conf, 'animate', False),
                "frames": getattr(self.conf, 'frames', 0),
                "fps": getattr(self.conf, 'fps', 24),
                "turntable_radius": getattr(self.conf, 'radius', 0.0) # Renommé pour clarté
            },

            # B. Caméra
            "camera": {
                "lookfrom": self.cam_pos.tolist(),
                "lookat": target.tolist(),
                "vfov": self.vfov,
                "aperture": self.aperture,
                "focus_dist": self.focus_dist
            },

            # C. Environnement (inchangé)
            "environment": {
                "map_path": self.conf.env_map,
                "light_level": self.env_light_level,
                "direct_level": self.env_direct_level,
                "indirect_level": self.env_indirect_level,
                "rotation": self.env_rotation,
                "auto_sun": self.sun_enabled,
                "sun_intensity": self.sun_intensity,
                "sun_radius": self.sun_radius,
                "sun_dist": self.sun_dist,
                "sun_env_level": self.auto_sun_env_level
            },

            # D. Liste des Objets (inchangé)
            "objects": []
        }

        # 3. Remplissage des objets
        cwd = os.getcwd()
        for oid, info in self.builder.registry.items():
            if info['type'] == 'light_sun': continue # Géré par Environment

            obj_data = copy.deepcopy(info)
            # Chemins relatifs pour les assets
            if 'asset_name' in obj_data:
                if os.path.exists(obj_data['asset_name']):
                    obj_data['asset_name'] = os.path.relpath(obj_data['asset_name'], cwd)
            
            data["objects"].append(obj_data)

        # 4. Écriture
        try:
            with open(filepath, 'w') as f:
                json.dump(data, f, indent=4)
            print(f"[System] Scene saved to {filepath}")
        except Exception as e:
            print(f"[System] Save Failed: {e}")
    
    def load_scene(self, filepath):
        """Charge une scène JSON et restaure la config complète."""
        if not os.path.exists(filepath): return

        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
        except Exception as e:
            print(f"[System] Load Failed: {e}")
            return

        print(f"[System] Loading scene: {filepath}...")

        # 1. NETTOYAGE (Clear Scene)
        ids_to_remove = list(self.builder.registry.keys())
        for oid in ids_to_remove:
            self.builder.engine.remove_instance(oid)
        self.builder.registry.clear()
        self.selected_id = -1
        self.sun_id = -1

        # 2. RESTAURATION SETTINGS [MIS A JOUR]
        if "render_settings" in data:
            rs = data["render_settings"]
            
            # Render
            self.conf.width = rs.get("width", self.conf.width)
            self.conf.height = rs.get("height", self.conf.height)
            self.conf.spp = rs.get("spp", self.conf.spp)
            self.conf.depth = rs.get("depth", self.conf.depth)
            
            # System
            if "param_stamp" in rs: self.conf.param_stamp = rs["param_stamp"]
            if "save_raw" in rs: self.conf.save_raw = rs["save_raw"]
            
            # Animation
            if "animate" in rs: self.conf.animate = rs["animate"]
            if "frames" in rs: self.conf.frames = rs["frames"]
            if "fps" in rs: self.conf.fps = rs["fps"]
            if "turntable_radius" in rs: self.conf.radius = rs["turntable_radius"]

            # Mise à jour Aspect Ratio Viewport
            if self.conf.height > 0:
                self.target_aspect = self.conf.width / self.conf.height

        # 3. RESTAURATION CAMÉRA (inchangé)
        cam = data["camera"]
        self.cam_pos = np.array(cam["lookfrom"], dtype=np.float32)
        target = np.array(cam["lookat"], dtype=np.float32)
        direction = target - self.cam_pos
        length = np.linalg.norm(direction)
        direction = direction / length if length > 0 else np.array([0, 0, -1])
        self.pitch = math.asin(np.clip(direction[1], -0.99, 0.99))
        self.yaw = math.atan2(direction[0], direction[2])
        
        self.vfov = cam.get("vfov", 40)
        self.aperture = cam.get("aperture", 0.0)
        self.focus_dist = cam.get("focus_dist", 10.0)
        self.move_speed = max(1.0, length * 0.8)

        # 4. RESTAURATION ENVIRONNEMENT (inchangé)
        env = data["environment"]
        self.env_light_level = env.get("light_level", 1.0)
        self.env_direct_level = env.get("direct_level", 1.0)
        self.env_indirect_level = env.get("indirect_level", 1.0)
        self.env_rotation = env.get("rotation", 0.0)
        self.sun_enabled = env.get("auto_sun", False)
        self.sun_intensity = env.get("sun_intensity", 50.0)
        self.sun_radius = env.get("sun_radius", 10.0)
        self.sun_dist = env.get("sun_dist", 1000.0)
        self.auto_sun_env_level = env.get("sun_env_level", 1.0)
        
        env_map_path = env.get("map_path")
        if env_map_path:
             if not os.path.isabs(env_map_path):
                 env_map_path = os.path.abspath(os.path.join(os.getcwd(), env_map_path))
             
             self.env_median_luminance = loader.load_environment(
                 self.builder, env_map_path,
                 env_light_level=self.env_light_level,
                 env_direct_level=self.env_direct_level,
                 env_indirect_level=self.env_indirect_level,
                 auto_sun=self.sun_enabled,
                 auto_sun_intensity=self.sun_intensity,
                 auto_sun_radius=self.sun_radius,
                 auto_sun_dist=self.sun_dist,
                 auto_sun_env_level=self.auto_sun_env_level,
                 clipping_multiplier=self.env_clipping_multiplier
             )
        
        self.builder.engine.set_env_rotation(self.env_rotation)
        
        # Récup ID Soleil
        for oid, info in self.builder.registry.items():
            if info['type'] == 'light_sun':
                self.sun_id = oid
                p = np.array(info['pos'])
                d = np.linalg.norm(p)
                if d > 0: self.sun_initial_dir = p/d
                break

        # 5. RESTAURATION OBJETS (inchangé)
        cwd = os.getcwd()
        for obj in data["objects"]:
            otype = obj["type"]
            pos = obj["pos"]
            rot = obj.get("rot", [0,0,0])
            scale = obj["scale"]
            mat = obj.get("mat_type", "lambertian")
            col = obj.get("color", [0.8, 0.8, 0.8])
            fuzz = obj.get("fuzz", 0.0)
            ir = obj.get("ir", 1.5)
            name = obj.get("name") 

            new_id = -1
            if otype == "sphere":
                new_id = self.builder.add_sphere(pos, scale[0], mat, col, fuzz, ir)
            elif otype == "mesh":
                asset_name = obj.get("asset_name")
                # Pas de logique complexe ici, add_mesh_instance gère l'appel moteur
                new_id = self.builder.add_mesh_instance(asset_name, pos, rot, scale)
            elif otype == "checker_sphere":
                c2 = obj.get("color2", [0,0,0])
                tscale = obj.get("texture_scale", 10.0)
                new_id = self.builder.add_checker_sphere(pos, scale[0], col, c2, tscale)
            elif otype == "quad":
                u = obj.get("u", [1,0,0])
                v = obj.get("v", [0,1,0])
                new_id = self.builder.add_quad(pos, u, v, mat, col, fuzz, ir)

            if new_id != -1 and name:
                self.builder.registry[new_id]['name'] = name

        self.dirty = True
        self.needs_ui_rebuild = True
        print("[System] Scene loaded successfully.")
    
    def save_scene_dialog(self):
        """Ouvre le dialogue système pour sauvegarder."""
        root = tk.Tk(); root.withdraw(); root.attributes('-topmost', True)
        f = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON Scene", "*.json")], initialdir="./scenes")
        root.destroy()
        if f: self.save_scene(f)

    def load_scene_dialog(self):
        """Ouvre le dialogue système pour charger."""
        root = tk.Tk(); root.withdraw(); root.attributes('-topmost', True)
        f = filedialog.askopenfilename(filetypes=[("JSON Scene", "*.json")], initialdir="./scenes")
        root.destroy()
        if f: self.load_scene(f)