import trimesh
import numpy as np
import os
import cpp_engine
from dataclasses import dataclass, field

# ==================================================================================
# 1. Structure de données pour les métadonnées
# ==================================================================================

@dataclass
class MeshInfo:
    """Contient les métadonnées géométriques d'un objet chargé."""
    name: str
    
    # Global Bounds (numpy arrays [x, y, z])
    min_coords: np.ndarray
    max_coords: np.ndarray
    size: np.ndarray    # [width, height, depth]
    center: np.ndarray  # Le centre géométrique

    # Infos Matériau par défaut de l'asset
    mat_type: str = "lambertian"
    color: list = field(default_factory=lambda: [0.8, 0.8, 0.8])
    fuzz: float = 0.0
    ior: float = 1.5
    
    # Helpers pratiques (distances depuis le pivot 0,0,0)
    @property
    def height(self): return self.size[1]
    
    @property
    def bottom_y(self): return self.min_coords[1] # Position des pieds par rapport au pivot
    
    def __repr__(self):
        return (f"<MeshInfo '{self.name}': {self.mat_type} | W={self.size[0]:.2f}, H={self.size[1]:.2f}, D={self.size[2]:.2f} | "
                f"Bottom Y={self.bottom_y:.3f}>")

# ==================================================================================
# 2. Fonctions de Chargement
# ==================================================================================

def load_mesh_to_engine(engine, file_path, scale=1.0, translation=[0,0,0], auto_center=False,
                        override_mat=None, override_color=None, override_ior=None):
    """
    Charge un fichier 3D et l'ajoute directement à la scène (HittableList).
    Retourne un objet MeshInfo.
    """
    if not os.path.exists(file_path):
        print(f"[Error] Mesh file not found: {file_path}")
        return None

    print(f"[Loader] Processing mesh: {file_path}...")
    
    try:
        scene_or_mesh = trimesh.load(file_path, force=None)
    except Exception as e:
        print(f"[Error] Failed to load mesh: {e}")
        return None

    geometries = []
    if isinstance(scene_or_mesh, trimesh.Scene):
        geometries = list(scene_or_mesh.geometry.values())
    else:
        geometries = [scene_or_mesh]

    # --- Pré-calcul pour auto-centrage global ---
    all_verts_raw = []
    for g in geometries: 
        all_verts_raw.append(g.vertices)
    
    center_mass = np.array([0,0,0])
    if auto_center and all_verts_raw:
        combined = np.vstack(all_verts_raw)
        center_mass = combined.mean(axis=0)

    # Liste pour stocker tous les vertices finaux (pour MeshInfo)
    all_final_verts = [] 

    print(f"[Loader] Found {len(geometries)} sub-meshes.")

    for geom in geometries:
        # --- A. Conversion Matériau (.mtl -> PBR) ---
        mat_type = "lambertian"
        color = [0.8, 0.8, 0.8]
        fuzz = 0.0
        ior = 1.5
        
        if hasattr(geom.visual, 'material'):
            mat = geom.visual.material
            if hasattr(mat, 'diffuse'):
                rgba = mat.diffuse
                if rgba.dtype == np.uint8: color = rgba[:3] / 255.0
                else: color = rgba[:3]

            opacity = getattr(mat, 'opacity', 1.0)
            if len(getattr(mat, 'diffuse', [])) == 4:
                alpha = mat.diffuse[3] / 255.0 if mat.diffuse.dtype == np.uint8 else mat.diffuse[3]
                if alpha < opacity: opacity = alpha

            if opacity < 0.99:
                mat_type = "dielectric"
                ior = getattr(mat, 'refraction_index', 1.5)
                if np.mean(color) < 0.1: color = [0.9, 0.9, 0.9]

            elif hasattr(mat, 'specular'):
                spec = mat.specular
                if spec.dtype == np.uint8: spec = spec / 255.0
                if np.mean(spec[:3]) > 0.2:
                    mat_type = "metal"
                    shininess = getattr(mat, 'shininess', 50.0)
                    fuzz = max(0.0, min(1.0, 1.0 - (shininess / 1000.0)))

        # --- Overrides ---
        if override_mat is not None: mat_type = override_mat
        if override_color is not None: color = override_color
        if override_ior is not None: ior = override_ior

        # --- B. Nettoyage Géométrie ---
        geom.fix_normals()
        verts = geom.vertices.copy()
        
        if auto_center:
            verts -= center_mass
        
        verts *= scale
        
        # On sauvegarde les vertices transformés (avant translation finale) pour le MeshInfo local
        # (Si on veut le MeshInfo global world-space, il faudrait ajouter la translation)
        # Ici on garde la logique "taille de l'objet"
        all_final_verts.append(verts.copy()) 

        verts += np.array(translation)
        
        norms = geom.vertex_normals.copy()
        
        c_verts = np.ascontiguousarray(verts, dtype=np.float32)
        c_norms = np.ascontiguousarray(norms, dtype=np.float32)
        c_faces = np.ascontiguousarray(geom.faces, dtype=np.int32)

        if isinstance(color, np.ndarray): color = color.tolist()
        vec_color = cpp_engine.Vec3(float(color[0]), float(color[1]), float(color[2]))

        engine.add_mesh(c_verts, c_faces, c_norms, mat_type, vec_color, float(fuzz), float(ior))       
        
    # --- C. Construction et Retour de MeshInfo ---
    if all_final_verts:
        total_verts = np.vstack(all_final_verts)
        min_v = total_verts.min(axis=0)
        max_v = total_verts.max(axis=0)
        
        info = MeshInfo(
            name=os.path.basename(file_path),
            min_coords=min_v,
            max_coords=max_v,
            size=max_v - min_v,
            center=(min_v + max_v) / 2.0
        )
        print(f"[Loader] {info}")
        return info
    
    return None


def load_asset(engine, asset_name, file_path, override_mat=None, override_color=None, override_ior=None):
    """
    Charge un asset en mémoire (Engine.mesh_assets) SANS l'afficher.
    Applique une logique "Pieds à Zéro" : Le point (0,0,0) local sera aux pieds de l'objet.
    Retourne un objet MeshInfo.
    """
    if not os.path.exists(file_path):
        print(f"[Error] Mesh file not found: {file_path}")
        return None

    print(f"[Loader] Loading Asset '{asset_name}' from: {file_path}...")
    try:
        scene_or_mesh = trimesh.load(file_path, force=None)
    except Exception as e:
        print(f"[Error] Failed to load mesh: {e}")
        return None

    geometries = []
    if isinstance(scene_or_mesh, trimesh.Scene):
        geometries = list(scene_or_mesh.geometry.values())
    else:
        geometries = [scene_or_mesh]

    # --- CALCUL DU PIVOT INTELLIGENT (PIEDS À ZÉRO) ---
    all_verts_raw = []
    for g in geometries: all_verts_raw.append(g.vertices)
    
    center_mass = np.array([0,0,0])
    all_final_verts = [] # Pour MeshInfo

    if all_verts_raw:
        combined = np.vstack(all_verts_raw)
        min_y = combined[:, 1].min()
        mean_x = combined[:, 0].mean()
        mean_z = combined[:, 2].mean()
        center_mass = np.array([mean_x, min_y, mean_z])

    for geom in geometries:
        # 1. Matériaux (Simplifié)
        mat_type = "lambertian"
        color = [0.8, 0.8, 0.8]
        fuzz = 0.0
        ior = 1.5

        if hasattr(geom.visual, 'material'):
            mat = geom.visual.material
            if hasattr(mat, 'diffuse'):
                rgba = mat.diffuse
                if rgba.dtype == np.uint8: color = rgba[:3] / 255.0
                else: color = rgba[:3]
        
        # --- APPLICATION DES OVERRIDES ---
        if override_mat: mat_type = override_mat
        if override_color: color = override_color
        if override_ior is not None: ior = override_ior # <--- LIGNE AJOUTÉE

        # 2. Géométrie
        _ = geom.vertex_normals 
        
        verts = geom.vertices.copy()
        verts -= center_mass 
        
        all_final_verts.append(verts.copy())
        
        norms = geom.vertex_normals.copy()
        
        c_verts = np.ascontiguousarray(verts, dtype=np.float32)
        c_norms = np.ascontiguousarray(norms, dtype=np.float32)
        c_faces = np.ascontiguousarray(geom.faces, dtype=np.int32)
        
        if isinstance(color, np.ndarray): color = color.tolist()
        vec_color = cpp_engine.Vec3(float(color[0]), float(color[1]), float(color[2]))

        # Enregistrement des infos matériau
        last_mat_type = mat_type
        last_color = color
        last_fuzz = float(fuzz)
        last_ior = float(ior)

        # Envoi à l'engine (Asset)
        engine.load_mesh_asset(asset_name, c_verts, c_faces, c_norms, 
                               mat_type, vec_color, float(fuzz), float(ior))

    # --- C. Construction et Retour de MeshInfo ---
    if all_final_verts:
        total_verts = np.vstack(all_final_verts)
        min_v = total_verts.min(axis=0)
        max_v = total_verts.max(axis=0)
        
        info = MeshInfo(
            name=asset_name,
            min_coords=min_v,
            max_coords=max_v,
            size=max_v - min_v,
            center=(min_v + max_v) / 2.0,
            mat_type=last_mat_type,
            color=last_color,
            fuzz=last_fuzz,
            ior=last_ior
        )
        print(f"[Loader] Asset Ready: {info}")
        return info

    return None

def print_bounds(name, verts):
    """(Optionnel) Affiche les dimensions brutes pour debug rapide."""
    min_v = verts.min(axis=0)
    max_v = verts.max(axis=0)
    width = max_v[0] - min_v[0]
    height = max_v[1] - min_v[1]
    depth = max_v[2] - min_v[2]

    print(f"--- 📏 BOUNDARIES : '{name}' ---")
    print(f"  • Size: {width:.3f} x {height:.3f} x {depth:.3f}")
    print("-----------------------------------")