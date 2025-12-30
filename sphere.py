from hittable import Hittable, HitRecord
from vec3 import Vec3, point3, dot, length_squared, unit_vector, random_unit_vector
from ray import Ray
import math
import numpy as np

class Sphere(Hittable):
    def __init__(self, center: Vec3, radius: float, material):
        self.center = center
        self.radius = radius
        self.mat = material

    def hit(self, r, t_min, t_max):
        oc = r.origin - self.center
        a = length_squared(r.direction)
        half_b = dot(oc, r.direction)
        c = length_squared(oc) - self.radius * self.radius
        discriminant = half_b * half_b - a * c

        if discriminant < 0:
            return None

        sqrtd = math.sqrt(discriminant)
        root = (-half_b - sqrtd) / a
        if root <= t_min or t_max <= root:
            root = (-half_b + sqrtd) / a
            if root <= t_min or t_max <= root:
                return None

        t = root
        p = r.at(t)
        outward_normal = (p - self.center) / self.radius
        
        # UV coordinates (spherical)
        theta = math.acos(-outward_normal[1])
        phi = math.atan2(-outward_normal[2], outward_normal[0]) + math.pi
        u = phi / (2 * math.pi)
        v = theta / math.pi
        
        rec = HitRecord(p=p, normal=outward_normal, t=t, u=u, v=v, front_face=True, material=self.mat)
        rec.set_face_normal(r, outward_normal)
        return rec
    
    def get_uv(self, p):
        # Already calculated in hit
        pass

    def random(self, origin: Vec3) -> Vec3:
        direction = self.center - origin
        distance_squared = length_squared(direction)
        
        # Create an orthonormal basis (uvw)
        w = unit_vector(direction)
        a = 1.0 if abs(w[0]) > 0.9 else 0.0
        # cross product with (0,1,0) or (1,0,0) depending on w
        if abs(w[0]) > 0.9:
            v_up = np.array([0, 1, 0])
        else:
            v_up = np.array([1, 0, 0])
            
        u = unit_vector(np.cross(v_up, w))
        v = np.cross(w, u)
        
        # Random point in cone
        # We need a random cone direction. 
        # But wait, the standard way is to sample the solid angle.
        # Let's use the method from Ray Tracing: The Rest of Your Life
        
        r1 = np.random.rand()
        r2 = np.random.rand()
        z = 1 + r2 * (math.sqrt(1 - self.radius*self.radius/distance_squared) - 1)
        phi = 2 * math.pi * r1
        x = math.cos(phi) * math.sqrt(1 - z*z)
        y = math.sin(phi) * math.sqrt(1 - z*z)
        
        return u * x + v * y + w * z

    def pdf_value(self, origin: Vec3, v: Vec3) -> float:
        # This returns the PDF value of the direction v
        hit_rec = self.hit(Ray(origin, v), 0.001, float('inf'))
        if not hit_rec:
            return 0.0
        
        cos_theta_max = math.sqrt(1 - self.radius*self.radius/length_squared(self.center - origin))
        solid_angle = 2 * math.pi * (1 - cos_theta_max)
        return 1.0 / solid_angle
