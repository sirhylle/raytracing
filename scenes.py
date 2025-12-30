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
    ambient: float = 1.0     # Sky lighting intensity (Light)
    sky_gain: float = 1.0    # Sky camera visibility (Visual)
    # Debug info (returned for UI/Logging)
    sun_intensity: Optional[float] = None
    sun_visible: Optional[bool] = None

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
            ambient=2.0,
            sky_gain=1.0
        )

class RandomSpheres(Scene):
    def setup(self, engine: cpp_engine.Engine, config_overrides: dict = None) -> SceneConfig:
        # Defaults
        default_sun_intensity = 10.0
        default_sun_visible = False
        
        # Apply Overrides
        overrides = config_overrides or {}
        sun_intens = overrides.get('sun_intensity', default_sun_intensity)
        sun_vis = overrides.get('sun_visible', default_sun_visible)

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
        sun_pos = v3(0, 100, -100)
        if sun_vis:
            engine.add_sphere(sun_pos, 30.0, "light", v3(sun_intens, sun_intens, sun_intens), 0.0, 1.0)
        else:
            engine.add_invisible_sphere_light(sun_pos, 30.0, v3(sun_intens, sun_intens, sun_intens))

        return SceneConfig(
            lookfrom=[11, 2, 3],
            lookat=[0, 0, 0],
            vup=[0, 1, 0],
            vfov=40.0, 
            aperture=0.05,
            focus_dist=10.0,
            env_map=None, 
            ambient=1.0,
            sky_gain=1.0,
            sun_intensity=sun_intens,
            sun_visible=sun_vis
        )

# Registry
AVAILABLE_SCENES = {
    "cornell": CornellBox(),
    "random": RandomSpheres()
}
