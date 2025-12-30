from dataclasses import dataclass
from abc import ABC, abstractmethod
import math
from vec3 import Vec3, dot

@dataclass
class HitRecord:
    p: Vec3
    normal: Vec3
    t: float
    u: float
    v: float
    front_face: bool
    material: 'Material' = None # Forward reference

    def set_face_normal(self, r: 'Ray', outward_normal: Vec3):
        self.front_face = dot(r.direction, outward_normal) < 0
        self.normal = outward_normal if self.front_face else -outward_normal

class Hittable(ABC):
    @abstractmethod
    def hit(self, r: 'Ray', t_min: float, t_max: float) -> HitRecord:
        """Returns HitRecord if hit, else None"""
        pass
    
    def pdf_value(self, origin: Vec3, v: Vec3) -> float:
        return 0.0
        
    def random(self, origin: Vec3) -> Vec3:
        return Vec3([1, 0, 0]) 
