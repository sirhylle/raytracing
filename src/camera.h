#pragma once

#include "common.h"
#include <cmath>

class Camera {
public:
  Vec3 origin;
  Vec3 lower_left_corner;
  Vec3 horizontal;
  Vec3 vertical;
  Vec3 u, v, w;
  Real lens_radius;
  Real vfov; // On garde ces params pour le debug ou l'UI si besoin
  Real focus_dist;

  Camera(Vec3 lookfrom, Vec3 lookat, Vec3 vup, Real vfov, Real aspect_ratio,
         Real aperture, Real focus_dist)
      : vfov(vfov), focus_dist(focus_dist) {
    auto theta = vfov * PI / 180.0f;
    auto h = std::tan(theta / 2);
    auto viewport_height = 2.0f * h;
    auto viewport_width = aspect_ratio * viewport_height;

    w = unit_vector(lookfrom - lookat);
    u = unit_vector(cross(vup, w));
    v = cross(w, u);

    origin = lookfrom;
    horizontal = focus_dist * viewport_width * u;
    vertical = focus_dist * viewport_height * v;
    lower_left_corner = origin - horizontal / 2 - vertical / 2 - focus_dist * w;

    lens_radius = aperture / 2;
  }

  Ray get_ray(Real s, Real t) const {
    Vec3 rd = lens_radius * random_in_unit_disk();
    Vec3 offset = u * rd.x() + v * rd.y();

    // Rayon partant de la lentille vers le plan focal
    return Ray(origin + offset,
               lower_left_corner + s * horizontal + t * vertical - origin -
                   offset,
               random_real());
  }
};