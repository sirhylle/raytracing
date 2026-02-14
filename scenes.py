import cpp_engine
import numpy as np
import random
from dataclasses import dataclass
from typing import Optional, List, Tuple
import math
import materials # NEW

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
    # Environment (Union[str, List[float]])
    # str -> Path to HDR/Image
    # List[float] -> RGB Color [r, g, b]
    environment: Optional[object] = None 
    # Lighting
    env_exposure: float = 1.0
    env_background: float = 1.0     
    env_diffuse: float = 0.5    
    env_specular: float = 0.5    

    
# Helper to unpack preset
def p(name):
    """Returns PBR params as dict for unpacking into add_* calls."""
    data = materials.get_preset_params(name) # {'roughness':..., 'metallic':..., ...}
    # We must also specify mat_type="standard" for C++
    data['mat_type'] = "standard"
    return data

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
        
        # Scale Factor: 0.01
        # Original: 555 -> 5.55
        
        # Left Green
        builder.add_quad(v3([5.55,0,0]), v3([0,5.55,0]), v3([0,0,5.55]), color=green, **p("CLAY"))
        # Right Red
        builder.add_quad(v3([0,0,0]), v3([0,5.55,0]), v3([0,0,5.55]), color=red, **p("CLAY"))
        # Top Light
        # Orig: [343, 554, 332], [-130,0,0], [0,0,-105]
        builder.add_quad(v3([3.43, 5.54, 3.32]), v3([-1.30,0,0]), v3([0,0,-1.05]), mat_type="light", color=light_color)
        # Floor
        builder.add_quad(v3([0,0,0]), v3([5.55,0,0]), v3([0,0,5.55]), color=white, **p("CLAY"))
        # Ceiling
        builder.add_quad(v3([5.55,5.55,5.55]), v3([-5.55,0,0]), v3([0,0,-5.55]), color=white, **p("CLAY"))
        # Back
        builder.add_quad(v3([0,0,5.55]), v3([5.55,0,0]), v3([0,5.55,0]), color=white, **p("CLAY"))
        
        # Objects (Radius 100 -> 1.0)
        # Metal Sphere
        # Orig: [200, 100, 200]
        builder.add_sphere(v3([2.00, 1.00, 2.00]), 1.0, color=[0.8, 0.85, 0.88], **p("CHROME"))
        # Glass Sphere
        # Orig: [400, 100, 300]
        builder.add_sphere(v3([4.00, 1.00, 3.00]), 1.0, color=[1.0, 1.0, 1.0], **p("GLASS"))

        return SceneConfig(
            lookfrom=[2.78, 2.78, -8.00], # Orig: 278, 278, -800
            lookat=[2.78, 2.78, 0],       # Orig: 278, 278, 0
            vup=[0, 1, 0],
            vfov=40.0,
            aperture=0.0,
            focus_dist=10.0, # Scaled reasonable dist
            environment=None,
            env_exposure=1.0,
            env_background=0.0, # Box is closed, no background needed usually (or black)
            env_diffuse=0.5,
            env_specular=0.5
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
                        # Diffuse (Clay) or Plastic
                        albedo = [random.random() * random.random(), random.random() * random.random(), random.random() * random.random()]
                        if random.random() < 0.5:
                            builder.add_sphere(center, 0.2, color=albedo, **p("CLAY"))
                        else:
                            builder.add_sphere(center, 0.2, color=albedo, **p("HARD_PLASTIC"))
                    elif choose_mat < 0.85:
                        # Metal
                        albedo = [0.5 * (1 + random.random()), 0.5 * (1 + random.random()), 0.5 * (1 + random.random())]
                        vals = p("CHROME")
                        vals['roughness'] = 0.5 * random.random() # Fuzz
                        builder.add_sphere(center, 0.2, color=albedo, **vals)
                    else:
                        # Glass
                        tint = [0.95 + 0.05*random.random(), 0.95 + 0.05*random.random(), 0.95 + 0.05*random.random()]
                        builder.add_sphere(center, 0.2, color=tint, **p("GLASS"))

        # Big Spheres
        builder.add_sphere(v3(0, 1, 0), 1.0, color=[1, 1, 1], **p("GLASS"))
        builder.add_sphere(v3(-4, 1, 0), 1.0, color=[1, 1, 1], **p("HARD_PLASTIC"))
        builder.add_sphere(v3(4, 1, 0), 1.0, color=[1, 1, 1], **p("CHROME"))

        return SceneConfig(
            lookfrom=[11, 2, 3],
            lookat=[0, 0, 0],
            vup=[0, 1, 0],
            vfov=40.0, aperture=0.05, focus_dist=10.0,
            environment=None, 
            env_exposure=1.0,
            env_background=1.0,
            env_diffuse=0.5,
            env_specular=0.5
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
        large_positions = [v3(-4.5, large_y, 0), v3(-1.5, large_y, 0), v3(1.5, large_y, 0), v3(4.5, large_y, 0)]
        
        builder.add_sphere(large_positions[0], large_radius, color=[0.9, 0.9, 0.9], **p("CLAY"))
        builder.add_sphere(large_positions[1], large_radius, color=[1.0, 1.0, 1.0], **p("GLASS"))
        builder.add_sphere(large_positions[2], large_radius, color=[0.2, 0.5, 0.9], **p("HARD_PLASTIC"))
        builder.add_sphere(large_positions[3], large_radius, color=[0.8, 0.85, 0.88], **p("CHROME"))
        
        for pos in large_positions: placed_spheres.append((pos, large_radius))

        # 3. Les Mini Sphères
        mini_radius = 0.25
        padding = 0.05
        
        def generate_and_place(target_count, x_range, z_range, total_placed_so_far):
            count = 0
            attempts = 0
            max_attempts = target_count * 200
            while count < target_count and attempts < max_attempts:
                attempts += 1
                x, z = random.uniform(*x_range), random.uniform(*z_range)
                candidate_center = v3(x, mini_radius, z)
                
                collision = False
                for existing_c, existing_r in placed_spheres:
                    if dist_sq(candidate_center, existing_c) < (mini_radius + existing_r + padding)**2:
                        collision = True; break
                if collision: continue 

                col = rnd_col()
                mat_idx = (total_placed_so_far + count) % 4
                
                if mat_idx == 0: builder.add_sphere(candidate_center, mini_radius, color=col, **p("CLAY"))
                elif mat_idx == 1: builder.add_sphere(candidate_center, mini_radius, color=[0.7 + 0.3*random.random()]*3, **p("GLASS"))
                elif mat_idx == 2: builder.add_sphere(candidate_center, mini_radius, color=col, **p("HARD_PLASTIC"))
                elif mat_idx == 3: 
                    vals = p("CHROME")
                    vals['roughness'] = random.uniform(0.0, 0.2)
                    builder.add_sphere(candidate_center, mini_radius, color=col, **vals)
                
                placed_spheres.append((candidate_center, mini_radius))
                count += 1
            return count

        generate_and_place(80, (-7, 7), (2.0, 7.0), 0)

        return SceneConfig(
            lookfrom=[0, 3, 8], lookat=[0, 1, 0], vup=[0, 1, 0], vfov=50.0, aperture=0.1, focus_dist=8.0,
            environment="env-dock-sun.hdr", env_exposure=1.0, env_background=1.0, env_diffuse=0.6, env_specular=2.0
        )

class Empty(Scene):
    def setup(self, builder, config_overrides: dict = None) -> SceneConfig:
        def v3(x, y, z): return cpp_engine.Vec3(float(x), float(y), float(z))

        # 1. Le Sol (Plateau damier)
        builder.add_checker_sphere(v3(0, -1000, 0), 1000.0, [0.1, 0.1, 0.1], [0.5, 0.5, 0.5], 2.0)
        
        return SceneConfig(
            lookfrom=[0, 3, 8], lookat=[0, 1, 0], vup=[0, 1, 0], vfov=50.0, aperture=0.0, focus_dist=8.0,
            environment="env-dock-sun.hdr", env_exposure=1.0, env_background=1.0, env_diffuse=0.6, env_specular=2.0
        )

class MeshScene1(Scene):
    def setup(self, builder, config_overrides: dict = None) -> SceneConfig:
        builder.add_checker_sphere(cpp_engine.Vec3(0.0, -100, -1.0), 100.0, [0.2, 0.3, 0.1], [0.9, 0.9, 0.9], 10.0)
        
        # Load Asset with overrides
        vals = p("GLASS")
        builder.load_asset(
            "my_bunny_asset", "assets/bunny/bunny.obj",
            override_mat="standard",
            override_color=[0.7, 0.9, 0.85],
            override_roughness=vals['roughness'],
            override_metallic=vals['metallic'],
            override_ior=vals['ir'],
            override_transmission=vals['transmission']
        ) # Note: 'override_mat' is string type in C++, 'standard' is used.
        # But wait, load_mesh_asset Signature:
        # load_mesh_asset(name, v, i, n, mat_type, color, rough, metal, ir, trans)
        # So I need to verify loader.py behavior for 'load_asset' which builds 'load_mesh_asset' calls.

        builder.add_mesh_instance("my_bunny_asset", pos=[0, 0, 0], rot=[0, 0, 0], scale=[1.0, 1.0, 1.0])

        return SceneConfig(lookfrom=[0, 2, 5], lookat=[0, 0, 0], vfov=40.0, environment="env-dock-sun.hdr")

class MeshScene2(Scene):
    def setup(self, builder):
        floor_height = -0.5
        builder.add_checker_sphere(cpp_engine.Vec3(0.0, -100.0 + floor_height, -1.0), 100.0, [0.2, 0.3, 0.1], [0.9, 0.9, 0.9], 10.0)

        vg = p("GLASS")
        info_glass = builder.load_asset("obj_glass", "assets/dragon/dragon.obj", 
                                        override_mat="standard", override_color=[0.9, 0.95, 1.0],
                                        override_roughness=vg['roughness'], override_metallic=vg['metallic'],
                                        override_ior=vg['ir'], override_transmission=vg['transmission'])
                                        
        vm = p("GOLD") # Let's use Gold instead of Chrome for variety
        _          = builder.load_asset("obj_metal", "assets/dragon/dragon.obj", 
                                        override_mat="standard", override_color=[0.8, 0.6, 0.2],
                                        override_roughness=vm['roughness'], override_metallic=vm['metallic'],
                                        override_ior=vm['ir'], override_transmission=vm['transmission'])

        if info_glass is None: return
        
        scale_king = 2.5
        y_pos_king = floor_height - (scale_king * info_glass.bottom_y)
        builder.add_mesh_instance("obj_glass", pos=[0, y_pos_king, 0], rot=[0, 90, 0], scale=[scale_king]*3)

        scale_guard = 1.0
        y_pos_guard = floor_height - (scale_guard * info_glass.bottom_y)
        radius = 2.0
        count = 8
        
        for i in range(count):
            angle = (360.0 / count) * i
            x = radius * math.cos(math.radians(angle))
            z = radius * math.sin(math.radians(angle))
            builder.add_mesh_instance("obj_metal", pos=[x, y_pos_guard, z], rot=[0, -angle - 90, 0], scale=[scale_guard]*3)

        return SceneConfig(lookfrom=[-0.9, 0.7, 3.93], lookat=[-0.73, 0.5, 2.96], vfov=50.0, aperture=0.1, focus_dist=3.72, environment="env-dock-sun.hdr")

class Basic(Scene):
    def setup(self, builder, config_overrides: dict = None) -> SceneConfig:
        def v3(l):
            return cpp_engine.Vec3(float(l[0]), float(l[1]), float(l[2]))

        # Light
        builder.add_sphere(v3([0, 5, 0]), 1.0, mat_type="light", color=[10, 10, 10])
        
        # Test Sphere (Red-ish)
        builder.add_sphere(v3([0, 0, -1]), 0.5, mat_type="standard", color=[0.8, 0.3, 0.3], 
                           roughness=0.1, metallic=0.0, ir=1.5, transmission=0.0)
        
        # Floor (Large Gray Plane)
        builder.add_quad(v3([-10, -0.5, -10]), v3([20, 0, 0]), v3([0, 0, 20]), 
                         mat_type="standard", color=[0.8, 0.8, 0.8], roughness=0.5)

        return SceneConfig(
            lookfrom=[0, 0, 3],
            lookat=[0, 0, 0],
            vup=[0, 1, 0],
            vfov=40.0,
            aperture=0.0,
            focus_dist=3.0,
            environment=[1.0, 1.0, 1.0],
            env_exposure=1.0,
            env_background=1.0, 
            env_diffuse=0.5,
            env_specular=0.5
        )

AVAILABLE_SCENES = {
    "cornell": CornellBox(),
    "random": RandomSpheres(),
    "showcase": MaterialsShowcase(),
    "mesh1": MeshScene1(),
    "mesh2": MeshScene2(),
    "empty": Empty(),
    "basic": Basic()
}
