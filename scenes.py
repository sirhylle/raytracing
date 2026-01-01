import cpp_engine
import numpy as np
import random
from dataclasses import dataclass
from typing import Optional, List, Tuple

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
    env_background_level: float = 1.0     # Sky brightness (when viewed directly)
    env_direct_level: float = 0.5    # Sky lighting intensity (by direct lighting)
    env_indirect_level: float = 0.5    # Sky lighting intensity (by indirect lighting)

class Scene:
    def setup(self, engine: cpp_engine.Engine, config_overrides: dict = None) -> SceneConfig:
        raise NotImplementedError

class CornellBox(Scene):
    def setup(self, engine: cpp_engine.Engine, config_overrides: dict = None) -> SceneConfig:
        def v3(l):
            return cpp_engine.Vec3(float(l[0]), float(l[1]), float(l[2]))

        # Materials & Geometry
        green = [0.12, 0.45, 0.15]
        red   = [0.65, 0.05, 0.05]
        white = [0.73, 0.73, 0.73]
        light_color = [15.0, 15.0, 15.0]
        
        # Left Green
        engine.add_quad(v3([555,0,0]), v3([0,555,0]), v3([0,0,555]), "lambertian", v3(green), 0.0, 1.5)
        # Right Red
        engine.add_quad(v3([0,0,0]), v3([0,555,0]), v3([0,0,555]), "lambertian", v3(red), 0.0, 1.5)
        # Light
        engine.add_quad(v3([343, 554, 332]), v3([-130,0,0]), v3([0,0,-105]), "light", v3(light_color), 0.0, 1.5)
        # Floor
        engine.add_quad(v3([0,0,0]), v3([555,0,0]), v3([0,0,555]), "lambertian", v3(white), 0.0, 1.5)
        # Ceiling
        engine.add_quad(v3([555,555,555]), v3([-555,0,0]), v3([0,0,-555]), "lambertian", v3(white), 0.0, 1.5)
        # Back
        engine.add_quad(v3([0,0,555]), v3([555,0,0]), v3([0,555,0]), "lambertian", v3(white), 0.0, 1.5)
        
        # Objects
        engine.add_sphere(v3([200, 100, 200]), 100.0, "metal", v3([0.8, 0.85, 0.88]), 0.0, 1.5)
        engine.add_sphere(v3([400, 100, 300]), 100.0, "dielectric", v3([1.0, 1.0, 1.0]), 0.0, 1.5)

        return SceneConfig(
            lookfrom=[278, 278, -800],
            lookat=[278, 278, 0],
            vup=[0, 1, 0],
            vfov=40.0,
            aperture=0.0,
            focus_dist=10.0,
            env_map=None,
            env_background_level=1.0,
            env_direct_level=0.5,
            env_indirect_level=0.5
        )

class RandomSpheres(Scene):
    def setup(self, engine: cpp_engine.Engine, config_overrides: dict = None) -> SceneConfig:
        
        def v3(x, y, z):
            return cpp_engine.Vec3(float(x), float(y), float(z))

        # Ground
        engine.add_checker_sphere(v3(0, -1000, 0), 1000.0, 
                                  v3(0.2, 0.3, 0.1), 
                                  v3(0.9, 0.9, 0.9), 
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
                        albedo = v3(random.random() * random.random(), 
                                    random.random() * random.random(), 
                                    random.random() * random.random())
                        if random.random() < 0.5:
                            engine.add_sphere(center, 0.2, "lambertian", albedo, 0.0, 1.5)
                        else:
                            engine.add_sphere(center, 0.2, "plastic", albedo, 0.0, 1.5)
                    elif choose_mat < 0.85:
                        # Metal
                        albedo = v3(0.5 * (1 + random.random()), 
                                    0.5 * (1 + random.random()), 
                                    0.5 * (1 + random.random()))
                        fuzz = 0.5 * random.random()
                        engine.add_sphere(center, 0.2, "metal", albedo, fuzz, 1.5)
                    else:
                        # Glass
                        tint = v3(0.95 + 0.05*random.random(), 
                                  0.95 + 0.05*random.random(), 
                                  0.95 + 0.05*random.random()) # Light tint
                        engine.add_sphere(center, 0.2, "dielectric", tint, 0.0, 1.5)

        # Big Spheres
        engine.add_sphere(v3(0, 1, 0), 1.0, "dielectric", v3(1, 1, 1), 0.0, 1.5)
        engine.add_sphere(v3(-4, 1, 0), 1.0, "plastic", v3(1, 1, 1), 0.0, 1.5)
        engine.add_sphere(v3(4, 1, 0), 1.0, "metal", v3(1, 1, 1), 0.0, 1.5)
        
        # Sun Light
        # sun_pos = v3(0, 100, -100)
        # if sun_vis:
        #     engine.add_sphere(sun_pos, 30.0, "light", v3(sun_intens, sun_intens, sun_intens), 0.0, 1.0)
        # else:
        #     engine.add_invisible_sphere_light(sun_pos, 30.0, v3(sun_intens, sun_intens, sun_intens))

        return SceneConfig(
            lookfrom=[11, 2, 3],
            lookat=[0, 0, 0],
            vup=[0, 1, 0],
            vfov=40.0, 
            aperture=0.05,
            focus_dist=10.0,
            env_map=None, 
            env_background_level=1.0,
            env_direct_level=0.5,
            env_indirect_level=0.5
        )

class MaterialsShowcase(Scene):
    def setup(self, engine: cpp_engine.Engine, config_overrides: dict = None) -> SceneConfig:
        def v3(x, y, z): return cpp_engine.Vec3(float(x), float(y), float(z))
        def rnd_v3(): return v3(random.random(), random.random(), random.random())
        def dist_sq(v1, v2):
            return (v1.x()-v2.x())**2 + (v1.y()-v2.y())**2 + (v1.z()-v2.z())**2

        random.seed(42) # Graine fixe pour la reproductibilité

        # 1. Le Sol (Plateau damier)
        engine.add_checker_sphere(
            v3(0, -1000, 0), 1000.0, 
            v3(0.1, 0.1, 0.1), v3(0.5, 0.5, 0.5), 10.0)

        # Liste pour stocker les sphères existantes (centre, rayon) pour les collisions
        placed_spheres = []

        # 2. Les 4 Grosses Sphères
        large_radius = 1.0
        large_y = large_radius
        # On stocke leurs positions pour que les petites ne rentrent pas dedans
        large_positions = [
            v3(-4.5, large_y, 0), v3(-1.5, large_y, 0),
            v3(1.5, large_y, 0), v3(4.5, large_y, 0)
        ]
        
        engine.add_sphere(large_positions[0], large_radius, "lambertian", v3(0.9, 0.9, 0.9))
        engine.add_sphere(large_positions[1], large_radius, "dielectric", v3(1.0, 1.0, 1.0))
        engine.add_sphere(large_positions[2], large_radius, "plastic", v3(0.2, 0.5, 0.9))
        engine.add_sphere(large_positions[3], large_radius, "metal", v3(0.8, 0.85, 0.88), 0.0)
        
        for pos in large_positions:
            placed_spheres.append((pos, large_radius))


        # 3. Les Mini Sphères (Placement sans collision)
        mini_radius = 0.25
        # Marge de sécurité pour éviter que les sphères ne se touchent parfaitement
        padding = 0.05 
        min_dist_sq = (mini_radius + mini_radius + padding)**2
        
        # Fonction helper pour générer des sphères dans une zone donnée
        def generate_and_place(target_count, x_range, z_range, total_placed_so_far):
            count = 0
            attempts = 0
            max_attempts = target_count * 200 # Sécurité anti boucle infinie

            while count < target_count and attempts < max_attempts:
                attempts += 1
                
                # Candidat position
                x = random.uniform(x_range[0], x_range[1])
                z = random.uniform(z_range[0], z_range[1])
                candidate_center = v3(x, mini_radius, z)
                
                # Check collision avec TOUTES les sphères précédentes (grosses et petites)
                collision = False
                for existing_c, existing_r in placed_spheres:
                    # Seuil de distance au carré dépend des rayons respectifs
                    threshold_sq = (mini_radius + existing_r + padding)**2
                    if dist_sq(candidate_center, existing_c) < threshold_sq:
                        collision = True
                        break
                
                if collision:
                    continue # On rejette et on réessaie

                # Pas de collision, on place la sphère
                col = rnd_v3()
                # L'index du matériau dépend du nombre total de petites sphères placées
                mat_idx = (total_placed_so_far + count) % 4
                
                if mat_idx == 0: # Mat
                    engine.add_sphere(candidate_center, mini_radius, "lambertian", col)
                elif mat_idx == 1: # Dielectric
                    tint = v3(0.7 + 0.3*random.random(), 0.7 + 0.3*random.random(), 0.7 + 0.3*random.random())
                    engine.add_sphere(candidate_center, mini_radius, "dielectric", tint)
                elif mat_idx == 2: # Plastic
                    engine.add_sphere(candidate_center, mini_radius, "plastic", col)
                elif mat_idx == 3: # Metal
                    fuzz = random.uniform(0.0, 0.2)
                    engine.add_sphere(candidate_center, mini_radius, "metal", col, fuzz)
                
                # On ajoute à la liste des obstacles
                placed_spheres.append((candidate_center, mini_radius))
                count += 1
            
            if attempts >= max_attempts:
                print(f"Warning: Could not place all spheres in zone Z={z_range}. Area too crowded.")
            return count

        # --- Placement par zones ---
        
        # Zone Arrière (Derrière les grosses sphères, Z < -1.5)
        # Environ 24 sphères
        #num_back = generate_and_place(24, (-6, 6), (-5, -2.0), 0)

        # Zone Avant (Devant les grosses sphères, Z > 1.5)
        # Beaucoup plus dense, environ 60 sphères
        #generate_and_place(80, (-7, 7), (2.0, 7.0), num_back)
        generate_and_place(80, (-7, 7), (2.0, 7.0), 0)


        return SceneConfig(
            lookfrom=[0, 3, 8],   
            lookat=[0, 1, 0],      
            vup=[0, 1, 0],
            vfov=50.0,             
            aperture=0.1,          
            focus_dist=8.0,
            env_map="env-dock-sun.hdr",
            env_background_level=1.0,
            env_direct_level=0.6,
            env_indirect_level=2.0
        )

# Registry
AVAILABLE_SCENES = {
    "cornell": CornellBox(),
    "random": RandomSpheres(),
    "showcase": MaterialsShowcase(),
}
