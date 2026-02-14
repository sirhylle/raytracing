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
import meshloader
import serializer
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
        self.res_stability = 0 # Counter for auto-scaling hysteresis (jitter filter)
        self.res_auto = True
        self.preview_mode = 0 
        self.preview_depth = 6
        self.preview_sampler = 0 # 0=Random, 1=Sobol
        self.render_sampler = 1  # 0=Random, 1=Sobol 

        # --- VIEWPORT LOGIC ---
        self.target_aspect = conf.render.width / conf.render.height
        self.viewport_rect = None
        
        # Camera
        self.cam_pos = np.array(conf.camera.lookfrom, dtype=np.float32)
        target = np.array(conf.camera.lookat, dtype=np.float32)
        direction = target - self.cam_pos
        length = np.linalg.norm(direction)
        # --- ADAPTIVE MOVE SPEED ---
        # Rule of thumb: traverse initial distance in ~1 to 2 seconds.
        self.move_speed = max(1.0, length * 0.8)
        #self.move_speed = 5.0 
        direction = direction / length if length > 0 else np.array([0, 0, -1])
        self.pitch = math.asin(np.clip(direction[1], -0.99, 0.99))
        self.yaw = math.atan2(direction[0], direction[2])
        self.vfov = conf.camera.vfov
        self.aperture = conf.camera.aperture
        self.focus_dist = conf.camera.focus_dist
        
        # UI State
        self.picking_focus = False
        self.selected_id = -1
        self.gizmo_mode = "MOVE"
        self.active_tab = "SCENE"
        self.typing_mode = False 
        # Reset State
        self.needs_render_reset = True
        self.needs_ui_rebuild = True
        self.needs_repaint = True
        self.accum_spp = 0
        self.axis_mode = "LOCAL" # "NONE", "LOCAL", "GLOBAL"
        
        # --- EXCLUSIVE ACCORDION MANAGEMENT ---
        # Stores the name of the open section for each tab. None if all closed.
        self.accordions = {
            "SCENE": "CAMERA", # Par défaut : Camera ouvert
            "OBJECT": None,     # Par défaut : Tout fermé
            "CREATE": "PRIMITIVES", # Par défaut : Primitives ouvert
            "RENDER": "OUTPUT" # On ouvre "Output" par défaut
        }

        # Rendering & IO State
        # GRANULAR DIRTY FLAGS (UI Refactor)
        self.needs_ui_rebuild = True   # Layout changed -> Rebuild UI list
        self.needs_repaint = True      # Visual change -> Redraw screen




        
        self.accum_spp = 0
        self.is_rendering = False
        self.ray_batch_size = 2 
        self.current_image = None

        # --- ENVIRONMENT & SUN ---
        self.env_rotation = 0.0
        self.env_exposure = conf.environment.exposure
        self.env_background = conf.environment.background
        self.env_diffuse = conf.environment.diffuse
        self.env_specular = conf.environment.specular
        
        self.sun_id = -1
        self.sun_enabled = conf.environment.auto_sun
        self.sun_intensity = conf.environment.sun_intensity
        self.sun_radius = conf.environment.sun_radius
        self.sun_dist = conf.environment.sun_dist
        self.env_clipping_multiplier = conf.environment.clipping_multiplier if hasattr(conf.environment, 'clipping_multiplier') and conf.environment.clipping_multiplier is not None else 20.0
        self.env_clipping_enabled = True # Remplacé par True par défaut pour l'instant
        self.env_median_luminance = 0.0 

        # --- SYSTEM VARS (Runtime) ---
        self.epsilon = 0.001
        self.firefly_clamp = 100.0
        try:
            self.epsilon = cpp_engine.get_epsilon()
            self.firefly_clamp = cpp_engine.get_firefly_clamp()
        except:
            print("[Warning] Could not fetch system vars from engine (outdated binary?)")
        
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
        
        # Force Initial Sync of Environment Levels
        self.update_environment(builder.engine)

    # --- BUSINESS LOGIC ---

    def set_active_tab(self, tab_name):
        """Changes the tab and requests UI rebuild."""
        if self.active_tab != tab_name:
            self.active_tab = tab_name
            self.needs_ui_rebuild = True
            self.needs_repaint = True

    def toggle_accordion(self, tab, section_name):
        """Opens 'section_name' in 'tab' and closes others. If already open, closes it."""
        if self.accordions[tab] == section_name:
            self.accordions[tab] = None
        else:
            self.accordions[tab] = section_name
        self.needs_ui_rebuild = True
        self.needs_repaint = True

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
        self.conf.render.width = int(w)
        self.conf.render.height = int(h)
        self.target_aspect = self.conf.render.width / self.conf.render.height

        # On recalcule le rectangle d'affichage (Letterboxing)
        # Note: On a besoin de VIEW_W/H. Ils sont importés depuis ui_core.
        self.calculate_viewport(VIEW_W, VIEW_H)
        
        # On force la mise à jour caméra (pour le nouvel aspect ratio)
        self.needs_render_reset = True
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
        self.needs_render_reset = True
        self.needs_repaint = True

    def update_epsilon(self, val):
        try:
            val = float(val)
            self.epsilon = val
            cpp_engine.set_epsilon(val)
            self.needs_render_reset = True
            self.needs_repaint = True
            # Might need accumulation reset? Generally yes for geometry intersections issues
            if hasattr(self.builder.engine, 'reset_accumulation'): self.builder.engine.reset_accumulation()
        except Exception as e:
            print(f"Error setting epsilon: {e}")

    def update_firefly_clamp(self, val):
        try:
            val = float(val)
            self.firefly_clamp = val
            cpp_engine.set_firefly_clamp(val)
            self.needs_render_reset = True
            self.needs_repaint = True
            if hasattr(self.builder.engine, 'reset_accumulation'): self.builder.engine.reset_accumulation()
        except Exception as e:
            print(f"Error setting firefly clamp: {e}")

    def push_material_update(self, engine):
        d = self.get_selected_info()
        if not d: return
        ctype = d.get('mat_type', 'lambertian')
        ccol  = d.get('color', [0.8, 0.8, 0.8])
        
        # PBR Fields
        crough = d.get('roughness', 0.5)
        if 'fuzz' in d: crough = d['fuzz'] # Legacy mapping

        cmetal = d.get('metallic', 0.0)
        cir    = d.get('ir', 1.5)
        ctrans = d.get('transmission', 0.0)
        cdisp  = d.get('dispersion', 0.0)
        
        engine.update_instance_material(self.selected_id, ctype, cpp_engine.Vec3(*ccol), crough, cmetal, cir, ctrans, cdisp)
        self.needs_render_reset = True
        self.needs_repaint = True

    def load_new_env_map(self, engine):
        root = tk.Tk(); root.withdraw(); root.attributes('-topmost', True)
        file_path = filedialog.askopenfilename(title="Load Environment Map", filetypes=[("HDR/IMG", "*.hdr *.exr *.jpg *.png")], initialdir="./env-maps")
        root.destroy()
        if not file_path: return
        
        # Update Config for persistence
        self.conf.environment.source = file_path

        # Nettoyage ancien soleil
        if self.sun_id != -1:
            engine.remove_instance(self.sun_id)
            if self.sun_id in self.builder.registry: del self.builder.registry[self.sun_id]
            self.sun_id = -1
            self.sun_enabled = False

        # Chargement via Loader
        median = loader.load_environment(
            self.builder, self.conf.environment  # Pass the object!
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
        # Reset State
        self.selected_id = -1
        self.gizmo_mode = "MOVE"
        self.needs_render_reset = True
        self.needs_ui_rebuild = True
        self.needs_repaint = True
        self.accum_spp = 0
        if hasattr(engine, 'reset_accumulation'): engine.reset_accumulation()
        self.accum_spp = 0
        self.needs_render_reset = True
        self.needs_ui_rebuild = True # To refresh sun params if needed

    def update_environment(self, engine):
        # NEW: Direct Pass-Through (No Swapping)
        engine.set_env_rotation(self.env_rotation)
        engine.set_env_levels(self.env_exposure, self.env_background, self.env_diffuse, self.env_specular)
        
        # Direct Clipping Update (via Engine API)
        if hasattr(engine, 'get_env_clipping_threshold'): # Safety check
            thresh = float('inf')
            
            # Apply if explicitly enabled
            if self.env_clipping_enabled:
                 # If Sun is active OR we have an explicit multiplier (even 0)
                 if self.sun_enabled:
                      thresh = self.env_median_luminance * self.env_clipping_multiplier
            
            # Optimization: Set only if really changed to avoid costly rebuild_cdf
            current_thresh = engine.get_env_clipping_threshold()
            # If thresh is inf and current too, no change
            # If diff > epsilon, change
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
            
        self.needs_render_reset = True
        self.needs_repaint = True

    def duplicate_selection(self, engine):
        """Duplicates the selected object via the Builder."""
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
        
        # PBR Params
        col = data.get('color', [0.8, 0.8, 0.8])
        mat = data.get('mat_type', 'lambertian')
        rough = data.get('roughness', 0.5)
        metal = data.get('metallic', 0.0)
        trans = data.get('transmission', 0.0)
        ir = data.get('ir', 1.5)
        disp = data.get('dispersion', 0.0)
        if 'fuzz' in data: rough = data['fuzz']

        new_id = -1

        # 3. Appel au Builder (Logique miroir de loader.py)
        # Le builder va créer l'objet C++ ET remplir le registre pour nous.
        
        if otype == 'sphere':
            # add_sphere(center, radius, mat_type, color, roughness, metallic, ir, transmission)
            new_id = self.builder.add_sphere(pos, scale[0], mat, col, roughness=rough, metallic=metal, ir=ir, transmission=trans, dispersion=disp)

        elif otype == 'mesh':
            name = data.get('name', 'Unknown')
            new_id = self.builder.add_mesh_instance(name, pos, rot, scale)
            # Force properties
            self.builder.registry[new_id]['color'] = col
            self.builder.registry[new_id]['mat_type'] = mat
            self.builder.registry[new_id]['roughness'] = rough
            self.builder.registry[new_id]['metallic'] = metal
            self.builder.registry[new_id]['ir'] = ir
            self.builder.registry[new_id]['transmission'] = trans
            self.builder.registry[new_id]['dispersion'] = disp
            self.push_material_update(engine)
            
        elif otype == 'light_sun':
             raw = data.get('raw_color', col)
             new_id = self.builder.add_invisible_sphere_light(pos, scale[0], col, raw)

        elif otype == 'checker_sphere':
            c2 = data.get('color2', [0.0, 0.0, 0.0])
            tex_scale = data.get('texture_scale', 4.0)
            new_id = self.builder.add_checker_sphere(pos, scale[0], col, c2, tex_scale)

        elif otype == 'quad':
            u_vec = data.get('u', [1,0,0])
            v_vec = data.get('v', [0,1,0])
            new_id = self.builder.add_quad(pos, u_vec, v_vec, mat, col, roughness=rough, metallic=metal, ir=ir, transmission=trans, dispersion=disp)
             
        # 4. Finalisation UX
        if new_id != -1:
            # On ne change pas le nom pour l'instant car il sert à retrouver les meshes
            if 'name' in self.builder.registry[new_id]:
                pass

            # On sélectionne le nouvel objet et on active le mode MOVE
            self.selected_id = new_id
            self.gizmo_mode = "MOVE"
            
            # 5. Sélection du nouvel objet
            self.selected_id = new_id
            self.needs_render_reset = True
            self.needs_ui_rebuild = True # New selection -> UI Update
            self.needs_repaint = True
            print(f"[Editor] Duplicated object {self.selected_id} -> {new_id}")

    def load_mesh_dialog(self, engine):
        """Ouvre un dialogue pour charger un mesh .obj/.glb etc."""
        root = tk.Tk(); root.withdraw(); root.attributes('-topmost', True)
        init_dir = "./assets" if os.path.exists("./assets") else "."
        file_path = filedialog.askopenfilename(title="Load Mesh Asset", 
                                               filetypes=[("3D Models", "*.obj *.glb *.stl *.ply")], 
                                               initialdir=init_dir)
        root.destroy()
        if not file_path: return
        
        # 1. Chargement de l'asset via MeshLoader (via Builder)
        # On utilise le nom du fichier comme nom d'asset
        filename = os.path.basename(file_path)
        asset_name = os.path.splitext(filename)[0]
        
        info = self.builder.load_asset(asset_name, file_path)
        
        if info:
            # 2. Spawn devant la caméra
            fx = math.sin(self.yaw) * math.cos(self.pitch)
            fy = math.sin(self.pitch)
            fz = math.cos(self.yaw) * math.cos(self.pitch)
            fwd = np.array([fx, fy, fz])
            spawn_pos = self.cam_pos + (fwd * 5.0)
            
            # 3. Création de l'instance
            new_id = self.builder.add_mesh_instance(info.name, pos=spawn_pos.tolist())
            
            if new_id != -1:
                self.selected_id = new_id
                self.gizmo_mode = "MOVE"
                self.set_active_tab("OBJECT")
                self.gizmo_mode = "MOVE"
                self.set_active_tab("OBJECT")
                self.scene_dirty = True
                self.ui_dirty = True

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
            # Default PBR sphere: Matte Grey
            new_id = self.builder.add_sphere(spawn_pos_list, 1.0, "lambertian", [0.8, 0.8, 0.8], roughness=0.5)
            
        elif type_key == "cube":
             # Utilisation du helper meshloader pour créer le cube virtuel
             info = meshloader.create_cube(self.builder.engine, 2.0)
             if info: self.builder.asset_library["primitive_cube"] = info
             
             # Instance
             new_id = self.builder.add_mesh_instance("primitive_cube", pos=spawn_pos_list, registry_type="mesh_prim")
             # Force mat settings
             if new_id in self.builder.registry:
                 self.builder.registry[new_id]['mat_type'] = "lambertian"
                 self.builder.registry[new_id]['color'] = [0.8, 0.8, 0.8]
                 self.builder.registry[new_id]['roughness'] = 0.5
                 self.builder.registry[new_id]['metallic'] = 0.0
                 self.builder.registry[new_id]['ir'] = 0.0
                 self.builder.registry[new_id]['transmission'] = 0.0    
        
        elif type_key == "cylinder":
             new_id = self.builder.add_cylinder(spawn_pos_list, 1.0, 2.0, "lambertian", [0.8, 0.8, 0.8])
             
        elif type_key == "cone":
             new_id = self.builder.add_cone(spawn_pos_list, 1.0, 2.0, "lambertian", [0.8, 0.8, 0.8])

        elif type_key == "pyramid":
             info = meshloader.create_pyramid(self.builder.engine, 2.0, 2.0)
             if info: self.builder.asset_library["primitive_pyramid"] = info
             new_id = self.builder.add_mesh_instance("primitive_pyramid", pos=spawn_pos_list, registry_type="mesh_prim")

        elif type_key == "tetrahedron":
             info = meshloader.create_tetrahedron(self.builder.engine, 2.0)
             if info: self.builder.asset_library["primitive_tetrahedron"] = info
             new_id = self.builder.add_mesh_instance("primitive_tetrahedron", pos=spawn_pos_list, registry_type="mesh_prim")

        elif type_key == "icosahedron":
             info = meshloader.create_icosahedron(self.builder.engine, 2.0)
             if info: self.builder.asset_library["primitive_icosahedron"] = info
             new_id = self.builder.add_mesh_instance("primitive_icosahedron", pos=spawn_pos_list, registry_type="mesh_prim")

        elif type_key == "light_sphere":
            new_id = self.builder.add_invisible_sphere_light(spawn_pos_list, 1.0, [10,10,10], [10,10,10])
        
        elif type_key == "light_quad":
             # Ceiling Light : Quad au dessus, émissif
             center = [spawn_pos_list[0], spawn_pos_list[1] + 2.5, spawn_pos_list[2]]
             s = 2.0
             # Quad horizontal facing down (Normal -Y)
             # Start Corner Q
             Q = [center[0]-s, center[1], center[2]-s]
             u = [2*s, 0, 0]   # +X
             v = [0, 0, 2*s]   # +Z
             # Cross(u, v) -> Down (-Y) ? 
             # (2,0,0) x (0,0,2) = (0, -4, 0). YES.
             
             # High emission color
             new_id = self.builder.add_quad(Q, u, v, "light", [15.0, 15.0, 15.0])
            
        elif type_key == "quad_floor":
             # Un quad plat au sol (XZ), ABAISSÉ (-2.0)
             center = [spawn_pos_list[0], spawn_pos_list[1] - 2.0, spawn_pos_list[2]]
             y = center[1]
             s = 5.0 # taille
             Q = [center[0]-s, y, center[2]-s]
             u = [2*s, 0, 0]
             v = [0, 0, 2*s]
             new_id = self.builder.add_quad(Q, u, v, "lambertian", [0.5, 0.5, 0.5])

        elif type_key == "quad_wall":
             # Un quad vertical (XY), DÉCALÉ À DROITE (+X)
             # +X est à droite si on regarde -Z.
             right_vec = np.cross(fwd, np.array([0,1,0]))
             if np.linalg.norm(right_vec) > 0.01:
                 right_vec /= np.linalg.norm(right_vec)
             else:
                 right_vec = np.array([1,0,0])
                 
             offset_pos = spawn_pos + (right_vec * 3.0) 
             center = offset_pos.tolist()
             
             z = center[2]
             s = 5.0
             # Quad facing +Z (vers camera si on est en -Z)
             Q = [center[0]-s, center[1]-s, z]
             u = [2*s, 0, 0]
             v = [0, 2*s, 0]
             new_id = self.builder.add_quad(Q, u, v, "lambertian", [0.8, 0.2, 0.2])

        # 3. Sélection automatique
        if new_id != -1:
            self.selected_id = new_id
            self.gizmo_mode = "MOVE"
            self.set_active_tab("OBJECT") # On switch sur l'onglet objet pour l'éditer direct
            self.set_active_tab("OBJECT") # On switch sur l'onglet objet pour l'éditer direct
            self.scene_dirty = True
            self.ui_dirty = True
            
    # --- SAVE / LOAD SYSTEM ---

    def save_scene(self, filepath):
        """Sérialise la scène complète en JSON via le Serializer."""
        
        # 1. Sync State -> Config
        # Camera
        fx = math.sin(self.yaw) * math.cos(self.pitch)
        fy = math.sin(self.pitch)
        fz = math.cos(self.yaw) * math.cos(self.pitch)
        target = self.cam_pos + np.array([fx, fy, fz])
        
        self.conf.camera.lookfrom = self.cam_pos.tolist()
        self.conf.camera.lookat = target.tolist()
        self.conf.camera.vfov = self.vfov
        self.conf.camera.aperture = self.aperture
        self.conf.camera.focus_dist = self.focus_dist
        
        # Environment (State overrides Config)
        self.conf.environment.exposure = self.env_exposure
        self.conf.environment.background = self.env_background
        self.conf.environment.diffuse = self.env_diffuse
        self.conf.environment.specular = self.env_specular
        self.conf.environment.rotation = self.env_rotation
        
        self.conf.environment.auto_sun = self.sun_enabled
        self.conf.environment.sun_intensity = self.sun_intensity
        self.conf.environment.sun_radius = self.sun_radius
        self.conf.environment.sun_dist = self.sun_dist
        self.conf.environment.clipping_multiplier = self.env_clipping_multiplier

        # System
        self.conf.system.epsilon = self.epsilon
        self.conf.system.firefly_clamp = self.firefly_clamp

        # 2. Serialize
        try:
             serializer.serialize_scene(self.conf, self.builder, filepath)
        except Exception as e:
             print(f"[System] Save Failed: {e}")
    
    def load_scene(self, filepath):
        """Charge une scène JSON via Loader et sync le State."""
        if not os.path.exists(filepath): return

        print(f"[System] Loading scene: {filepath}...")

        # 1. NETTOYAGE (Clear Scene)
        ids_to_remove = list(self.builder.registry.keys())
        for oid in ids_to_remove:
            self.builder.engine.remove_instance(oid)
        self.builder.registry.clear()
        self.selected_id = -1
        self.sun_id = -1

        # 2. Utilisation du Loader standard (qui met à jour self.conf et builder)
        # Note: loader.load_scene_from_json ne gère pas le nettoyage instance C++ (fait au dessus)
        # Mais il peuple le registre et la config.
        try:
             # On réutilise le code de Loader
             import json
             with open(filepath, 'r') as f:
                  data = json.load(f)
        except Exception as e:
             print(f"Load failed: {e}")
             return

        # Mise à jour Config
        loader.load_scene_from_json(self.builder, filepath, self.conf)

        # 3. SYNC STATE FROM CONFIG
        
        # Caméra
        self.cam_pos = np.array(self.conf.camera.lookfrom, dtype=np.float32)
        target = np.array(self.conf.camera.lookat, dtype=np.float32)
        direction = target - self.cam_pos
        length = np.linalg.norm(direction)
        direction = direction / length if length > 0 else np.array([0, 0, -1])
        self.pitch = math.asin(np.clip(direction[1], -0.99, 0.99))
        self.yaw = math.atan2(direction[0], direction[2])
        self.vfov = self.conf.camera.vfov
        self.aperture = self.conf.camera.aperture
        self.focus_dist = self.conf.camera.focus_dist
        self.move_speed = max(1.0, length * 0.8)

        # Environment
        self.env_exposure = self.conf.environment.exposure
        self.env_background = self.conf.environment.background
        self.env_diffuse = self.conf.environment.diffuse
        self.env_specular = self.conf.environment.specular
        self.env_rotation = self.conf.environment.rotation
        self.sun_enabled = self.conf.environment.auto_sun
        self.sun_intensity = self.conf.environment.sun_intensity
        self.sun_radius = self.conf.environment.sun_radius
        self.sun_dist = self.conf.environment.sun_dist
        
        # Samplers (Special case: JSON might have 'render_sampler' which loader mapped to config.sampler)
        # But Editor has split render/preview samplers.
        # We try to read them from JSON specifically if possible, else default.
        if "render_settings" in data:
             rs = data["render_settings"]
             self.preview_sampler = rs.get("preview_sampler", 0)
             self.render_sampler = rs.get("render_sampler", self.conf.render.sampler)
        
        # System Vars
        self.update_epsilon(self.conf.system.epsilon)
        self.update_firefly_clamp(self.conf.system.firefly_clamp)

        # Enforce Env Update
        self.update_environment(self.builder.engine)
        
        # Update Viewport
        self.target_aspect = self.conf.render.width / self.conf.render.height if self.conf.render.height > 0 else 1.33

        self.scene_dirty = True
        self.ui_dirty = True

        
        # Récup ID Soleil
        for oid, info in self.builder.registry.items():
            if info['type'] == 'light_sun':
                self.sun_id = oid
                p = np.array(info['pos'])
                d = np.linalg.norm(p)
                if d > 0: self.sun_initial_dir = p/d
                break

        # Force Sync after load
        self.update_environment(self.builder.engine)

        # 5. RESTAURATION OBJETS (inchangé)
        cwd = os.getcwd()
        for obj in data["objects"]:
            otype = obj["type"]
            pos = obj["pos"]
            rot = obj.get("rot", [0,0,0])
            scale = obj["scale"]
            mat = obj.get("mat_type", "lambertian")
            col = obj.get("color", [0.8, 0.8, 0.8])
            name = obj.get("name") # FIX: Define name variable
            
            # PBR Load
            fuzz = obj.get("fuzz", 0.0)
            rough = obj.get("roughness", fuzz)
            metal = obj.get("metallic", 0.0)
            ir = obj.get("ir", 1.5)
            trans = obj.get("transmission", 0.0)
            disp = obj.get("dispersion", 0.0)

            new_id = -1
            if otype == "sphere":
                new_id = self.builder.add_sphere(pos, scale[0], mat, col, roughness=rough, metallic=metal, ir=ir, transmission=trans, dispersion=disp)
            elif otype == "cylinder":
                # scale[0]=radius, scale[1]=height
                new_id = self.builder.add_cylinder(pos, scale[0], scale[1], mat, col, roughness=rough, metallic=metal, ir=ir, transmission=trans, dispersion=disp)
            elif otype == "cone":
                new_id = self.builder.add_cone(pos, scale[0], scale[1], mat, col, roughness=rough, metallic=metal, ir=ir, transmission=trans, dispersion=disp)
            elif otype == "mesh_prim":
                asset_name = obj.get("asset_name")
                
                # REGENERATION DES PRIMITIVES VIRTUELLES
                if asset_name and asset_name not in self.builder.asset_library:
                    print(f"[Loader] Regenerating virtual primitive: {asset_name}")
                    info = None
                    if asset_name == "primitive_cube":
                        info = meshloader.create_cube(self.builder.engine, 2.0)
                    elif asset_name == "primitive_pyramid":
                         info = meshloader.create_pyramid(self.builder.engine, 2.0, 2.0)
                    elif asset_name == "primitive_tetrahedron":
                         info = meshloader.create_tetrahedron(self.builder.engine, 2.0)
                    elif asset_name == "primitive_icosahedron":
                         info = meshloader.create_icosahedron(self.builder.engine, 2.0)
                    
                    if info:
                        self.builder.asset_library[asset_name] = info

                new_id = self.builder.add_mesh_instance(asset_name, pos, rot, scale, registry_type="mesh_prim")
                
                # FORCE props
                if new_id != -1:
                    self.builder.registry[new_id]['color'] = col
                    self.builder.registry[new_id]['mat_type'] = mat
                    self.builder.registry[new_id]['roughness'] = rough
                    self.builder.registry[new_id]['metallic'] = metal
                    self.builder.registry[new_id]['ir'] = ir
                    self.builder.registry[new_id]['transmission'] = trans
                    self.builder.registry[new_id]['dispersion'] = disp
                    self.push_material_update(self.builder.engine)
            
            elif otype == "mesh":
                asset_name = obj.get("asset_name")
                # Standard OBJ loading (implicit via asset_name)
                # If asset_name is a path, engine handles it or we should load it?
                # For now assume asset is already loaded or engine lazy loads?
                # Wait, if we restart app, engine.asset_map is empty.
                # add_mesh_instance calls engine.add_instance(mesh_name).
                # If mesh_name is not in engine, it crashes or fails?
                # We need to Ensure asset is loaded or mesh_load it!
                # Since we don't store "filepath" separately (it IS asset_name?), we rely on previous import logic?
                # Ah, import uses asset_name = filepath.
                # So if asset_name exists on disk, we should load it if not present?
                
                # Verify if loaded
                # Actually, standard mesh loader workflow:
                # 1. drag drop -> calls meshloader.load_mesh -> registers in asset_library
                # So upon Reload, we must check if asset_name is in registry.
                # If not, try to load it from disk (asset_name is likely absolute or relative path).
                
                if asset_name and asset_name not in self.builder.asset_library:
                    # Attempt reload from disk
                    if os.path.exists(asset_name):
                         print(f"[Loader] Reloading external mesh: {asset_name}")
                         # Use meshloader basic load
                         # Note: mat override logic in meshloader?
                         info = meshloader.load_mesh(self.builder.engine, asset_name)
                         if info: self.builder.asset_library[asset_name] = info
                
                new_id = self.builder.add_mesh_instance(asset_name, pos, rot, scale, registry_type="mesh")
                
                if new_id != -1:
                    self.builder.registry[new_id]['color'] = col
                    self.builder.registry[new_id]['mat_type'] = mat
                    self.builder.registry[new_id]['roughness'] = rough
                    self.builder.registry[new_id]['metallic'] = metal
                    self.builder.registry[new_id]['ir'] = ir
                    self.builder.registry[new_id]['transmission'] = trans
                    self.builder.registry[new_id]['dispersion'] = disp
                    self.push_material_update(self.builder.engine)
                
            elif otype == "checker_sphere":
                c2 = obj.get("color2", [0,0,0])
                tscale = obj.get("texture_scale", 10.0)
                new_id = self.builder.add_checker_sphere(pos, scale[0], col, c2, tscale)
            elif otype == "quad":
                u = obj.get("u", [1,0,0])
                v = obj.get("v", [0,1,0])
            elif otype == "quad":
                u = obj.get("u", [1,0,0])
                v = obj.get("v", [0,1,0])
                new_id = self.builder.add_quad(pos, u, v, mat, col, roughness=rough, metallic=metal, ir=ir, transmission=trans, dispersion=disp)


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

    # =================================================================================================
    # COMPATIBILITY PROPERTIES
    # =================================================================================================
    @property
    def scene_dirty(self):
        return self.needs_render_reset

    @scene_dirty.setter
    def scene_dirty(self, value):
        if value:
            self.needs_render_reset = True
            self.needs_repaint = True

    @property
    def ui_dirty(self):
        return self.needs_ui_rebuild

    @ui_dirty.setter
    def ui_dirty(self, value):
        if value:
            self.needs_ui_rebuild = True
            self.needs_repaint = True

    @property
    def dirty(self):
        return self.scene_dirty

    @dirty.setter
    def dirty(self, value):
        self.scene_dirty = value