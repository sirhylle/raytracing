import cpp_engine
import numpy as np
import random
from dataclasses import dataclass
from typing import Optional, List, Tuple
import meshloader
import transforms as tf
import math

random.seed(60)

@dataclass
class SceneConfig:
    """Preferred configuration returned by a scene."""
    lookfrom: Optional[List[float]] = None
    lookat: Optional[List[float]] = None
    vup: Optional[List[float]] = None
    vfov: Optional[float] = None
    aperture: Optional[float] = None
    focus_dist: Optional[float] = None
    env_map: Optional[str] = None
    # Lighting
    env_light_level: float = 1.0     # Sky lighting intensity (as direct lighting)
    env_direct_level: float = 0.5    # Sky brightness (when viewed directly)
    env_indirect_level: float = 0.5    # Sky brightness (when viewed indirectly)

class Scene:
    def setup(self, builder, config_overrides: dict = None) -> SceneConfig:
        raise NotImplementedError

class CornellBox(Scene):
    def setup(self, builder, config_overrides: dict = None) -> SceneConfig:
        def v3(l):
            return cpp_engine.Vec3(float(l[0]), float(l[1]), float(l[2]))

        green = [0.12, 0.45, 0.15]
        red   = [0.65, 0.05, 0.05]
        white = [0.73, 0.73, 0.73]
        light_color = [15.0, 15.0, 15.0]
        # Left Green
        builder.add_quad(v3([555,0,0]), v3([0,555,0]), v3([0,0,555]), "lambertian", green, 0.0, 1.5)
        # Right Red
        builder.add_quad(v3([0,0,0]), v3([0,555,0]), v3([0,0,555]), "lambertian", red, 0.0, 1.5)
        # Top Light
        builder.add_quad(v3([343, 554, 332]), v3([-130,0,0]), v3([0,0,-105]), "light", light_color, 0.0, 1.5)
        # Floor
        builder.add_quad(v3([0,0,0]), v3([555,0,0]), v3([0,0,555]), "lambertian", white, 0.0, 1.5)
        # Ceiling
        builder.add_quad(v3([555,555,555]), v3([-555,0,0]), v3([0,0,-555]), "lambertian", white, 0.0, 1.5)
        # Back
        builder.add_quad(v3([0,0,555]), v3([555,0,0]), v3([0,555,0]), "lambertian", white, 0.0, 1.5)
        
        # Objects
        builder.add_sphere(v3([200, 100, 200]), 100.0, "metal", [0.8, 0.85, 0.88], 0.0, 1.5)
        builder.add_sphere(v3([400, 100, 300]), 100.0, "dielectric", [1.0, 1.0, 1.0], 0.0, 1.5)

        return SceneConfig(
            lookfrom=[278, 278, -800],
            lookat=[278, 278, 0],
            vup=[0, 1, 0],
            vfov=40.0,
            aperture=0.0,
            focus_dist=10.0,
            env_map="env-dock-sun.hdr",
            env_light_level=5.0,
            env_direct_level=0.5,
            env_indirect_level=0.5
        )

class RandomSpheres(Scene):
    def setup(self, builder, config_overrides: dict = None) -> SceneConfig:
        def v3(x, y, z): return cpp_engine.Vec3(float(x), float(y), float(z))

        builder.add_checker_sphere(v3(0, -1000, 0), 1000.0, 
                                  [0.2, 0.3, 0.1], 
                                  [0.9, 0.9, 0.9], 
                                  10.0)

        # Random small spheres
        for a in range(-11, 11):
            for b in range(-11, 11):
                choose_mat = random.random()
                center_x = a + 0.9 * random.random()
                center_z = b + 0.9 * random.random()
                center = v3(center_x, 0.2, center_z)

                if (np.linalg.norm([center_x - 4, center_z - 0]) > 0.9):
                    if choose_mat < 0.6:
                        # Diffuse or Plastic
                        albedo = [random.random() * random.random(), random.random() * random.random(), random.random() * random.random()]
                        if random.random() < 0.5:
                            builder.add_sphere(center, 0.2, "lambertian", albedo, 0.0, 1.5)
                        else:
                            builder.add_sphere(center, 0.2, "plastic", albedo, 0.0, 1.5)
                    elif choose_mat < 0.85:
                        # Metal
                        albedo = [0.5 * (1 + random.random()), 0.5 * (1 + random.random()), 0.5 * (1 + random.random())]
                        fuzz = 0.5 * random.random()
                        builder.add_sphere(center, 0.2, "metal", albedo, fuzz, 1.5)
                    else:
                        # Glass
                        tint = [0.95 + 0.05*random.random(), 0.95 + 0.05*random.random(), 0.95 + 0.05*random.random()]
                        builder.add_sphere(center, 0.2, "dielectric", tint, 0.0, 1.5)

        # Big Spheres
        builder.add_sphere(v3(0, 1, 0), 1.0, "dielectric", [1, 1, 1], 0.0, 1.5)
        builder.add_sphere(v3(-4, 1, 0), 1.0, "plastic", [1, 1, 1], 0.0, 1.5)
        builder.add_sphere(v3(4, 1, 0), 1.0, "metal", [1, 1, 1], 0.0, 1.5)

        return SceneConfig(
            lookfrom=[11, 2, 3],
            lookat=[0, 0, 0],
            vup=[0, 1, 0],
            vfov=40.0, aperture=0.05, focus_dist=10.0,
            env_map=None, 
            env_light_level=1.0,
            env_direct_level=0.5,
            env_indirect_level=0.5
        )

class MaterialsShowcase(Scene):
    def setup(self, builder, config_overrides: dict = None) -> SceneConfig:
        def v3(x, y, z): return cpp_engine.Vec3(float(x), float(y), float(z))
        def rnd_col(): return [random.random(), random.random(), random.random()]
        def dist_sq(v1, v2): return (v1.x()-v2.x())**2 + (v1.y()-v2.y())**2 + (v1.z()-v2.z())**2
        random.seed(42)

        # 1. Le Sol (Plateau damier)
        builder.add_checker_sphere(v3(0, -1000, 0), 1000.0, [0.1, 0.1, 0.1], [0.5, 0.5, 0.5], 2.0)
        
        placed_spheres = []
        # 2. Les 4 Grosses Sphères
        large_radius = 1.0
        large_y = large_radius
        # On stocke leurs positions pour que les petites ne rentrent pas dedans
        large_positions = [v3(-4.5, large_y, 0), v3(-1.5, large_y, 0), v3(1.5, large_y, 0), v3(4.5, large_y, 0)]
        
        builder.add_sphere(large_positions[0], large_radius, "lambertian", [0.9, 0.9, 0.9])
        builder.add_sphere(large_positions[1], large_radius, "dielectric", [1.0, 1.0, 1.0])
        builder.add_sphere(large_positions[2], large_radius, "plastic", [0.2, 0.5, 0.9])
        builder.add_sphere(large_positions[3], large_radius, "metal", [0.8, 0.85, 0.88], 0.0)
        
        for pos in large_positions: placed_spheres.append((pos, large_radius))

        # 3. Les Mini Sphères (Placement sans collision)
        mini_radius = 0.25
        # Marge de sécurité pour éviter que les sphères ne se touchent parfaitement
        padding = 0.05
        
        # Fonction helper pour générer des sphères dans une zone donnée
        def generate_and_place(target_count, x_range, z_range, total_placed_so_far):
            count = 0
            attempts = 0
            max_attempts = target_count * 200
            while count < target_count and attempts < max_attempts:
                attempts += 1
                # Candidat position
                x, z = random.uniform(*x_range), random.uniform(*z_range)
                candidate_center = v3(x, mini_radius, z)
                
                # Check collision avec TOUTES les sphères précédentes (grosses et petites)
                collision = False
                for existing_c, existing_r in placed_spheres:
                    if dist_sq(candidate_center, existing_c) < (mini_radius + existing_r + padding)**2:
                        collision = True; break
                if collision: continue # On rejette et on réessaie

                # Pas de collision, on place la sphère
                col = rnd_col()
                # L'index du matériau dépend du nombre total de petites sphères placées
                mat_idx = (total_placed_so_far + count) % 4
                if mat_idx == 0: builder.add_sphere(candidate_center, mini_radius, "lambertian", col)
                elif mat_idx == 1: builder.add_sphere(candidate_center, mini_radius, "dielectric", [0.7 + 0.3*random.random()]*3)
                elif mat_idx == 2: builder.add_sphere(candidate_center, mini_radius, "plastic", col)
                elif mat_idx == 3: builder.add_sphere(candidate_center, mini_radius, "metal", col, random.uniform(0.0, 0.2))
                
                # On ajoute à la liste des obstacles
                placed_spheres.append((candidate_center, mini_radius))
                count += 1
            
            if attempts >= max_attempts:
                print(f"Warning: Could not place all spheres in zone Z={z_range}. Area too crowded.")
            return count

        generate_and_place(80, (-7, 7), (2.0, 7.0), 0)

        return SceneConfig(
            lookfrom=[0, 3, 8], lookat=[0, 1, 0], vup=[0, 1, 0], vfov=50.0, aperture=0.1, focus_dist=8.0,
            env_map="env-dock-sun.hdr", env_light_level=1.0, env_direct_level=0.6, env_indirect_level=2.0
        )

class MeshScene1(Scene):
    def setup(self, builder, config_overrides: dict = None) -> SceneConfig:
        # 1. Le Sol
        builder.add_checker_sphere(
            cpp_engine.Vec3(0.0, -100, -1.0), 100.0,
            [0.2, 0.3, 0.1], [0.9, 0.9, 0.9], 10.0
        )
        
        # 2. Chargement via le Builder (Système éditable)
        # On définit l'asset (le modèle 3D + matériau de base)
        builder.load_asset(
            "my_bunny_asset",                  # Nom unique de l'asset
            "assets/bunny/bunny.obj",          # Chemin
            override_mat="dielectric", 
            override_color=[0.7, 0.9, 0.85],
            override_ior=1.5
        )

        # 3. Instanciation (Placement dans la scène)
        # C'est ici que l'objet est ajouté au registre Python et devient cliquable
        builder.add_mesh_instance(
            "my_bunny_asset",
            pos=[0, 0, 0],
            rot=[0, 0, 0],
            scale=[1.0, 1.0, 1.0]
        )

        return SceneConfig(
            lookfrom=[0, 2, 5], 
            lookat=[0, 0, 0], 
            vfov=40.0, 
            env_map="env-dock-sun.hdr"
        )

class MeshScene2(Scene):
    def setup(self, builder):
        # 1. Le Sol
        floor_height = -0.5
        builder.add_checker_sphere(
            cpp_engine.Vec3(0.0, -100.0 + floor_height, -1.0), 100.0,
            [0.2, 0.3, 0.1], [0.9, 0.9, 0.9], 10.0
        )

        # 2. Chargement Assets
        # On charge deux versions : une brute, une en verre
        info_glass = builder.load_asset("obj_glass", "assets/dragon/dragon.obj", override_mat="dielectric", override_color=[0.9, 0.95, 1.0])
        _          = builder.load_asset("obj_metal", "assets/dragon/dragon.obj", override_mat="metal", override_color=[0.8, 0.6, 0.2])

        if info_glass is None:
            print("Erreur chargement asset")
            return
        
        # 3. Le Roi (Centre)
        scale_king = 2.5
        y_pos_king = floor_height - (scale_king * info_glass.bottom_y)
        
        builder.add_mesh_instance(
            "obj_glass", 
            pos=[0, y_pos_king, 0], 
            rot=[0, 90, 0],        # Rotation Y=90 degrés
            scale=[scale_king, scale_king, scale_king]
        )

        # 4. La Garde Royale
        scale_guard = 1.0
        y_pos_guard = floor_height - (scale_guard * info_glass.bottom_y)
        radius = 2.0
        count = 8
        
        for i in range(count):
            angle = (360.0 / count) * i
            x = radius * math.cos(math.radians(angle))
            z = radius * math.sin(math.radians(angle))
            
            # Plus besoin de maths complexes ici, on déclare juste l'intention
            builder.add_mesh_instance(
                "obj_metal",
                pos=[x, y_pos_guard, z],
                rot=[0, -angle - 90, 0], # Orientation
                scale=[scale_guard, scale_guard, scale_guard]
            )

        return SceneConfig(
            lookfrom=[-0.9, 0.7, 3.93], lookat=[-0.73, 0.5, 2.96], vfov=50.0,
            aperture=0.1, focus_dist=3.72, env_map="env-dock-sun.hdr",
            env_light_level=1.0, env_direct_level=0.6, env_indirect_level=2.0
        )

# Registry
AVAILABLE_SCENES = {
    "cornell": CornellBox(),
    "random": RandomSpheres(),
    "showcase": MaterialsShowcase(),
    "mesh1": MeshScene1(),
    "mesh2": MeshScene2()
}