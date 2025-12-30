from hittable import Hittable, HitRecord
from vec3 import Vec3
import random

class HittableList(Hittable):
    def __init__(self, object=None):
        self.objects = []
        if object:
            self.add(object)

    def add(self, object):
        self.objects.append(object)
        
    def clear(self):
        self.objects = []

    def hit(self, r, t_min, t_max):
        temp_rec = None
        closest_so_far = t_max
        rec = None

        for object in self.objects:
            temp_rec = object.hit(r, t_min, closest_so_far)
            if temp_rec:
                closest_so_far = temp_rec.t
                rec = temp_rec
        
        return rec
        
    def pdf_value(self, origin: Vec3, v: Vec3) -> float:
        weight = 1.0 / len(self.objects)
        sum_pdf = 0.0
        for obj in self.objects:
            sum_pdf += weight * obj.pdf_value(origin, v)
        return sum_pdf

    def random(self, origin: Vec3) -> Vec3:
        if not self.objects:
             return Vec3([1, 0, 0])
        int_size = len(self.objects)
        return self.objects[random.randint(0, int_size-1)].random(origin)
