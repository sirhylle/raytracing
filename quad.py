from hittable import Hittable, HitRecord
from vec3 import Vec3, cross, dot, unit_vector, length
from ray import Ray
import math
import numpy as np

class Quad(Hittable):
    def __init__(self, Q: Vec3, u: Vec3, v: Vec3, material):
        self.Q = Q
        self.u = u
        self.v = v
        self.mat = material
        
        n = cross(u, v)
        self.normal = unit_vector(n)
        self.D = dot(self.normal, Q)
        self.w = n / dot(n, n)
        self.area = length(n)

    def hit(self, r, t_min, t_max):
        denom = dot(self.normal, r.direction)
        
        # No hit if parallel
        if abs(denom) < 1e-8:
            return None

        t = (self.D - dot(self.normal, r.origin)) / denom
        if t < t_min or t > t_max:
            return None
            
        intersection = r.at(t)
        planar_hitpt_vector = intersection - self.Q
        alpha = dot(self.w, cross(planar_hitpt_vector, self.v))
        beta = dot(self.w, cross(self.u, planar_hitpt_vector))
        
        if not (0 <= alpha <= 1 and 0 <= beta <= 1):
            return None
            
        rec = HitRecord(p=intersection, normal=self.normal, t=t, u=alpha, v=beta, front_face=True, material=self.mat)
        rec.set_face_normal(r, self.normal)
        return rec
        
    def pdf_value(self, origin: Vec3, v: Vec3) -> float:
        hit_rec = self.hit(Ray(origin, v), 0.001, float('inf'))
        if not hit_rec:
            return 0.0
            
        distance_squared = hit_rec.t * hit_rec.t * length(v)**2 # Approximate if v is not unit? v should be direction. 
        # t is distance if direction is unit. If v is not unit, t is scale factor.
        # Assuming v is a direction vector for PDF, likely unit or used for direction.
        # In RayTracingTheRestOfYourLife, pdf = distance_squared / (cosine * area)
        
        d_sq = hit_rec.t * hit_rec.t * np.dot(v, v)
        cosine = abs(dot(v, hit_rec.normal) / length(v))
        
        return d_sq / (cosine * self.area)

    def random(self, origin: Vec3) -> Vec3:
        p = self.Q + (np.random.rand() * self.u) + (np.random.rand() * self.v)
        return p - origin
