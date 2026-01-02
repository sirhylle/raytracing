import numpy as np
import math

def translate(x, y, z):
    """Matrice de Translation"""
    m = np.identity(4, dtype=np.float32)
    m[0, 3] = x
    m[1, 3] = y
    m[2, 3] = z
    return m

def scale(x, y, z):
    """Matrice de Scale (Mise à l'échelle)"""
    m = np.identity(4, dtype=np.float32)
    m[0, 0] = x
    m[1, 1] = y
    m[2, 2] = z
    return m

def rotate_y(angle_degrees):
    """Rotation autour de l'axe Y (Haut)"""
    rad = math.radians(angle_degrees)
    c = math.cos(rad)
    s = math.sin(rad)
    m = np.identity(4, dtype=np.float32)
    m[0, 0] = c
    m[0, 2] = s
    m[2, 0] = -s
    m[2, 2] = c
    return m

def rotate_x(angle_degrees):
    """Rotation autour de l'axe X"""
    rad = math.radians(angle_degrees)
    c = math.cos(rad)
    s = math.sin(rad)
    m = np.identity(4, dtype=np.float32)
    m[1, 1] = c
    m[1, 2] = -s
    m[2, 1] = s
    m[2, 2] = c
    return m

def rotate_z(angle_degrees):
    """Rotation autour de l'axe Z"""
    rad = math.radians(angle_degrees)
    c = math.cos(rad)
    s = math.sin(rad)
    m = np.identity(4, dtype=np.float32)
    m[0, 0] = c
    m[0, 1] = -s
    m[1, 0] = s
    m[1, 1] = c
    return m