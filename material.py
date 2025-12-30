from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Tuple
import numpy as np
import math
from vec3 import Vec3, dot, unit_vector, random_unit_vector, reflect, refract, near_zero, random_in_unit_sphere, color
from ray import Ray
from hittable import HitRecord

@dataclass
class ScatterRecord:
    specular_ray: Optional[Ray] = None
    attenuation: Optional[Vec3] = None
    is_specular: bool = False
    
    # For PDF based sampling (Diffuse)
    pdf_ptr: object = None # Could be a PDF object or just we use implicit PDF logic in integrator

class Material(ABC):
    def scatter(self, r_in: Ray, hit_record: HitRecord) -> Optional[ScatterRecord]:
        return None
        
    def scattering_pdf(self, r_in: Ray, hit_record: HitRecord, scattered: Ray) -> float:
        return 0.0

    def emit(self, hit_record: HitRecord, u: float, v: float, p: Vec3) -> Vec3:
        return np.array([0, 0, 0], dtype=np.float64)

class Lambertian(Material):
    def __init__(self, albedo: Vec3):
        self.albedo = albedo

    def scatter(self, r_in: Ray, hit_record: HitRecord) -> Optional[ScatterRecord]:
        # Standard scatter: normal + random unit vector which is cos weighted approx
        # For NEE, we generate this ray but the Integrator will also sample lights.
        # This ray is for the Indirect term.
        scatter_direction = hit_record.normal + random_unit_vector()
        
        # Catch degenerate scatter direction
        if near_zero(scatter_direction):
            scatter_direction = hit_record.normal

        scattered = Ray(hit_record.p, unit_vector(scatter_direction), r_in.tm)
        
        return ScatterRecord(
            specular_ray=scattered, # We store it here, but is_specular=False
            attenuation=self.albedo,
            is_specular=False
        )

    def scattering_pdf(self, r_in: Ray, hit_record: HitRecord, scattered: Ray) -> float:
        cosine = dot(hit_record.normal, unit_vector(scattered.direction))
        return float(max(0, cosine / math.pi))

class Metal(Material):
    def __init__(self, albedo: Vec3, fuzz: float):
        self.albedo = albedo
        self.fuzz = fuzz

    def scatter(self, r_in: Ray, hit_record: HitRecord) -> Optional[ScatterRecord]:
        reflected = reflect(unit_vector(r_in.direction), hit_record.normal)
        reflected = unit_vector(reflected + self.fuzz * random_in_unit_sphere())
        scattered = Ray(hit_record.p, reflected, r_in.tm)
        
        if dot(scattered.direction, hit_record.normal) > 0:
            return ScatterRecord(
                specular_ray=scattered,
                attenuation=self.albedo,
                is_specular=True
            )
        return None

class Dielectric(Material):
    def __init__(self, index_of_refraction: float):
        self.ir = index_of_refraction

    def scatter(self, r_in: Ray, hit_record: HitRecord) -> Optional[ScatterRecord]:
        attenuation = color(1.0, 1.0, 1.0)
        ri = (1.0 / self.ir) if hit_record.front_face else self.ir
        
        unit_direction = unit_vector(r_in.direction)
        cos_theta = min(dot(-unit_direction, hit_record.normal), 1.0)
        sin_theta = math.sqrt(1.0 - cos_theta*cos_theta)
        
        cannot_refract = ri * sin_theta > 1.0
        direction = None
        
        if cannot_refract or (self.reflectance(cos_theta, ri) > np.random.rand()):
            direction = reflect(unit_direction, hit_record.normal)
        else:
            direction = refract(unit_direction, hit_record.normal, ri)
            
        scattered = Ray(hit_record.p, direction, r_in.tm)
        return ScatterRecord(
            specular_ray=scattered,
            attenuation=attenuation,
            is_specular=True
        )

    @staticmethod
    def reflectance(cosine: float, ref_idx: float) -> float:
        # Schlick's approximation
        r0 = (1 - ref_idx) / (1 + ref_idx)
        r0 = r0*r0
        return r0 + (1-r0) * math.pow((1 - cosine), 5)

class DiffuseLight(Material):
    def __init__(self, emit_color: Vec3):
        self.emit_color = emit_color
        
    def scatter(self, r_in: Ray, hit_record: HitRecord) -> Optional[ScatterRecord]:
        return None
        
    def emit(self, hit_record: HitRecord, u: float, v: float, p: Vec3) -> Vec3:
        if hit_record.front_face:
            return self.emit_color
        return np.array([0, 0, 0], dtype=np.float64)
