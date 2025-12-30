from vec3 import Vec3, point3, vec3, cross, unit_vector, random_in_unit_disk
from ray import Ray
import math
import numpy as np

class Camera:
    def __init__(self, lookfrom: Vec3, lookat: Vec3, vup: Vec3, vfov: float, aspect_ratio: float, aperture: float = 0.0, focus_dist: float = 10.0):
        theta = math.radians(vfov)
        h = math.tan(theta/2)
        viewport_height = 2.0 * h
        viewport_width = aspect_ratio * viewport_height
        
        self.w = unit_vector(lookfrom - lookat)
        self.u = unit_vector(cross(vup, self.w))
        self.v = cross(self.w, self.u)
        
        self.origin = lookfrom
        self.horizontal = focus_dist * viewport_width * self.u
        self.vertical = focus_dist * viewport_height * self.v
        self.lower_left_corner = self.origin - self.horizontal/2 - self.vertical/2 - focus_dist*self.w
        
        self.lens_radius = aperture / 2
        
    def get_ray(self, s: float, t: float) -> Ray:
        rd = self.lens_radius * random_in_unit_disk() if self.lens_radius > 0 else vec3(0,0,0)
        offset = self.u * rd[0] + self.v * rd[1]
        
        return Ray(
            self.origin + offset,
            self.lower_left_corner + s*self.horizontal + t*self.vertical - self.origin - offset,
            np.random.rand() # Time
        )


