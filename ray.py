import numpy as np
from vec3 import Vec3, point3, vec3

class Ray:
    def __init__(self, origin: Vec3, direction: Vec3, time: float = 0.0):
        self.orig = origin
        self.dir = direction
        self.tm = time

    @property
    def origin(self) -> Vec3:
        return self.orig

    @property
    def direction(self) -> Vec3:
        return self.dir
    
    def at(self, t: float) -> Vec3:
        return self.orig + t * self.dir
