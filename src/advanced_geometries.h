#pragma once

#include "common.h"
#include "hittable.h"
#include "materials.h"

// ===============================================================================================
// MODULE: ADVANCED GEOMETRIES
// ===============================================================================================
// Adds analytic primitives: Cylinder, Cone.
// These are defined as "Unit" primitives (radius 1, height 1) centered at the
// origin, intended to be transformed via Instances.

// -----------------------------------------------------------------------------------------------
// CYLINDER (Capped)
// -----------------------------------------------------------------------------------------------
// Aligned along Y axis. Radius 1. y range [-0.5, 0.5].
class Cylinder : public Hittable {
public:
  std::shared_ptr<Material> mat_ptr;
  Real radius;
  Real y_min;
  Real y_max;

  Cylinder(std::shared_ptr<Material> m)
      : mat_ptr(m), radius(1.0f), y_min(-0.5f), y_max(0.5f) {}

  virtual bool hit(const Ray &r, Real t_min, Real t_max,
                   HitRecord &rec) const override {
    Vec3 oc = r.orig;
    Vec3 dir = r.dir;
    bool hit_any = false;

    // 1. Body Intersection
    Real a = dir.x() * dir.x() + dir.z() * dir.z();
    if (std::abs(a) > 1e-6f) {
      Real half_b = oc.x() * dir.x() + oc.z() * dir.z();
      Real c = oc.x() * oc.x() + oc.z() * oc.z() - radius * radius;
      Real discriminant = half_b * half_b - a * c;
      if (discriminant >= 0) {
        Real sqrtd = std::sqrt(discriminant);

        auto check_body = [&](Real t) -> bool {
          if (t > t_min && t < t_max) {
            Real y = oc.y() + t * dir.y();
            if (y >= y_min && y <= y_max) {
              rec.t = t;
              rec.p = r.at(t);
              rec.normal = Vec3(rec.p.x(), 0, rec.p.z()) / radius;
              rec.set_face_normal(r, rec.normal);

              Real phi = std::atan2(rec.normal.x(), rec.normal.z());
              if (phi < 0)
                phi += 2 * PI;
              rec.u = phi / (2 * PI);
              rec.v = (y - y_min) / (y_max - y_min);
              rec.mat_ptr = mat_ptr.get();
              return true;
            }
          }
          return false;
        };

        // Check both roots
        // We must update t_max if we find a closer hit
        if (check_body((-half_b - sqrtd) / a)) {
          hit_any = true;
          t_max = rec.t;
        }
        if (check_body((-half_b + sqrtd) / a)) {
          hit_any = true;
          t_max = rec.t;
        }
      }
    }

    // 2. Caps Intersection
    auto check_cap = [&](Real y_cap, bool is_top) -> bool {
      if (std::abs(dir.y()) < 1e-6f)
        return false;
      Real t = (y_cap - oc.y()) / dir.y();
      if (t < t_min || t > t_max)
        return false;

      Real x = oc.x() + t * dir.x();
      Real z = oc.z() + t * dir.z();
      if ((x * x + z * z) <= radius * radius) {
        rec.t = t;
        rec.p = r.at(t);
        rec.normal = Vec3(0, is_top ? 1.0f : -1.0f, 0);
        rec.set_face_normal(r, rec.normal);
        rec.mat_ptr = mat_ptr.get();
        rec.u = (x / radius + 1.0f) * 0.5f;
        rec.v = (z / radius + 1.0f) * 0.5f;
        return true;
      }
      return false;
    };

    if (check_cap(y_max, true)) {
      hit_any = true;
      t_max = rec.t;
    }
    if (check_cap(y_min, false)) {
      hit_any = true;
      t_max = rec.t;
    }

    return hit_any;
  }

  virtual bool bounding_box(AABB &output_box) const override {
    output_box =
        AABB(Vec3(-radius, y_min, -radius), Vec3(radius, y_max, radius));
    return true;
  }
};

// -----------------------------------------------------------------------------------------------
// CONE (Capped)
// -----------------------------------------------------------------------------------------------
class Cone : public Hittable {
public:
  std::shared_ptr<Material> mat_ptr;
  Real radius;
  Real height;
  Real y_min;
  Real y_max;

  Cone(std::shared_ptr<Material> m)
      : mat_ptr(m), radius(1.0f), height(1.0f), y_min(-0.5f), y_max(0.5f) {}

  virtual bool hit(const Ray &r, Real t_min, Real t_max,
                   HitRecord &rec) const override {
    Real k = radius / height;
    Real k2 = k * k;
    Real y_tip = y_max;
    Vec3 oc = r.orig;
    Vec3 dir = r.dir;
    bool hit_any = false;

    // 1. Body Intersection
    Real dir_x = dir.x(), dir_y = dir.y(), dir_z = dir.z();
    Real oc_x = oc.x(), oc_y = oc.y(), oc_z = oc.z();

    Real A = dir_x * dir_x + dir_z * dir_z - k2 * dir_y * dir_y;
    Real B = 2 * (oc_x * dir_x + oc_z * dir_z + k2 * (y_tip - oc_y) * dir_y);
    Real C = oc_x * oc_x + oc_z * oc_z - k2 * (y_tip - oc_y) * (y_tip - oc_y);

    Real discriminant = B * B - 4 * A * C;
    if (discriminant >= 0) {
      Real sqrtd = std::sqrt(discriminant);

      auto check_root = [&](Real t) -> bool {
        if (t < t_min || t > t_max)
          return false;
        Real y = oc_y + t * dir_y;
        if (y >= y_min && y <= y_max) {
          rec.t = t;
          rec.p = r.at(t);
          rec.normal = Vec3(2 * rec.p.x(), 2 * k2 * (y_tip - y), 2 * rec.p.z());
          rec.normal = unit_vector(rec.normal);
          rec.set_face_normal(r, rec.normal);
          rec.mat_ptr = mat_ptr.get();

          Real phi = std::atan2(rec.p.x(), rec.p.z());
          if (phi < 0)
            phi += 2 * PI;
          rec.u = phi / (2 * PI);
          rec.v = (y - y_min) / height;
          return true;
        }
        return false;
      };

      if (check_root((-B - sqrtd) / (2 * A))) {
        hit_any = true;
        t_max = rec.t;
      }
      if (check_root((-B + sqrtd) / (2 * A))) {
        hit_any = true;
        t_max = rec.t;
      }
    }

    // 2. Cap Intersection (Base at y_min)
    if (std::abs(dir_y) > 1e-6f) {
      Real t = (y_min - oc_y) / dir_y;
      if (t > t_min && t < t_max) {
        Real x = oc_x + t * dir_x;
        Real z = oc_z + t * dir_z;
        if (x * x + z * z <= radius * radius) {
          rec.t = t;
          rec.p = r.at(t);
          rec.normal = Vec3(0, -1, 0);
          rec.set_face_normal(r, rec.normal);
          rec.mat_ptr = mat_ptr.get();
          rec.u = (x / radius + 1) * 0.5f;
          rec.v = (z / radius + 1) * 0.5f;

          hit_any = true;
          t_max = rec.t;
        }
      }
    }

    return hit_any;
  }

  virtual bool bounding_box(AABB &output_box) const override {
    output_box =
        AABB(Vec3(-radius, y_min, -radius), Vec3(radius, y_max, radius));
    return true;
  }
};
