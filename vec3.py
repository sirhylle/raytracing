import numpy as np
import math

# Using simple numpy arrays for vec3
# Type alias for clarity (though Python doesn't enforce it)
Vec3 = np.ndarray 

def vec3(x, y, z) -> Vec3:
    return np.array([x, y, z], dtype=np.float32)

def point3(x, y, z) -> Vec3:
    return np.array([x, y, z], dtype=np.float32)

def color(r, g, b) -> Vec3:
    return np.array([r, g, b], dtype=np.float32)

def length_squared(v: Vec3) -> float:
    return np.dot(v, v)

def length(v: Vec3) -> float:
    return np.linalg.norm(v)

def unit_vector(v: Vec3) -> Vec3:
    return v / length(v)

def dot(u: Vec3, v: Vec3) -> float:
    return np.dot(u, v)

def cross(u: Vec3, v: Vec3) -> Vec3:
    return np.cross(u, v)

def random_vec3(min_val=0.0, max_val=1.0) -> Vec3:
    return np.random.uniform(min_val, max_val, 3)

def random_in_unit_sphere() -> Vec3:
    while True:
        p = random_vec3(-1, 1)
        if length_squared(p) < 1:
            return p

def random_unit_vector() -> Vec3:
    return unit_vector(random_in_unit_sphere())

def random_on_hemisphere(normal: Vec3) -> Vec3:
    on_unit_sphere = random_unit_vector()
    if dot(on_unit_sphere, normal) > 0.0:
        return on_unit_sphere
    else:
        return -on_unit_sphere

def reflect(v: Vec3, n: Vec3) -> Vec3:
    return v - 2 * dot(v, n) * n

def refract(uv: Vec3, n: Vec3, etai_over_etat: float) -> Vec3:
    cos_theta = min(dot(-uv, n), 1.0)
    r_out_perp = etai_over_etat * (uv + cos_theta * n)
    r_out_parallel = -math.sqrt(abs(1.0 - length_squared(r_out_perp))) * n
    return r_out_perp + r_out_parallel

def random_cosine_direction() -> Vec3:
    r1 = np.random.rand()
    r2 = np.random.rand()
    phi = 2 * np.pi * r1
    x = math.cos(phi) * math.sqrt(r2)
    y = math.sin(phi) * math.sqrt(r2)
    z = math.sqrt(1 - r2)
    return vec3(x, y, z)

def random_in_unit_disk() -> Vec3:
    while True:
        p = vec3(np.random.uniform(-1,1), np.random.uniform(-1,1), 0)
        if length_squared(p) < 1:
            return p

def near_zero(v: Vec3) -> bool:
    s = 1e-8
    return (abs(v[0]) < s) and (abs(v[1]) < s) and (abs(v[2]) < s)
