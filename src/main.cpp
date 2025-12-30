#include <nanobind/nanobind.h>
#include <nanobind/ndarray.h>
#include <nanobind/stl/shared_ptr.h>
#include <nanobind/stl/string.h>
#include <nanobind/stl/vector.h>

#include <algorithm>
#include <atomic>
#include <cmath>
#include <iostream>
#include <limits>
#include <memory>
#include <omp.h>
#include <optional>
#include <random>
#include <stdexcept>
#include <string>
#include <vector>


namespace nb = nanobind;
using namespace nb::literals;

// ===============================================================================================
// CORE MATH
// ===============================================================================================

// --- MODIFICATION 1 : Passage en float ---
using Real = float;
const Real PI = 3.1415926535897932385f; // Ajout du suffixe 'f'

struct Vec3 {
  Real e[3];

  Vec3() : e{0, 0, 0} {}
  Vec3(Real e0, Real e1, Real e2) : e{e0, e1, e2} {}

  Real x() const { return e[0]; }
  Real y() const { return e[1]; }
  Real z() const { return e[2]; }

  Vec3 operator-() const { return Vec3(-e[0], -e[1], -e[2]); }
  Real operator[](int i) const { return e[i]; }
  Real &operator[](int i) { return e[i]; }

  Vec3 &operator+=(const Vec3 &v) {
    e[0] += v.e[0];
    e[1] += v.e[1];
    e[2] += v.e[2];
    return *this;
  }

  Vec3 &operator*=(Real t) {
    e[0] *= t;
    e[1] *= t;
    e[2] *= t;
    return *this;
  }

  // Utilisation de 1.0f pour éviter la promotion implicite en double
  Vec3 &operator/=(Real t) { return *this *= (1.0f / t); }

  Real length_squared() const {
    return e[0] * e[0] + e[1] * e[1] + e[2] * e[2];
  }

  Real length() const { return std::sqrt(length_squared()); }
};

inline Vec3 operator+(const Vec3 &u, const Vec3 &v) {
  return Vec3(u.e[0] + v.e[0], u.e[1] + v.e[1], u.e[2] + v.e[2]);
}

inline Vec3 operator-(const Vec3 &u, const Vec3 &v) {
  return Vec3(u.e[0] - v.e[0], u.e[1] - v.e[1], u.e[2] - v.e[2]);
}

inline Vec3 operator*(const Vec3 &u, const Vec3 &v) {
  return Vec3(u.e[0] * v.e[0], u.e[1] * v.e[1], u.e[2] * v.e[2]);
}

inline Vec3 operator*(Real t, const Vec3 &v) {
  return Vec3(t * v.e[0], t * v.e[1], t * v.e[2]);
}

inline Vec3 operator*(const Vec3 &v, Real t) { return t * v; }

inline Vec3 operator/(const Vec3 &v, Real t) { return (1.0f / t) * v; }

inline Real dot(const Vec3 &u, const Vec3 &v) {
  return u.e[0] * v.e[0] + u.e[1] * v.e[1] + u.e[2] * v.e[2];
}

inline Vec3 cross(const Vec3 &u, const Vec3 &v) {
  return Vec3(u.e[1] * v.e[2] - u.e[2] * v.e[1],
              u.e[2] * v.e[0] - u.e[0] * v.e[2],
              u.e[0] * v.e[1] - u.e[1] * v.e[0]);
}

inline Vec3 unit_vector(const Vec3 &v) { return v / v.length(); }

// Random Utils
thread_local std::mt19937 generator{std::random_device{}()};
// Distribution reste correcte, elle templatera sur float
thread_local std::uniform_real_distribution<Real> distribution(0.0f, 1.0f);

inline Real random_real() { return distribution(generator); }

inline Real random_real(Real min, Real max) {
  return min + (max - min) * random_real();
}

inline Vec3 random_vec3() {
  return Vec3(random_real(), random_real(), random_real());
}

inline Vec3 random_vec3(Real min, Real max) {
  return Vec3(random_real(min, max), random_real(min, max),
              random_real(min, max));
}

inline Vec3 random_in_unit_sphere() {
  while (true) {
    auto p = random_vec3(-1, 1);
    if (p.length_squared() < 1)
      return p;
  }
}

inline Vec3 random_unit_vector() {
  return unit_vector(random_in_unit_sphere());
}

inline Vec3 random_in_unit_disk() {
  while (true) {
    auto p = Vec3(random_real(-1, 1), random_real(-1, 1), 0);
    if (p.length_squared() < 1)
      return p;
  }
}

inline Vec3 reflect(const Vec3 &v, const Vec3 &n) {
  return v - 2 * dot(v, n) * n;
}

inline Vec3 refract(const Vec3 &uv, const Vec3 &n, Real etai_over_etat) {
  auto cos_theta = std::fmin(dot(-uv, n), 1.0f);
  Vec3 r_out_perp = etai_over_etat * (uv + cos_theta * n);
  Vec3 r_out_parallel =
      -std::sqrt(std::fabs(1.0f - r_out_perp.length_squared())) * n;
  return r_out_perp + r_out_parallel;
}

// ===============================================================================================
// RAY & HIT
// ===============================================================================================

struct Ray {
  Vec3 orig;
  Vec3 dir;
  Real tm;
  bool is_shadow;
  bool is_primary;

  Ray() : tm(0), is_shadow(false), is_primary(false) {}
  Ray(const Vec3 &origin, const Vec3 &direction, Real time = 0.0f,
      bool shadow = false, bool primary = false)
      : orig(origin), dir(direction), tm(time), is_shadow(shadow),
        is_primary(primary) {}

  Vec3 at(Real t) const { return orig + t * dir; }
};

class Material;

struct AABB {
  Vec3 min, max;

  AABB() {}
  AABB(const Vec3 &a, const Vec3 &b) : min(a), max(b) {
    // Optionnel : s'assurer que min < max pour éviter des bugs bizarres
  }

  // Méthode "Slab" optimisée sans division (plus rapide)
  bool hit(const Ray &r, Real t_min, Real t_max) const {
    for (int a = 0; a < 3; a++) {
      auto invD = 1.0f / r.dir[a];
      auto t0 = (min[a] - r.orig[a]) * invD;
      auto t1 = (max[a] - r.orig[a]) * invD;
      if (invD < 0.0f)
        std::swap(t0, t1);
      t_min = t0 > t_min ? t0 : t_min;
      t_max = t1 < t_max ? t1 : t_max;
      if (t_max <= t_min)
        return false;
    }
    return true;
  }
};

// Fonction utilitaire pour fusionner deux boîtes
inline AABB surrounding_box(const AABB &box0, const AABB &box1) {
  Vec3 small(std::fmin(box0.min.x(), box1.min.x()),
             std::fmin(box0.min.y(), box1.min.y()),
             std::fmin(box0.min.z(), box1.min.z()));
  Vec3 big(std::fmax(box0.max.x(), box1.max.x()),
           std::fmax(box0.max.y(), box1.max.y()),
           std::fmax(box0.max.z(), box1.max.z()));
  return AABB(small, big);
}

struct HitRecord {
  Vec3 p;
  Vec3 normal;
  Material *mat_ptr;
  Real t;
  Real u;
  Real v;
  bool front_face;

  inline void set_face_normal(const Ray &r, const Vec3 &outward_normal) {
    front_face = dot(r.dir, outward_normal) < 0;
    normal = front_face ? outward_normal : -outward_normal;
  }
};

class Hittable {
public:
  virtual bool hit(const Ray &r, Real t_min, Real t_max,
                   HitRecord &rec) const = 0;
  virtual bool bounding_box(AABB &output_box) const = 0;
  virtual Real pdf_value(const Vec3 &o, const Vec3 &v) const { return 0.0f; }
  virtual Vec3 random(const Vec3 &o) const { return Vec3(1, 0, 0); }
  virtual ~Hittable() = default;
};

// ===============================================================================================
// GEOMETRY
// ===============================================================================================

class Sphere : public Hittable {
public:
  Vec3 center;
  Real radius;
  std::shared_ptr<Material> mat_ptr;

  Sphere(Vec3 cen, Real r, std::shared_ptr<Material> m)
      : center(cen), radius(r), mat_ptr(m) {};

  virtual bool hit(const Ray &r, Real t_min, Real t_max,
                   HitRecord &rec) const override;
  virtual bool bounding_box(AABB &output_box) const override;
  virtual Real pdf_value(const Vec3 &o, const Vec3 &v) const override;
  virtual Vec3 random(const Vec3 &o) const override;
};

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

  virtual bool hit(const Ray &r, Real t_min, Real t_max,
                   HitRecord &rec) const override;
  virtual bool bounding_box(AABB &output_box) const override;
  virtual Real pdf_value(const Vec3 &o, const Vec3 &v) const override;
  virtual Vec3 random(const Vec3 &o) const override;
};

class HittableList : public Hittable {
public:
  std::vector<std::shared_ptr<Hittable>> owned_objects;
  std::vector<Hittable *> raw_objects;

  HittableList() {}
  void add(std::shared_ptr<Hittable> object) {
    owned_objects.push_back(object);
    raw_objects.push_back(object.get());
  }

  virtual bool hit(const Ray &r, Real t_min, Real t_max,
                   HitRecord &rec) const override;
  virtual bool bounding_box(AABB &output_box) const override;
  virtual Real pdf_value(const Vec3 &o, const Vec3 &v) const override;
  virtual Vec3 random(const Vec3 &o) const override;
};

// ===============================================================================================
// MATERIALS
// ===============================================================================================

struct ScatterRecord {
  Ray specular_ray;
  bool is_specular;
  Vec3 attenuation;
};

class Material {
public:
  virtual bool scatter(const Ray &r_in, const HitRecord &rec,
                       ScatterRecord &srec) const {
    return false;
  };

  virtual Real scattering_pdf(const Ray &r_in, const HitRecord &rec,
                              const Ray &scattered) const {
    return 0;
  }

  virtual Vec3 emit(const Ray &r_in, const HitRecord &rec, Real u, Real v,
                    const Vec3 &p) const {
    return Vec3(0, 0, 0);
  }

  virtual bool is_transparent() const { return false; }

  virtual ~Material() = default;
};

class Lambertian : public Material {
public:
  Vec3 albedo;
  Lambertian(const Vec3 &a) : albedo(a) {}

  virtual bool scatter(const Ray &r_in, const HitRecord &rec,
                       ScatterRecord &srec) const override {
    srec.is_specular = false;
    srec.attenuation = albedo;
    srec.specular_ray =
        Ray(rec.p, unit_vector(rec.normal + random_unit_vector()), r_in.tm);
    return true;
  }

  virtual Real scattering_pdf(const Ray &r_in, const HitRecord &rec,
                              const Ray &scattered) const override {
    auto cosine = dot(rec.normal, unit_vector(scattered.dir));
    return cosine < 0 ? 0 : cosine / PI;
  }
};

class LambertianChecker : public Material {
public:
  Vec3 albedo1;
  Vec3 albedo2;
  Real scale;

  LambertianChecker(const Vec3 &a1, const Vec3 &a2, Real s)
      : albedo1(a1), albedo2(a2), scale(s) {}

  virtual bool scatter(const Ray &r_in, const HitRecord &rec,
                       ScatterRecord &srec) const override {
    srec.is_specular = false;

    // --- MODIFICATION : 1e-5f ---
    Real eps = 1e-5f;
    Real sines = std::sin(scale * rec.p.x()) * std::sin(scale * rec.p.y()) *
                 std::sin(scale * rec.p.z());

    if (sines < 0)
      srec.attenuation = albedo1;
    else
      srec.attenuation = albedo2;

    srec.specular_ray =
        Ray(rec.p, unit_vector(rec.normal + random_unit_vector()), r_in.tm);
    return true;
  }

  virtual Real scattering_pdf(const Ray &r_in, const HitRecord &rec,
                              const Ray &scattered) const override {
    auto cosine = dot(rec.normal, unit_vector(scattered.dir));
    return cosine < 0 ? 0 : cosine / PI;
  }
};

class Metal : public Material {
public:
  Vec3 albedo;
  Real fuzz;
  Metal(const Vec3 &a, Real f) : albedo(a), fuzz(f < 1 ? f : 1) {}

  virtual bool scatter(const Ray &r_in, const HitRecord &rec,
                       ScatterRecord &srec) const override {
    Vec3 reflected = reflect(unit_vector(r_in.dir), rec.normal);
    srec.specular_ray =
        Ray(rec.p, reflected + fuzz * random_in_unit_sphere(), r_in.tm);
    srec.attenuation = albedo;
    srec.is_specular = true;
    return (dot(srec.specular_ray.dir, rec.normal) > 0);
  }
};

// Phantom Light: Visible only to Shadow Rays (is_shadow=true),
// Transparent to Camera/Specular rays.
class InvisibleLight : public Material {
public:
  Vec3 emit_color;
  InvisibleLight(const Vec3 &c) : emit_color(c) {}

  virtual bool scatter(const Ray &r_in, const HitRecord &rec,
                       ScatterRecord &srec) const override {
    // Transparent passthrough for non-shadow rays
    srec.is_specular = true;
    // Pass r_in.is_primary to keep background visibility correct
    srec.specular_ray = Ray(rec.p + 0.001f * r_in.dir, r_in.dir, r_in.tm,
                            r_in.is_shadow, r_in.is_primary);

    srec.attenuation = Vec3(1.0f, 1.0f, 1.0f);
    return true;
  }

  virtual Vec3 emit(const Ray &r_in, const HitRecord &rec, Real u, Real v,
                    const Vec3 &p) const override {
    if (r_in.is_shadow) {
      return emit_color;
    }
    return Vec3(0, 0, 0);
  }
};

class Dielectric : public Material {
public:
  Real ir;
  Vec3 tint;

  Dielectric(Real index_of_refraction,
             const Vec3 &tint_color = Vec3(1.0f, 1.0f, 1.0f))
      : ir(index_of_refraction), tint(tint_color) {}

  virtual bool is_transparent() const override { return true; }

  virtual bool scatter(const Ray &r_in, const HitRecord &rec,
                       ScatterRecord &srec) const override {
    srec.attenuation = tint;
    srec.is_specular = true;
    Real refraction_ratio = rec.front_face ? (1.0f / ir) : ir;

    Vec3 unit_direction = unit_vector(r_in.dir);
    Real cos_theta = std::fmin(dot(-unit_direction, rec.normal), 1.0f);
    Real sin_theta = std::sqrt(1.0f - cos_theta * cos_theta);

    bool cannot_refract = refraction_ratio * sin_theta > 1.0f;
    Vec3 direction;

    if (cannot_refract ||
        reflectance(cos_theta, refraction_ratio) > random_real())
      direction = reflect(unit_direction, rec.normal);
    else
      direction = refract(unit_direction, rec.normal, refraction_ratio);

    srec.specular_ray = Ray(rec.p, direction, r_in.tm);
    return true;
  }

  static Real reflectance(Real cosine, Real ref_idx) {
    auto r0 = (1.0f - ref_idx) / (1.0f + ref_idx);
    r0 = r0 * r0;
    return r0 + (1.0f - r0) * std::pow((1.0f - cosine), 5);
  }
};

class Plastic : public Material {
public:
  Vec3 albedo;
  Real ir;
  Real fuzz;

  Plastic(const Vec3 &a, Real index_of_refraction, Real f)
      : albedo(a), ir(index_of_refraction), fuzz(f) {}

  virtual bool scatter(const Ray &r_in, const HitRecord &rec,
                       ScatterRecord &srec) const override {
    // Clearcoat Layer (Fresnel)
    Real refraction_ratio = rec.front_face ? (1.0f / ir) : ir;
    Vec3 unit_direction = unit_vector(r_in.dir);
    Real cos_theta = std::fmin(dot(-unit_direction, rec.normal), 1.0f);

    // Simple Schlick approximation for Fresnel prob
    Real r0 = (1.0f - ir) / (1.0f + ir);
    r0 = r0 * r0;
    Real reflect_prob = r0 + (1.0f - r0) * std::pow((1.0f - cos_theta), 5);

    if (random_real() < reflect_prob) {
      // Specular Reflection (White Highlight)
      Vec3 reflected = reflect(unit_direction, rec.normal);
      srec.is_specular = true;
      srec.specular_ray =
          Ray(rec.p, reflected + fuzz * random_in_unit_sphere(), r_in.tm);
      srec.attenuation = Vec3(1.0f, 1.0f, 1.0f); // White highlight
      return true;
    } else {
      // Diffuse Base
      // Treat as specular to avoid PDF issues for now (Path Tracing handles it
      // fine)
      srec.is_specular = true;
      srec.attenuation = albedo;
      // Generate diffuse ray manually
      srec.specular_ray =
          Ray(rec.p, unit_vector(rec.normal + random_unit_vector()), r_in.tm);
      return true;
    }
  }

  // Support scattering_pdf for the diffuse part
  virtual Real scattering_pdf(const Ray &r_in, const HitRecord &rec,
                              const Ray &scattered) const override {
    auto cosine = dot(rec.normal, unit_vector(scattered.dir));
    return cosine < 0 ? 0 : cosine / PI;
  }
};

class DiffuseLight : public Material {
public:
  Vec3 emit_color;
  DiffuseLight(const Vec3 &c) : emit_color(c) {}

  virtual bool scatter(const Ray &r_in, const HitRecord &rec,
                       ScatterRecord &srec) const override {
    return false;
  }

  virtual Vec3 emit(const Ray &r_in, const HitRecord &rec, Real u, Real v,
                    const Vec3 &p) const override {
    if (rec.front_face)
      return emit_color;
    return Vec3(0, 0, 0);
  }
};

// ===============================================================================================
// IMPLEMENTATION (METHOD BODIES)
// ===============================================================================================

bool Sphere::hit(const Ray &r, Real t_min, Real t_max, HitRecord &rec) const {
  Vec3 oc = r.orig - center;
  auto a = r.dir.length_squared();
  auto half_b = dot(oc, r.dir);
  auto c = oc.length_squared() - radius * radius;

  auto discriminant = half_b * half_b - a * c;
  if (discriminant < 0)
    return false;
  auto sqrtd = std::sqrt(discriminant);

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

  // UV
  auto theta = std::acos(-outward_normal.y());
  auto phi = std::atan2(-outward_normal.z(), outward_normal.x()) + PI;
  rec.u = phi / (2 * PI);
  rec.v = theta / PI;

  rec.mat_ptr = mat_ptr.get();
  return true;
}

bool Sphere::bounding_box(AABB &output_box) const {
  output_box = AABB(center - Vec3(radius, radius, radius),
                    center + Vec3(radius, radius, radius));
  return true;
}

Real Sphere::pdf_value(const Vec3 &o, const Vec3 &v) const {
  HitRecord rec;
  // --- MODIFICATION : Epsilon 1e-4f ---
  if (!this->hit(Ray(o, v), 0.001f, std::numeric_limits<Real>::infinity(), rec))
    return 0;

  auto cos_theta_max =
      std::sqrt(1.0f - radius * radius / (center - o).length_squared());
  auto solid_angle = 2 * PI * (1.0f - cos_theta_max);
  return 1.0f / solid_angle;
}

Vec3 Sphere::random(const Vec3 &o) const {
  Vec3 direction = center - o;
  auto distance_squared = direction.length_squared();

  auto w = unit_vector(direction);
  auto a = (std::abs(w.x()) > 0.9f) ? Vec3(0, 1, 0) : Vec3(1, 0, 0);
  auto u = unit_vector(cross(a, w));
  if (std::abs(w.x()) > 0.9f)
    a = Vec3(0, 1, 0);
  else
    a = Vec3(1, 0, 0);
  u = unit_vector(cross(a, w));
  Vec3 v = cross(w, u);

  auto r1 = random_real();
  auto r2 = random_real();
  auto z =
      1.0f + r2 * (std::sqrt(1.0f - radius * radius / distance_squared) - 1.0f);

  auto phi = 2 * PI * r1;
  auto x = std::cos(phi) * std::sqrt(1.0f - z * z);
  auto y = std::sin(phi) * std::sqrt(1.0f - z * z);

  return x * u + y * v + w * z;
}

bool Quad::hit(const Ray &r, Real t_min, Real t_max, HitRecord &rec) const {
  auto denom = dot(normal, r.dir);
  // --- MODIFICATION : Epsilon pour float ---
  if (std::fabs(denom) < 1e-6f)
    return false;

  auto t = (D - dot(normal, r.orig)) / denom;
  if (t < t_min || t > t_max)
    return false;

  auto intersection = r.at(t);
  Vec3 planar_hitpt_vector = intersection - Q;
  auto alpha = dot(w, cross(planar_hitpt_vector, v));
  auto beta = dot(w, cross(u, planar_hitpt_vector));

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

bool Quad::bounding_box(AABB &output_box) const {
  // Calcul de la boite min/max du parallélogramme
  // Q est un coin, u et v sont les vecteurs côtés
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

  // Ajouter un petit padding pour éviter les boites d'épaisseur nulle
  Real padding = 0.0001f;
  if (std::fabs(max_v.x() - min_v.x()) < padding) {
    min_v.e[0] -= padding;
    max_v.e[0] += padding;
  }
  if (std::fabs(max_v.y() - min_v.y()) < padding) {
    min_v.e[1] -= padding;
    max_v.e[1] += padding;
  }
  if (std::fabs(max_v.z() - min_v.z()) < padding) {
    min_v.e[2] -= padding;
    max_v.e[2] += padding;
  }

  output_box = AABB(min_v, max_v);
  return true;
}

Real Quad::pdf_value(const Vec3 &o, const Vec3 &v) const {
  HitRecord rec;
  if (!this->hit(Ray(o, v), 0.001f, std::numeric_limits<Real>::infinity(), rec))
    return 0;

  auto distance_squared = rec.t * rec.t * v.length_squared();
  auto cosine = std::fabs(dot(v, rec.normal) / v.length());
  return distance_squared / (cosine * area);
}

Vec3 Quad::random(const Vec3 &o) const {
  auto p = Q + (random_real() * u) + (random_real() * v);
  return p - o;
}

bool HittableList::hit(const Ray &r, Real t_min, Real t_max,
                       HitRecord &rec) const {
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

bool HittableList::bounding_box(AABB &output_box) const {
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

Real HittableList::pdf_value(const Vec3 &o, const Vec3 &v) const {
  if (raw_objects.empty())
    return 0.0f;

  auto weight = 1.0f / raw_objects.size();
  Real sum = 0;
  for (const auto *object : raw_objects)
    sum += weight * object->pdf_value(o, v);
  return sum;
}

Vec3 HittableList::random(const Vec3 &o) const {
  auto list_size = raw_objects.size();
  if (list_size == 0)
    return Vec3(1, 0, 0);

  std::uniform_int_distribution<size_t> dist(0, list_size - 1);
  size_t random_index = dist(generator);

  return raw_objects[random_index]->random(o);
}

// ===============================================================================================
// BVHNode
// ===============================================================================================

class BVHNode : public Hittable {
public:
  std::shared_ptr<Hittable> left;
  std::shared_ptr<Hittable> right;
  AABB box;

  // Constructeur principal pour l'extérieur
  BVHNode(const HittableList &list)
      : BVHNode(list.owned_objects, 0, list.owned_objects.size()) {}

  // Constructeur récursif interne
  BVHNode(const std::vector<std::shared_ptr<Hittable>> &src_objects,
          size_t start, size_t end) {
    auto objects = src_objects; // Copie locale modifiable pour le tri

    int axis = static_cast<int>(random_real(0, 3)); // 0=X, 1=Y, 2=Z

    // Comparateur
    auto comparator = [axis](const std::shared_ptr<Hittable> &a,
                             const std::shared_ptr<Hittable> &b) {
      AABB box_a, box_b;
      if (!a->bounding_box(box_a) || !b->bounding_box(box_b))
        std::cerr << "Objet sans boite englobante dans le BVH.\n";
      return box_a.min[axis] < box_b.min[axis];
    };

    size_t object_span = end - start;

    if (object_span == 1) {
      left = right = objects[start];
    } else if (object_span == 2) {
      if (comparator(objects[start], objects[start + 1])) {
        left = objects[start];
        right = objects[start + 1];
      } else {
        left = objects[start + 1];
        right = objects[start];
      }
    } else {
      std::sort(objects.begin() + start, objects.begin() + end, comparator);
      size_t mid = start + object_span / 2;
      left = std::make_shared<BVHNode>(objects, start, mid);
      right = std::make_shared<BVHNode>(objects, mid, end);
    }

    AABB box_left, box_right;
    if (!left->bounding_box(box_left) || !right->bounding_box(box_right))
      std::cerr << "Objet sans boite englobante.\n";

    box = surrounding_box(box_left, box_right);
  }

  virtual bool hit(const Ray &r, Real t_min, Real t_max,
                   HitRecord &rec) const override {
    // 1. Si on rate la boite, on s'arrête immédiatement
    if (!box.hit(r, t_min, t_max))
      return false;

    // 2. Sinon on teste les enfants
    bool hit_left = left->hit(r, t_min, t_max, rec);
    // Optimisation : si on touche à gauche à 'rec.t', on n'a besoin de chercher
    // à droite que ce qui est plus proche que 'rec.t'.
    bool hit_right = right->hit(r, t_min, hit_left ? rec.t : t_max, rec);

    return hit_left || hit_right;
  }

  virtual bool bounding_box(AABB &output_box) const override {
    output_box = box;
    return true;
  }
};

// ===============================================================================================
// ENVIRONMENT MAP
// ===============================================================================================

struct EnvironmentMap {
  std::vector<Real> data;
  int width;
  int height;
  Real visible_strength = 1.0f;
  Real lighting_strength = 1.0f;

  EnvironmentMap(const std::vector<Real> &d, int w, int h)
      : data(d), width(w), height(h) {}

  void set_strengths(Real vis, Real light) {
    visible_strength = vis;
    lighting_strength = light;
  }

  Vec3 sample(const Vec3 &dir, bool is_primary) const {
    if (dir.length_squared() < 1e-6f)
      return Vec3(0, 0, 0);

    Real strength = is_primary ? visible_strength : lighting_strength;
    if (strength <= 0)
      return Vec3(0, 0, 0);

    auto unit_dir = unit_vector(dir);
    auto theta = std::acos(unit_dir.y());
    auto phi = std::atan2(-unit_dir.z(), unit_dir.x()) + PI;

    Real u = phi / (2 * PI);
    Real v = theta / PI;

    // Bilinear interpolation
    Real px = u * width - 0.5f;
    Real py = v * height - 0.5f;

    int x0 = static_cast<int>(std::floor(px));
    int y0 = static_cast<int>(std::floor(py));

    Real fx = px - x0;
    Real fy = py - y0;

    auto get_pixel = [&](int x, int y) {
      // Wrap x, Clamp y
      x = (x % width + width) % width;
      y = std::max(0, std::min(y, height - 1));
      int idx = (y * width + x) * 3;
      // Bounds check not needed if logic is correct, but keeping safe
      if (idx < 0 || idx + 2 >= data.size())
        return Vec3(0, 0, 0);
      return Vec3(data[idx], data[idx + 1], data[idx + 2]);
    };

    Vec3 c00 = get_pixel(x0, y0);
    Vec3 c10 = get_pixel(x0 + 1, y0);
    Vec3 c01 = get_pixel(x0, y0 + 1);
    Vec3 c11 = get_pixel(x0 + 1, y0 + 1);

    Vec3 c0 = c00 * (1.0f - fx) + c10 * fx;
    Vec3 c1 = c01 * (1.0f - fx) + c11 * fx;

    return (c0 * (1.0f - fy) + c1 * fy) * strength;
  }
};

// ===============================================================================================
// RENDERER
// ===============================================================================================

Vec3 ray_color(const Ray &r, const Hittable &world, const HittableList &lights,
               const EnvironmentMap *env_map, int depth) {
  if (depth <= 0)
    return Vec3(0, 0, 0);

  HitRecord rec;
  if (!world.hit(r, 0.001f, std::numeric_limits<Real>::infinity(), rec)) {
    if (env_map)
      return env_map->sample(r.dir, r.is_primary);
    return Vec3(0, 0, 0);
  }

  Vec3 emitted = rec.mat_ptr->emit(r, rec, rec.u, rec.v, rec.p);

  ScatterRecord srec;
  if (!rec.mat_ptr->scatter(r, rec, srec))
    return emitted;

  if (srec.is_specular) {
    return emitted + srec.attenuation * ray_color(srec.specular_ray, world,
                                                  lights, env_map, depth - 1);
  }

  // NEE
  Vec3 direct_light(0, 0, 0);

  // Only sample lights if there are any
  if (!lights.raw_objects.empty()) {
    auto light_ray_dir = lights.random(rec.p);
    Ray light_ray(rec.p, light_ray_dir, r.tm, true);
    auto light_pdf_val = lights.pdf_value(rec.p, light_ray.dir);

    if (light_pdf_val > 0) {
      HitRecord hit_light;
      if (world.hit(light_ray, 0.001f, std::numeric_limits<Real>::infinity(),
                    hit_light)) {
        auto li_emit = hit_light.mat_ptr->emit(
            light_ray, hit_light, hit_light.u, hit_light.v, hit_light.p);
        if (li_emit.length_squared() > 0) {
          auto scattering_pdf = rec.mat_ptr->scattering_pdf(r, rec, light_ray);
          if (scattering_pdf > 0) {
            direct_light =
                li_emit * srec.attenuation * scattering_pdf / light_pdf_val;
          }
        }
      }
    }
  }

  // 2. Indirect
  auto indirect = srec.attenuation * ray_color(srec.specular_ray, world, lights,
                                               env_map, depth - 1);

  return emitted + direct_light + indirect;
}

// Forward decl
Vec3 ray_color_nee(const Ray &r, const Hittable &world,
                   const HittableList &lights, const EnvironmentMap *env_map,
                   int depth, bool allow_emission = true);

Vec3 ray_color_nee(const Ray &r, const Hittable &world,
                   const HittableList &lights, const EnvironmentMap *env_map,
                   int depth, bool allow_emission) {
  if (depth <= 0)
    return Vec3(0, 0, 0);

  HitRecord rec;
  if (!world.hit(r, 0.001f, std::numeric_limits<Real>::infinity(), rec)) {
    if (env_map && allow_emission)
      return env_map->sample(r.dir, r.is_primary);
    return Vec3(0, 0, 0);
  }

  Vec3 emitted = rec.mat_ptr->emit(r, rec, rec.u, rec.v, rec.p);
  if (!allow_emission)
    emitted = Vec3(0, 0, 0); // Suppress

  ScatterRecord srec;
  if (!rec.mat_ptr->scatter(r, rec, srec))
    return emitted; // Light source hit directly

  if (srec.is_specular) {
    return emitted + srec.attenuation * ray_color_nee(srec.specular_ray, world,
                                                      lights, env_map,
                                                      depth - 1, true);
  }

  // Direct
  Vec3 direct(0, 0, 0);
  if (!lights.raw_objects.empty()) {
    auto light_ray_dir = lights.random(rec.p);
    Ray light_ray(rec.p, light_ray_dir, r.tm, true);
    auto light_pdf = lights.pdf_value(rec.p, light_ray.dir);

    if (light_pdf > 0) {
      Vec3 transmission(1.0f, 1.0f, 1.0f);
      Ray shadow_ray = light_ray;
      bool reached_light = false;
      HitRecord hit_light;

      // Loop for transparent shadows (Fake Caustics)
      for (int i = 0; i < 5; ++i) { // Max 5 transparent layers
        if (world.hit(shadow_ray, 0.001f, std::numeric_limits<Real>::infinity(),
                      hit_light)) {
          // Hit something
          if (hit_light.mat_ptr->is_transparent()) {
            // Attenuate
            ScatterRecord srec_shadow;
            if (hit_light.mat_ptr->scatter(shadow_ray, hit_light,
                                           srec_shadow)) {
              transmission = transmission * srec_shadow.attenuation;
            }

            // Continue ray through
            shadow_ray = Ray(hit_light.p + 0.001f * shadow_ray.dir,
                             shadow_ray.dir, shadow_ray.tm, true);
          } else {
            // Opaque or Light?
            // Check if it's a light source
            auto li_emit = hit_light.mat_ptr->emit(
                shadow_ray, hit_light, hit_light.u, hit_light.v, hit_light.p);
            if (li_emit.length_squared() > 0) {
              // It is a light!
              // Use this emission
              auto scattering_pdf =
                  rec.mat_ptr->scattering_pdf(r, rec, light_ray);
              if (scattering_pdf > 0) {
                direct =
                    li_emit * srec.attenuation * scattering_pdf / light_pdf;
                direct = direct * transmission; // Apply transparency
              }
              reached_light = true;
            }
            break; // Stopped by opaque or light
          }
        } else {
          break;
        }
      }
    }
  }

  // Indirect
  // Use stored specular_ray (which is diffuse importance sampled ray in this
  // case)
  Vec3 indirect =
      srec.attenuation * ray_color_nee(srec.specular_ray, world, lights,
                                       env_map, depth - 1, false);

  return emitted + direct + indirect;
}

// Camera
class Camera {
public:
  Vec3 origin;
  Vec3 lower_left_corner;
  Vec3 horizontal;
  Vec3 vertical;
  Vec3 u, v, w;
  Real lens_radius;

  Camera(Vec3 lookfrom, Vec3 lookat, Vec3 vup, Real vfov, Real aspect_ratio,
         Real aperture, Real focus_dist) {
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
    return Ray(origin + offset,
               lower_left_corner + s * horizontal + t * vertical - origin -
                   offset,
               random_real());
  }
};

// Scene Manager API
class PyScene {
public:
  HittableList world;
  HittableList lights;
  std::shared_ptr<Hittable> world_bvh;
  std::shared_ptr<Camera> camera;
  std::shared_ptr<EnvironmentMap> background;

  // Progress tracking
  std::atomic<int> completed_scanlines{0};
  std::atomic<int> total_scanlines{1};

  PyScene() {
    // Default black environment map 1x1
    std::vector<Real> d = {0, 0, 0};
    background = std::make_shared<EnvironmentMap>(d, 1, 1);
  }

  void add_sphere(const Vec3 &center, Real radius, std::string mat_type,
                  const Vec3 &color, Real fuzz = 0, Real ir = 1.5f) {
    std::shared_ptr<Material> mat;
    if (mat_type == "lambertian")
      mat = std::make_shared<Lambertian>(color);
    else if (mat_type == "metal")
      mat = std::make_shared<Metal>(color, fuzz);
    else if (mat_type == "dielectric")
      mat = std::make_shared<Dielectric>(ir, color);
    else if (mat_type == "plastic")
      mat = std::make_shared<Plastic>(color, ir, fuzz);
    else if (mat_type == "light")
      mat = std::make_shared<DiffuseLight>(color);

    auto sphere = std::make_shared<Sphere>(center, radius, mat);
    world.add(sphere);
    if (mat_type == "light")
      lights.add(sphere);
  }

  void add_checker_sphere(const Vec3 &center, Real radius, const Vec3 &color1,
                          const Vec3 &color2, Real scale) {
    auto mat = std::make_shared<LambertianChecker>(color1, color2, scale);
    auto sphere = std::make_shared<Sphere>(center, radius, mat);
    world.add(sphere);
  }

  void add_invisible_sphere_light(const Vec3 &center, Real radius,
                                  const Vec3 &color) {
    auto mat = std::make_shared<InvisibleLight>(color);
    auto sphere = std::make_shared<Sphere>(center, radius, mat);
    world.add(sphere);
    lights.add(sphere);
  }

  void add_quad(const Vec3 &Q, const Vec3 &u, const Vec3 &v,
                std::string mat_type, const Vec3 &color, Real fuzz = 0,
                Real ir = 1.5f) {
    std::shared_ptr<Material> mat;
    if (mat_type == "lambertian")
      mat = std::make_shared<Lambertian>(color);
    else if (mat_type == "metal")
      mat = std::make_shared<Metal>(color, fuzz);
    else if (mat_type == "dielectric")
      mat = std::make_shared<Dielectric>(ir, color);
    else if (mat_type == "plastic")
      mat = std::make_shared<Plastic>(color, ir, fuzz);
    else if (mat_type == "light")
      mat = std::make_shared<DiffuseLight>(color);

    auto quad = std::make_shared<Quad>(Q, u, v, mat);
    world.add(quad);
    if (mat_type == "light")
      lights.add(quad);
  }

  void set_camera(const Vec3 &lookfrom, const Vec3 &lookat, const Vec3 &vup,
                  Real vfov, Real aspect, Real aperture, Real dist) {
    camera = std::make_shared<Camera>(lookfrom, lookat, vup, vfov, aspect,
                                      aperture, dist);
  }

  void set_environment(nb::object image) {
    PyObject *obj = image.ptr();
    Py_buffer view;
    int flags = PyBUF_STRIDES | PyBUF_FORMAT | PyBUF_ND;

    if (PyObject_GetBuffer(obj, &view, flags) != 0) {
      throw std::runtime_error(
          "Argument is not a buffer compatible object (numpy array required)");
    }

    struct BufferGuard {
      Py_buffer *v;
      ~BufferGuard() { PyBuffer_Release(v); }
    } guard{&view};

    if (view.ndim != 3)
      throw std::runtime_error("Environment map must be 3D array (H,W,C)");

    size_t h = static_cast<size_t>(view.shape[0]);
    size_t w = static_cast<size_t>(view.shape[1]);
    size_t c = static_cast<size_t>(view.shape[2]);

    if (c != 3)
      throw std::runtime_error("Environment map must have 3 channels (RGB)");

    std::vector<Real> data(w * h * 3);

    const char *buf = static_cast<const char *>(view.buf);
    size_t stride_y = static_cast<size_t>(view.strides[0]);
    size_t stride_x = static_cast<size_t>(view.strides[1]);
    size_t stride_c = static_cast<size_t>(view.strides[2]);

    for (size_t y = 0; y < h; ++y) {
      for (size_t x = 0; x < w; ++x) {
        for (size_t k = 0; k < 3; ++k) {
          const void *pixel_addr =
              buf + y * stride_y + x * stride_x + k * stride_c;
          float val = *static_cast<const float *>(pixel_addr);
          data[(y * w + x) * 3 + k] = static_cast<Real>(val);
        }
      }
    }

    // background = std::make_shared<EnvironmentMap>(data, w, h);
    //  On convertit explicitement w et h (size_t) en int pour le constructeur
    background = std::make_shared<EnvironmentMap>(data, static_cast<int>(w),
                                                  static_cast<int>(h));
  }

  void set_env_strength(Real vis, Real light) {
    if (background) {
      background->set_strengths(vis, light);
    }
  }

  nb::ndarray<nb::numpy, float> render(int width, int height, int spp,
                                       int depth, int n_threads) {

    // CONSTRUIRE LE BVH AVANT LE RENDU
    if (world.owned_objects.empty()) {
      world_bvh = std::make_shared<HittableList>();
    } else {
      world_bvh = std::make_shared<BVHNode>(world);
    }

    // Init progress
    total_scanlines = height;
    completed_scanlines = 0;

    // Prepare output
    float *data = new float[width * height * 3];

    try {
      // Scope for GIL release
      // We only release GIL during the heavy computation
      {
        nb::gil_scoped_release release;

        // Set thread count if specified
        if (n_threads > 0) {
          omp_set_num_threads(n_threads);
        }

// Parallel Rendering
// Simple OMP
#pragma omp parallel for schedule(dynamic)
        for (int j = 0; j < height; ++j) {
          for (int i = 0; i < width; ++i) {
            Vec3 pixel_color(0, 0, 0);
            for (int s = 0; s < spp; ++s) {
              auto u = (i + random_real()) / (width - 1);
              auto v = (j + random_real()) / (height - 1);
              Ray r = camera->get_ray(u, v);
              r.is_primary = true;
              pixel_color += ray_color_nee(r, *world_bvh, lights,
                                           background.get(), depth, true);
            }

            int idx = ((height - 1 - j) * width + i) * 3;
            data[idx + 0] = pixel_color.x() / spp;
            data[idx + 1] = pixel_color.y() / spp;
            data[idx + 2] = pixel_color.z() / spp;
          }

          // Update progress
          completed_scanlines++;
        }
      } // GIL assumed re-acquired here

    } catch (const std::exception &e) {
      std::cerr << "Render error: " << e.what() << std::endl;
      delete[] data;
      throw;
    } catch (...) {
      std::cerr << "Unknown render error" << std::endl;
      delete[] data;
      throw;
    }

    nb::capsule owner(data, [](void *p) noexcept { delete[] (float *)p; });

    return nb::ndarray<nb::numpy, float>(
        data, {(size_t)height, (size_t)width, 3ul}, owner);
  }

  float get_progress() const {
    int t = total_scanlines.load();
    if (t == 0)
      return 0.0f;
    return (float)completed_scanlines.load() / t;
  }
};

NB_MODULE(cpp_engine, m) {
  nb::class_<PyScene>(m, "Engine")
      .def(nb::init<>())
      .def("add_sphere", &PyScene::add_sphere)
      .def("add_invisible_sphere_light", &PyScene::add_invisible_sphere_light)
      .def("add_checker_sphere", &PyScene::add_checker_sphere)
      .def("add_quad", &PyScene::add_quad)
      .def("set_camera", &PyScene::set_camera)
      .def("set_environment", &PyScene::set_environment)
      .def("set_env_strength", &PyScene::set_env_strength)
      .def("get_progress", &PyScene::get_progress)
      .def("render", &PyScene::render, nb::arg("width"), nb::arg("height"),
           nb::arg("spp"), nb::arg("depth"), nb::arg("n_threads") = 0);

  nb::class_<Vec3>(m, "Vec3").def(nb::init<Real, Real, Real>());
}