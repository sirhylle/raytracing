"""
================================================================================================
MODULE: MESH LOADER
================================================================================================

DESCRIPTION:
  Handles loading of external 3D geometry (OBJ, STL, PLY, GLB) using the 'trimesh' library.
  It performs essential preprocessing:
  1. Geometry Cleaning (Fixing normals, duplicates).
  2. Material Conversion (Mapping external materials to our native Lambertian/Metal/Dielectric).
  3. Pivot Adjustment (centering or placing at feet).
  
  Interacts directly with the C++ Engine to upload vertex/face data.

================================================================================================
"""
import trimesh
import numpy as np
import math
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
    mat_type: str = "standard"
    color: list = field(default_factory=lambda: [0.8, 0.8, 0.8])
    roughness: float = 0.5
    metallic: float = 0.0
    ior: float = 1.5
    transmission: float = 0.0
    
    # Helpers pratiques (distances depuis le pivot 0,0,0)
    @property
    def height(self): return self.size[1]
    
    @property
    def bottom_y(self): return self.min_coords[1] # Position des pieds par rapport au pivot
    
    def __repr__(self):
        return (f"<MeshInfo '{self.name}': {self.mat_type} | W={self.size[0]:.2f}, H={self.size[1]:.2f}, D={self.size[2]:.2f} | "
                f"Bottom Y={self.bottom_y:.3f}>")

def load_asset(engine, asset_name, file_path, 
               override_mat=None, override_color=None, 
               override_roughness=None, override_metallic=None, 
               override_ior=None, override_transmission=None):
    """
    Loads a mesh into the Engine's Asset Library (memory) WITHOUT adding it to the scene graph.
    Supports PBR overrides.
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

    return process_trimesh_objects(engine, asset_name, scene_or_mesh, 
                                   override_mat, override_color, 
                                   override_roughness, override_metallic, 
                                   override_ior, override_transmission)

def create_cube(engine, size=2.0):
    """
    Creates a virtual cube asset using Trimesh box but unmerged for flat shading.
    """
    asset_name = "primitive_cube"
    mesh = trimesh.creation.box(extents=[size, size, size])
    
    # Critical for flat shading: Unmerge vertices so each face has unique vertices/normals
    mesh.unmerge_vertices()    
    return process_trimesh_objects(engine, asset_name, mesh)

def create_pyramid(engine, size=2.0, height=2.0):
    """Creates a Square Base Pyramid."""
    asset_name = "primitive_pyramid"
    s = size / 2.0
    h = height / 2.0 # Centered around Y=0 ?
    # Let's pivot at base=0 ? No, standard centered.
    # Base at -h/2, Tip at +h/2
    y_base = -h
    y_tip = h
    
    # Faces: Base(Square) + 4 Triangles
    # Base: 4 verts
    # Sides: 4 * 3 verts = 12 verts
    # Total 16 verts
    
    v_base = [
        [-s, y_base, s], [s, y_base, s], [s, y_base, -s], [-s, y_base, -s]
    ]
    # Tip
    tip = [0, y_tip, 0]
    
    vertices = []
    normals = [] # We'll compute them or let trimesh compute per-face? 
    # For simplicity, if we provide vertices/faces without normals but 'process=False',
    # trimesh might not have normals. We should provide them or compute them.
    # Better: generate Verts/Faces, make Trimesh(process=False), then mesh.fix_normals()? 
    # mesh.fix_normals() might merge vertices.
    # Best: List vertices per face, then compute cross product.
    
    # --- 1. Base (Facing Down) ---
    vertices.extend([v_base[3], v_base[2], v_base[1], v_base[0]]) # CCW looking from bottom?
    # Normal (0, -1, 0)
    for _ in range(4): normals.append([0, -1, 0])
    
    # --- 2. Front Face (+Z) ---
    # v0, v1, tip
    vertices.extend([v_base[0], v_base[1], tip])
    # Normal: Cross((v1-v0), (tip-v0))
    n = np.cross(np.array(v_base[1])-np.array(v_base[0]), np.array(tip)-np.array(v_base[0]))
    n = n / np.linalg.norm(n)
    for _ in range(3): normals.append(n.tolist())

    # --- 3. Right Face (+X) ---
    # v1, v2, tip
    vertices.extend([v_base[1], v_base[2], tip])
    n = np.cross(np.array(v_base[2])-np.array(v_base[1]), np.array(tip)-np.array(v_base[1]))
    n = n / np.linalg.norm(n)
    for _ in range(3): normals.append(n.tolist())
    
    # --- 4. Back Face (-Z) ---
    # v2, v3, tip
    vertices.extend([v_base[2], v_base[3], tip])
    n = np.cross(np.array(v_base[3])-np.array(v_base[2]), np.array(tip)-np.array(v_base[2]))
    n = n / np.linalg.norm(n)
    for _ in range(3): normals.append(n.tolist())
    
    # --- 5. Left Face (-X) ---
    # v3, v0, tip
    vertices.extend([v_base[3], v_base[0], tip])
    n = np.cross(np.array(v_base[0])-np.array(v_base[3]), np.array(tip)-np.array(v_base[3]))
    n = n / np.linalg.norm(n)
    for _ in range(3): normals.append(n.tolist())
    
    # Faces indices
    faces = []
    # Base (Quad -> 2 tris)
    faces.append([0, 1, 2]); faces.append([0, 2, 3])
    # Sides (Triangles)
    base_idx = 4
    for i in range(4):
        faces.append([base_idx, base_idx+1, base_idx+2])
        base_idx += 3
        
    mesh = trimesh.Trimesh(vertices=vertices, faces=faces, vertex_normals=normals, process=False)
    return process_trimesh_objects(engine, asset_name, mesh)

def create_tetrahedron(engine, size=2.0):
    """
    Creates a regular tetrahedron with one face on the ground (XZ plane).
    Center of mass is at (0, y_center, 0).
    """
    asset_name = "primitive_tetrahedron"
    
    # Geometric properties of a regular tetrahedron with edge length 'a'
    # We want it to fit in 'size' approx.
    # Radius of circumsphere R = size/2.
    # Edge length a = 4*R/sqrt(6)
    
    R = size / 2.0
    a = 4 * R / np.sqrt(6)
    
    # Height of tetrahedron H = sqrt(6)/3 * a
    # H = sqrt(6)/3 * (4*R/sqrt(6)) = 4/3 * R
    # That makes sense.
    
    # Coordinates where base is on XZ plane y=0?
    # Or center of mass at origin? 
    # Let's put center of mass at (0,0,0) so it spins nicely.
    # Distance from center to base face = H/4 = R/3 ?
    # Distance from center to peak = 3*H/4 = R ?
    
    # Peak at (0, R, 0)
    # Base triangle at y = -H/4 = -R * (1/3) ? No.
    # Center to Vertex distance is R.
    # Center to Face distance is r = R/3.
    # So if Peak is at (0, R, 0), Base is at y = -R/3.
    
    y_tip = R
    y_base = -R / 3.0
    
    # Base vertices on circle of radius r_base?
    # Side length a. Distance from centroid of base to base vertices is a/sqrt(3).
    # a/sqrt(3) = (4*R/sqrt(6)) / sqrt(3) = 4*R / sqrt(18) = 4*R / (3*sqrt(2)) = 2*sqrt(2)/3 * R
    
    r_base = (2.0 * np.sqrt(2.0) / 3.0) * R
    
    # Angles: 0, 120, 240
    import math
    
    # Vertex 0 (Tip)
    v0 = [0, y_tip, 0]
    
    # Vertex 1,2,3 (Base)
    angles = [0, 2*math.pi/3, 4*math.pi/3]
    v_base = []
    for ang in angles:
        # Note: -y_base because it's below origin
        v_base.append([r_base * math.sin(ang), y_base, r_base * math.cos(ang)])
        
    v1, v2, v3 = v_base[0], v_base[1], v_base[2]
    
    # Faces (Triangle orientation OUTWARD)
    # Base is v1-v3-v2 (looking from bottom up is CW, so down is CCW?)
    # Normal should be (0,-1,0).
    # Cross(v3-v1, v2-v1) ?
    
    raw_faces_verts = [
        [v1, v3, v2], # Base (facing down)
        [v0, v1, v2], # Side 1
        [v0, v2, v3], # Side 2
        [v0, v3, v1], # Side 3
    ]
    
    # Build mesh manually to be sure
    vertices = []
    normals = []
    
    for f_verts in raw_faces_verts:
        p0, p1, p2 = np.array(f_verts[0]), np.array(f_verts[1]), np.array(f_verts[2])
        n = np.cross(p1-p0, p2-p0)
        norm = np.linalg.norm(n)
        if norm > 0: n /= norm
        
        vertices.extend(f_verts)
        normals.extend([n.tolist()]*3)
        
    faces = []
    for i in range(4):
        base = i*3
        faces.append([base, base+1, base+2])

    mesh = trimesh.Trimesh(vertices=vertices, faces=faces, vertex_normals=normals, process=False)
    return process_trimesh_objects(engine, asset_name, mesh)



def create_icosahedron(engine, size=2.0):
    asset_name = "primitive_icosahedron"
    mesh = trimesh.creation.icosahedron() # Radius=1 default
    mesh.apply_scale(size/2.0)
    mesh.unmerge_vertices()
    return process_trimesh_objects(engine, asset_name, mesh)

def process_trimesh_objects(engine, asset_name, scene_or_mesh,
                            override_mat=None, override_color=None, 
                            override_roughness=None, override_metallic=None, 
                            override_ior=None, override_transmission=None):
    """
    Internal helper to process a trimesh Scene or Trimesh object and upload to Engine.
    """
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

    # Default logic PBR (Found in loop)

    for geom in geometries:
        # 1. Extraction des propriétés du fichier (Source of Truth)
        # Valeurs par défaut "safe"
        mat_type = "standard"
        color = [0.8, 0.8, 0.8]
        roughness = 0.5
        metallic = 0.0
        ior = 1.5
        transmission = 0.0
        
        if hasattr(geom, 'visual') and hasattr(geom.visual, 'material'):
            mat = geom.visual.material
            if hasattr(mat, 'name') and mat.name:
                print(f"[Loader]   -> Found Material: '{mat.name}'")
            
            # --- A. Couleur / Albedo ---
            if hasattr(mat, 'diffuse'):
                # trimesh peut renvoyer un color object ou un numpy array
                diff = mat.diffuse
                if isinstance(diff, np.ndarray):
                    if diff.dtype == np.uint8: color = (diff[:3] / 255.0).tolist()
                    else: color = diff[:3].tolist()
                elif isinstance(diff, (list, tuple)) and len(diff) >= 3:
                     # Parfois c'est [r,g,b,a]
                     color = list(diff)[:3]
            # Fallback PBR GLTF
            elif hasattr(mat, 'baseColorFactor'):
                 c = mat.baseColorFactor
                 if len(c) >= 3: color = list(c)[:3]

            # --- B. Roughness ---
            # 1. PBR Direct
            if hasattr(mat, 'roughnessFactor'):
                roughness = float(mat.roughnessFactor)
            # 2. Legacy OBJ (Ns / Shininess)
            elif hasattr(mat, 'shininess'):
                # Mapping empirique: Roughness = sqrt(2 / (Ns + 2))
                # Ns va souvent de 0 à 1000
                ns = float(mat.shininess)
                if ns <= 0.001:
                    roughness = 1.0 # Fully Matte
                else:
                    roughness = math.sqrt(2.0 / (ns + 2.0))
            
            # --- C. Metallic ---
            if hasattr(mat, 'metallicFactor'):
                metallic = float(mat.metallicFactor)
            elif hasattr(mat, 'specular'):
                # Heuristique faible: si specular est très brillant -> metallic ?
                # Pour l'instant, OBJ est souvent diélectrique.
                pass

            # --- D. Transmission / Opacity ---
            # Trimesh 'transparency' est souvent bizarre (d ou Tr).
            # On regarde 'opacity' si dispo (1=opaque, 0=transparent)
            opacity = 1.0
            if hasattr(mat, 'opacity'): # Common in trimesh processed mats
                opacity = float(mat.opacity)
            elif hasattr(mat, 'transparency'):
                # Parfois transparency = 1 - opacity, parfois c'est l'inverse...
                # Trimesh semble normaliser 'transparency' comme alpha si c'est chargé depuis 'd'.
                pass
            
            if opacity < 0.99:
                transmission = 1.0 - opacity
                
            # --- E. IOR ---
            if hasattr(mat, 'ior'): # PBR extension
                ior_val = float(mat.ior)
                if ior_val > 0: ior = ior_val
            # OBJ n'a pas toujours Ni accessible facilement via visual.material standard de trimesh
            # Sauf si PBRMaterial.

        # --- APPLICATION DES OVERRIDES (Priorité Utilisateur) ---
        # Seulement si l'argument est NON-NONE
        if override_mat is not None: mat_type = override_mat
        if override_color is not None: color = override_color
        if override_roughness is not None: roughness = override_roughness
        if override_metallic is not None: metallic = override_metallic
        if override_ior is not None: ior = override_ior
        if override_transmission is not None: transmission = override_transmission

        # 2. Géométrie
        _ = geom.vertex_normals 
        
        verts = geom.vertices.copy()
        verts -= center_mass 
        
        all_final_verts.append(verts.copy())
        
        norms = geom.vertex_normals.copy()
        
        c_verts = np.ascontiguousarray(verts, dtype=np.float32)
        c_norms = np.ascontiguousarray(norms, dtype=np.float32)
        c_faces = np.ascontiguousarray(geom.faces, dtype=np.int32)
        
        # Color safety check
        if isinstance(color, np.ndarray): color = color.tolist()
        if len(color) < 3: color = [0.8, 0.8, 0.8]
        
        vec_color = cpp_engine.Vec3(float(color[0]), float(color[1]), float(color[2]))

        # Enregistrement des infos matériau (pour le MeshInfo final - prend le dernier)
        last_mat_type = mat_type
        last_color = color
        last_rough = float(roughness)
        last_metal = float(metallic)
        last_ior = float(ior)
        last_trans = float(transmission)

        # Envoi à l'engine (Asset)
        engine.load_mesh_asset(asset_name, c_verts, c_faces, c_norms, 
                               mat_type, vec_color, 
                               float(roughness), float(metallic), float(ior), float(transmission))

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
            roughness=last_rough,
            metallic=last_metal,
            ior=last_ior,
            transmission=last_trans
        )
        print(f"[Loader] Asset Ready: {info}")
        return info

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