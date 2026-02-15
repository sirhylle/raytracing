#pragma once

// ===============================================================================================
// MODULE: GEOMETRY
// ===============================================================================================
//
// DESCRIPTION:
//   This file defines the fundamental geometric primitives used in the ray
//   tracer:
//   - Sphere : Canonical analytical sphere.
//   - Quad   : Parallelogram/Rectangle (useful for area lights & Cornell Box
//   walls).
//   - Triangle: Basic building block for meshes.
//   - HittableList: A container to group multiple objects.
//
// KEY CONCEPTS:
//   - Ray-Object Intersection: Each primitive implements 'hit()' to solve the
//   geometric equation
//     t such that Ray(t) intersects the surface.
//   - Bounding Box (AABB): Computed for each primitive to build the BVH
//   acceleration structure.
//   - PDF (Probability Density Function): Used for Importance Sampling (Next
//   Event Estimation).
//     It allows the renderer to ask "What is the probability that a random ray
//     hits this object?" and "How do I generate a random direction towards this
//     object?".
//
// ===============================================================================================

#include "common.h"
#include "hittable.h"
#include "materials.h" // Nécessaire car les objets possèdent un Material

#include <algorithm>
#include <memory>
#include <vector>

// ===============================================================================================
// CONTAINER : LISTE D'OBJETS (HittableList)
// ===============================================================================================

class HittableList : public Hittable {
public:
  std::vector<std::shared_ptr<Hittable>>
      owned_objects; // Propriétaire des objets (Smart Pointers)
  std::vector<Hittable *> raw_objects; // Accès rapide pour la boucle de rendu

  HittableList() {}

  void add(std::shared_ptr<Hittable> object) {
    owned_objects.push_back(object);
    raw_objects.push_back(object.get());
  }

  void clear() {
    owned_objects.clear();
    raw_objects.clear();
  }

  // Parcours de la liste : On cherche l'intersection la plus proche
  virtual bool hit(const Ray &r, Real t_min, Real t_max,
                   HitRecord &rec) const override {
    HitRecord temp_rec;
    bool hit_anything = false;
    auto closest_so_far = t_max;

    for (const auto *object : raw_objects) {
      if (object->hit(r, t_min, closest_so_far, temp_rec)) {
        hit_anything = true;
        closest_so_far = temp_rec.t;
        rec = temp_rec;
      }
    }
    return hit_anything;
  }

  virtual bool bounding_box(AABB &output_box) const override {
    if (raw_objects.empty())
      return false;

    AABB temp_box;
    bool first_box = true;

    for (const auto *object : raw_objects) {
      if (!object->bounding_box(temp_box))
        return false;
      output_box = first_box ? temp_box : surrounding_box(output_box, temp_box);
      first_box = false;
    }
    return true;
  }

  // PDF pour l'échantillonnage de lumière (choix aléatoire d'un objet dans la
  // liste)
  virtual Real pdf_value(const Vec3 &o, const Vec3 &v) const override {
    if (raw_objects.empty())
      return 0.0f;
    auto weight = 1.0f / raw_objects.size();
    Real sum = 0;
    for (const auto *object : raw_objects)
      sum += weight * object->pdf_value(o, v);
    return sum;
  }

  virtual Vec3 random(const Vec3 &o, Sampler &sampler) const override {
    auto list_size = raw_objects.size();
    if (list_size == 0)
      return Vec3(1, 0, 0);
    // Use sampler for index selection
    size_t random_index =
        static_cast<size_t>(sampler.get_1d() * (list_size - 1));
    return raw_objects[random_index]->random(o, sampler);
  }
};

// ===============================================================================================
// SPHÈRE
// ===============================================================================================

class Sphere : public Hittable {
public:
  Vec3 center;
  Real radius;
  std::shared_ptr<Material> mat_ptr;

  Sphere(Vec3 cen, Real r, std::shared_ptr<Material> m)
      : center(cen), radius(r), mat_ptr(m) {};

  // ---------------------------------------------------------------------------------------------
  // ALGORITHM: RAY-SPHERE INTERSECTION
  // ---------------------------------------------------------------------------------------------
  // We solve the quadratic equation derived from substituting the ray equation
  // P(t) = A + t*b into the sphere equation (P - C) . (P - C) = r^2.
  //
  // resulting in: t^2(b.b) + 2t(b.(A-C)) + ((A-C).(A-C) - r^2) = 0
  // which is in the form: a*t^2 + half_b*2*t + c = 0
  //
  // We check the discriminant (delta = half_b^2 - a*c).
  // If delta < 0, no real roots (ray misses).
  // If delta >= 0, we check the two roots (entry and exit points).
  // ---------------------------------------------------------------------------------------------

  virtual bool hit(const Ray &r, Real t_min, Real t_max,
                   HitRecord &rec) const override {
    Vec3 oc = r.orig - center;
    auto a = r.dir.length_squared();
    auto half_b = dot(oc, r.dir);
    auto c = oc.length_squared() - radius * radius;

    auto discriminant = half_b * half_b - a * c;
    if (discriminant < 0)
      return false;
    auto sqrtd = std::sqrt(discriminant);

    // On cherche la racine la plus proche dans l'intervalle [t_min, t_max]
    auto root = (-half_b - sqrtd) / a;
    if (root <= t_min || t_max <= root) {
      root = (-half_b + sqrtd) / a;
      if (root <= t_min || t_max <= root)
        return false;
    }

    rec.t = root;
    rec.p = r.at(rec.t);
    Vec3 outward_normal = (rec.p - center) / radius;
    rec.set_face_normal(r, outward_normal);

    // Calcul UV sphériques
    auto theta = std::acos(-outward_normal.y());
    auto phi = std::atan2(-outward_normal.z(), outward_normal.x()) + PI;
    rec.u = phi / (2 * PI);
    rec.v = theta / PI;
    rec.mat_ptr = mat_ptr.get();

    return true;
  }

  virtual bool bounding_box(AABB &output_box) const override {
    output_box = AABB(center - Vec3(radius, radius, radius),
                      center + Vec3(radius, radius, radius));
    return true;
  }

  bool is_opaque() const override { return !mat_ptr->is_transparent(); }

  // ---------------------------------------------------------------------------------------------
  // ALGORITHM: PROBABILITY DENSITY FUNCTION (PDF) & SAMPLING
  // ---------------------------------------------------------------------------------------------
  // Essential for Importance Sampling (picking a light source intelligently).
  //
  // pdf_value: Returns the probability density of choosing a direction 'v' that
  // hits this sphere
  //            assuming a uniform sampling over the solid angle subtended by
  //            the sphere. Formula = 1 / SolidAngle.
  //
  // random:    Generates a random direction vector from 'o' aiming continuously
  // at the sphere.
  //            It constructs a local coordinate system (ONB) facing the sphere
  //            center and samples a cone uniformly.
  // ---------------------------------------------------------------------------------------------

  // PDF : Probabilité de toucher la sphère depuis le point o
  virtual Real pdf_value(const Vec3 &o, const Vec3 &v) const override {
    HitRecord rec;
    if (!this->hit(Ray(o, v), 0.001f, INFINITY_REAL, rec))
      return 0;

    auto cos_theta_max =
        std::sqrt(1.0f - radius * radius / (center - o).length_squared());
    auto solid_angle = 2 * PI * (1.0f - cos_theta_max);
    return 1.0f / solid_angle;
  }

  // Random : Génère une direction vers la sphère (Cone Sampling)
  virtual Vec3 random(const Vec3 &o, Sampler &sampler) const override {
    Vec3 direction = center - o;
    auto distance_squared = direction.length_squared();
    auto uvw =
        Onb(unit_vector(direction)); // Onb (Orthonormal Basis) local inline
    return uvw.local(random_to_sphere(radius, distance_squared, sampler));
  }

private:
  // Helpers privés pour le sampling sphérique
  static Vec3 random_to_sphere(Real radius, Real distance_squared,
                               Sampler &sampler) {
    auto r1 = sampler.get_1d();
    auto r2 = sampler.get_1d();
    auto z = 1.0f +
             r2 * (std::sqrt(1.0f - radius * radius / distance_squared) - 1.0f);
    auto phi = 2 * PI * r1;
    auto x = std::cos(phi) * std::sqrt(1.0f - z * z);
    auto y = std::sin(phi) * std::sqrt(1.0f - z * z);
    return Vec3(x, y, z);
  }

  // Petite structure ONB locale pour simplifier 'random'
  struct Onb {
    Vec3 axis[3];
    Onb(const Vec3 &n) {
      axis[2] = unit_vector(n);
      Vec3 a = (std::abs(axis[2].x()) > 0.9f) ? Vec3(0, 1, 0) : Vec3(1, 0, 0);
      axis[1] = unit_vector(cross(axis[2], a));
      axis[0] = cross(axis[2], axis[1]); // Correction ordre cross product
    }
    Vec3 local(const Vec3 &a) const {
      return a.x() * axis[0] + a.y() * axis[1] + a.z() * axis[2];
    }
  };
};

// ===============================================================================================
// QUAD (Rectangle / Parallélogramme)
// ===============================================================================================

class Quad : public Hittable {
public:
  Vec3 Q, u, v;
  Vec3 w, normal;
  Real D, area;
  std::shared_ptr<Material> mat_ptr;

  Quad(Vec3 _Q, Vec3 _u, Vec3 _v, std::shared_ptr<Material> m)
      : Q(_Q), u(_u), v(_v), mat_ptr(m) {
    auto n = cross(u, v);
    normal = unit_vector(n);
    D = dot(normal, Q);
    w = n / dot(n, n);
    area = n.length();
  }

  // ---------------------------------------------------------------------------------------------
  // ALGORITHM: RAY-QUAD INTERSECTION
  // ---------------------------------------------------------------------------------------------
  // 1. Plane Intersection:
  //    Check if ray is parallel to the plane (dot product approx 0).
  //    Compute 't' for the plane defined by point Q and normal 'n'.
  //
  // 2. Planar Coordinates Check (Barycentric-like):
  //    Once we have the hit point P on the infinite plane, we project vector (P
  //    - Q) onto the basis vectors (u, v) using the precomputed helper 'w' (w =
  //    n / length(n)^2). alpha = dot(w, cross(P-Q, v)) beta  = dot(w, cross(u,
  //    P-Q))
  //
  //    If 0 <= alpha <= 1 and 0 <= beta <= 1, the point is inside the
  //    parallelogram.
  // ---------------------------------------------------------------------------------------------

  virtual bool hit(const Ray &r, Real t_min, Real t_max,
                   HitRecord &rec) const override {
    auto denom = dot(normal, r.dir);
    if (std::fabs(denom) < 1e-6f)
      return false; // Parallèle au plan

    auto t = (D - dot(normal, r.orig)) / denom;
    if (t < t_min || t > t_max)
      return false;

    auto intersection = r.at(t);
    Vec3 planar_hitpt_vector = intersection - Q;
    auto alpha = dot(w, cross(planar_hitpt_vector, v));
    auto beta = dot(w, cross(u, planar_hitpt_vector));

    // Vérification qu'on est DANS le rectangle (0..1)
    if (!((0 <= alpha && alpha <= 1) && (0 <= beta && beta <= 1)))
      return false;

    rec.u = alpha;
    rec.v = beta;
    rec.t = t;
    rec.p = intersection;
    rec.mat_ptr = mat_ptr.get();
    rec.set_face_normal(r, normal);
    return true;
  }

  virtual bool bounding_box(AABB &output_box) const override {
    auto min_v = Vec3(
        std::fmin(Q.x(), std::fmin((Q + u).x(),
                                   std::fmin((Q + v).x(), (Q + u + v).x()))),
        std::fmin(Q.y(), std::fmin((Q + u).y(),
                                   std::fmin((Q + v).y(), (Q + u + v).y()))),
        std::fmin(Q.z(), std::fmin((Q + u).z(),
                                   std::fmin((Q + v).z(), (Q + u + v).z()))));
    auto max_v = Vec3(
        std::fmax(Q.x(), std::fmax((Q + u).x(),
                                   std::fmax((Q + v).x(), (Q + u + v).x()))),
        std::fmax(Q.y(), std::fmax((Q + u).y(),
                                   std::fmax((Q + v).y(), (Q + u + v).y()))),
        std::fmax(Q.z(), std::fmax((Q + u).z(),
                                   std::fmax((Q + v).z(), (Q + u + v).z()))));
    // Padding pour éviter les boites plates
    output_box = AABB(min_v - Vec3(0.001, 0.001, 0.001),
                      max_v + Vec3(0.001, 0.001, 0.001));
    return true;
  }

  virtual Real pdf_value(const Vec3 &o, const Vec3 &v) const override {
    HitRecord rec;
    if (!this->hit(Ray(o, v), 0.001f, INFINITY_REAL, rec))
      return 0;
    auto distance_squared = rec.t * rec.t * v.length_squared();
    auto cosine = std::fabs(dot(v, rec.normal) / v.length());
    return distance_squared / (cosine * area);
  }

  virtual Vec3 random(const Vec3 &o, Sampler &sampler) const override {
    Vec3 uv = sampler.get_2d();
    auto p = Q + (uv.x() * u) + (uv.y() * v);
    return p - o;
  }

  bool is_opaque() const override { return !mat_ptr->is_transparent(); }
};

// ===============================================================================================
// TRIANGLE
// ===============================================================================================

class Triangle : public Hittable {
public:
  Vec3 v0, v1, v2;
  Vec3 n0, n1, n2;
  std::shared_ptr<Material> mat_ptr;

  Triangle(Vec3 _v0, Vec3 _v1, Vec3 _v2, Vec3 _n0, Vec3 _n1, Vec3 _n2,
           std::shared_ptr<Material> m)
      : v0(_v0), v1(_v1), v2(_v2), n0(_n0), n1(_n1), n2(_n2), mat_ptr(m) {}

  // ---------------------------------------------------------------------------------------------
  // ALGORITHM: MÖLLER-TRUMBORE
  // ---------------------------------------------------------------------------------------------
  // A fast, efficient ray-triangle intersection algorithm that does not require
  // precomputing the plane equation.
  //
  // It solves constraints for barycentric coordinates (u, v):
  // P(t) = (1 - u - v)*V0 + u*V1 + v*V2
  //
  // If we find u, v such that u >= 0, v >= 0 and u + v <= 1, the intersection
  // is valid. We also interpolate the vertex normals (n0, n1, n2) using these
  // coordinates for smooth shading.
  // ---------------------------------------------------------------------------------------------

  virtual bool hit(const Ray &r, Real t_min, Real t_max,
                   HitRecord &rec) const override {
    // Algorithme de Möller–Trumbore
    const float EPSILON = 1e-6f;
    Vec3 edge1 = v1 - v0;
    Vec3 edge2 = v2 - v0;
    Vec3 h = cross(r.dir, edge2);
    Real a = dot(edge1, h);

    if (a > -EPSILON && a < EPSILON)
      return false;

    Real f = 1.0f / a;
    Vec3 s = r.orig - v0;
    Real u = f * dot(s, h);
    if (u < 0.0f || u > 1.0f)
      return false;

    Vec3 q = cross(s, edge1);
    Real v = f * dot(r.dir, q);
    if (v < 0.0f || u + v > 1.0f)
      return false;

    Real t = f * dot(edge2, q);
    if (t > t_min && t < t_max) {
      rec.t = t;
      rec.p = r.at(t);
      // Interpolation Phong des normales
      Vec3 smooth_normal = (1.0f - u - v) * n0 + u * n1 + v * n2;
      rec.set_face_normal(r, unit_vector(smooth_normal));
      rec.mat_ptr = mat_ptr.get();
      rec.u = u;
      rec.v = v;
      return true;
    }
    return false;
  }

  virtual bool bounding_box(AABB &output_box) const override {
    Real min_x = std::min({v0.x(), v1.x(), v2.x()});
    Real min_y = std::min({v0.y(), v1.y(), v2.y()});
    Real min_z = std::min({v0.z(), v1.z(), v2.z()});

    Real max_x = std::max({v0.x(), v1.x(), v2.x()});
    Real max_y = std::max({v0.y(), v1.y(), v2.y()});
    Real max_z = std::max({v0.z(), v1.z(), v2.z()});

    output_box = AABB(Vec3(min_x - 0.001f, min_y - 0.001f, min_z - 0.001f),
                      Vec3(max_x + 0.001f, max_y + 0.001f, max_z + 0.001f));
    return true;
  }

  bool is_opaque() const override { return !mat_ptr->is_transparent(); }
};