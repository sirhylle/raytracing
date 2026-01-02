#include <nanobind/nanobind.h>
#include <nanobind/ndarray.h>
#include <nanobind/stl/pair.h>
#include <nanobind/stl/shared_ptr.h>
#include <nanobind/stl/string.h>
#include <nanobind/stl/tuple.h>
#include <nanobind/stl/vector.h>

#include <algorithm>
#include <atomic>
#include <cmath>
#include <iostream>
#include <limits>
#include <memory>
#include <omp.h>
#include <random>
#include <stdexcept>
#include <string>
#include <vector>

namespace nb = nanobind;
using namespace nb::literals;

// ===============================================================================================
// GLOBAL CONFIGURATION
// ===============================================================================================

using Real = float;
const Real PI = 3.1415926535897932385f;

// 1. Gestion du faux soleil (InvisibleLight) dans les reflets
// true  : Le soleil est visible dans les miroirs/verres (Recommandé)
// false : Le soleil est totalement invisible (sauf pour éclairer la scène)
const bool VISIBLE_IN_REFLECTIONS = true;

// 2. Intensité de l'ombre des objets transparents (Verre/Eau)
// 1.0 = Pas d'ombre (Physiquement incorrect pour un path tracer simple)
// 0.8 = Ombre légère (Réaliste "artistique")
// 0.0 = Ombre noire (Physiquement faux mais très contrasté)
const Real DIELECTRIC_SHADOW_TRANSMISSION = 0.8f;

// 3. Gestion des Fireflies (Lucioles)
// Valeur à partir de laquelle on commence à compresser les pixels trop lumineux
// 100.0 = Conservateur (garde la dynamique)
// 10.0  = Agressif (image très propre mais caustiques ternes)
const Real FIREFLY_CLAMP_LIMIT = 50.0f;

// ===============================================================================================
// CORE MATH
// ===============================================================================================

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

// Fonction de compression douce
// Transforme x (0 -> inf) en y (0 -> limit)
// Les valeurs faibles ne changent presque pas, les valeurs extrêmes sont
// freinées.
inline Real soft_clamp(Real x, Real limit) { return x * limit / (x + limit); }

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
};

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

class Triangle : public Hittable {
public:
  Vec3 v0, v1, v2; // Les 3 sommets
  Vec3 n0, n1, n2; // Les 3 normales aux sommets
  std::shared_ptr<Material> mat_ptr;

  Triangle(Vec3 _v0, Vec3 _v1, Vec3 _v2, Vec3 _n0, Vec3 _n1, Vec3 _n2,
           std::shared_ptr<Material> m);

  virtual bool hit(const Ray &r, Real t_min, Real t_max,
                   HitRecord &rec) const override;
  virtual bool bounding_box(AABB &output_box) const override;
  // On peut laisser pdf et random par défaut (return 0) pour l'instant
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

  virtual Vec3 get_albedo(const HitRecord &rec) const { return Vec3(0, 0, 0); }

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

  virtual Vec3 get_albedo(const HitRecord &rec) const override {
    return albedo;
  }
};

class LambertianChecker : public Material {
public:
  Vec3 albedo1;
  Vec3 albedo2;
  Real scale;

  LambertianChecker(const Vec3 &a1, const Vec3 &a2, Real s)
      : albedo1(a1), albedo2(a2), scale(s) {}

  virtual Vec3 get_albedo(const HitRecord &rec) const override {
    // Fréquence du damier
    const double s = scale;

    // Calcul des coordonnées entières de la "case"
    // On utilise floor pour gérer correctement les négatifs
    int ix = static_cast<int>(std::floor(s * rec.p.x()));
    int iy = static_cast<int>(std::floor(s * rec.p.y()));
    int iz = static_cast<int>(std::floor(s * rec.p.z()));

    // LOGIQUE ROBUSTE :
    // 1. Si on est sur le sol (Y ~ 0), le "iy" va clignoter entre 0 et -1.
    // 2. La solution propre est de désactiver l'influence de Y pour le sol.
    //    On peut le faire dynamiquement : si la normale pointe vers le haut
    //    (0,1,0), on ignore la composante Y du damier.

    bool isPlanar =
        std::abs(rec.normal.y()) > 0.9; // Détection auto du sol plat

    // Formule XOR Standard (très rapide et stable)
    // (ix ^ iy ^ iz) & 1  vérifie si la somme des bits est impaire
    bool isOdd;

    if (isPlanar) {
      // Mode 2D : On ignore iy (on considère qu'on est sur la couche 0)
      isOdd = (ix ^ iz) & 1;
    } else {
      // Mode 3D complet (pour les sphères)
      isOdd = (ix ^ iy ^ iz) & 1;
    }

    return isOdd ? albedo2 : albedo1;
  }

  // 1. On centralise la logique de couleur ici
  virtual Vec3 get_albedo_old(const HitRecord &rec) {
    // Epsilon minuscule pour X et Z (juste pour la stabilité numérique des
    // lignes) Cela ne décale pas le motif visiblement.
    const double eps = 1e-5;

    // LE FIX EST ICI : On décale Y de 0.5 (moitié d'une case).
    // Ainsi, le sol (y=0) tombe mathématiquement au milieu d'une case
    // verticale. Fini le bruit, et fini le décalage horizontal !
    int xInt = static_cast<int>(std::floor(scale * rec.p.x() + eps));
    int yInt = static_cast<int>(std::floor(scale * rec.p.y() + 0.5));
    int zInt = static_cast<int>(std::floor(scale * rec.p.z() + eps));

    // Astuce bitwise : Si la somme des coordonnées entières est paire
    bool isEven = (xInt + yInt + zInt) % 2 == 0;

    return isEven ? albedo1 : albedo2;
  }

  virtual bool scatter(const Ray &r_in, const HitRecord &rec,
                       ScatterRecord &srec) const override {
    srec.is_specular = false;

    // 2. Scatter récupère maintenant la couleur via get_albedo
    // Cela garantit que le rendu et le débruitage "voient" la même chose.
    srec.attenuation = get_albedo(rec);

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

  virtual Vec3 get_albedo(const HitRecord &rec) const override {
    return albedo;
  }
};

// Phantom Light: Visible only to Shadow Rays (is_shadow=true),
// Transparent to Camera/Specular rays.
class InvisibleLight : public Material {
public:
  Vec3 emit_color;
  InvisibleLight(const Vec3 &c) : emit_color(c) {}

  virtual bool is_transparent() const override { return true; }

  virtual bool scatter(const Ray &r_in, const HitRecord &rec,
                       ScatterRecord &srec) const override {

    // LOGIQUE CONDITIONNELLE
    if (VISIBLE_IN_REFLECTIONS) {
      // Si activé : On bloque les rayons secondaires (reflets) pour qu'ils
      // voient l'émission
      if (!r_in.is_primary) {
        return false;
      }
    }

    // Si désactivé OU si c'est un rayon primaire : On laisse tout passer
    // (transparence)

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

    bool should_emit = false;

    // 1. Toujours émettre pour les ombres (pour éclairer la scène)
    if (r_in.is_shadow) {
      should_emit = true;
    }

    // 2. Si activé, émettre aussi pour les reflets (!is_primary)
    if (VISIBLE_IN_REFLECTIONS && !r_in.is_primary) {
      should_emit = true;
    }

    if (should_emit) {
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

  virtual Vec3 get_albedo(const HitRecord &rec) const override { return tint; }
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

  virtual Vec3 get_albedo(const HitRecord &rec) const override {
    return albedo;
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

  virtual Vec3 get_albedo(const HitRecord &rec) const override {
    return emit_color;
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

// --- IMPLÉMENTATION TRIANGLE ---

Triangle::Triangle(Vec3 _v0, Vec3 _v1, Vec3 _v2, Vec3 _n0, Vec3 _n1, Vec3 _n2,
                   std::shared_ptr<Material> m)
    : v0(_v0), v1(_v1), v2(_v2), n0(_n0), n1(_n1), n2(_n2), mat_ptr(m) {
  // On ne pas la normale géométrique ici, on fait confiance aux
  // données
}

bool Triangle::hit(const Ray &r, Real t_min, Real t_max, HitRecord &rec) const {
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

    // --- Interpolation de Phong (Smooth Shading) ---
    // On utilise les coordonnées barycentriques (u, v) et w = 1-u-v
    // pour mélanger les normales des 3 sommets.
    Vec3 smooth_normal = (1.0f - u - v) * n0 + u * n1 + v * n2;

    // Important : Il faut re-normaliser car l'interpolation linéaire raccourcit
    // les vecteurs
    rec.set_face_normal(r, unit_vector(smooth_normal));

    rec.mat_ptr = mat_ptr.get();
    rec.u = u;
    rec.v = v;
    return true;
  }
  return false;
}

bool Triangle::bounding_box(AABB &output_box) const {
  // On cherche le min et max sur les 3 axes
  Real min_x = std::min({v0.x(), v1.x(), v2.x()});
  Real min_y = std::min({v0.y(), v1.y(), v2.y()});
  Real min_z = std::min({v0.z(), v1.z(), v2.z()});

  Real max_x = std::max({v0.x(), v1.x(), v2.x()});
  Real max_y = std::max({v0.y(), v1.y(), v2.y()});
  Real max_z = std::max({v0.z(), v1.z(), v2.z()});

  // Petit padding de sécurité (0.001) pour éviter les boites plates qui cassent
  // le BVH
  output_box = AABB(Vec3(min_x - 0.001f, min_y - 0.001f, min_z - 0.001f),
                    Vec3(max_x + 0.001f, max_y + 0.001f, max_z + 0.001f));
  return true;
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

  // 1. Constructeur Public (Point d'entrée)
  // On prend 'HittableList list' par VALEUR pour forcer une copie unique ici.
  // Ensuite on délègue le travail au constructeur récursif qui travaillera sur
  // cette copie.
  BVHNode(HittableList list)
      : BVHNode(list.owned_objects, 0, list.owned_objects.size()) {}

  // 2. Constructeur Récursif Interne
  // IMPORTANT : On prend 'objects' par RÉFÉRENCE (std::vector<...>&) pour ne
  // plus copier !
  BVHNode(std::vector<std::shared_ptr<Hittable>> &objects, size_t start,
          size_t end) {

    // PLUS DE COPIE ICI ! On travaille directement sur la référence.

    // 1. Calculer la bbox de tous les objets actuels pour trouver le meilleur
    // axe
    AABB total_box;
    bool first = true;
    for (size_t i = start; i < end; ++i) {
      AABB temp_box;
      if (objects[i]->bounding_box(temp_box)) {
        total_box = first ? temp_box : surrounding_box(total_box, temp_box);
        first = false;
      }
    }

    Vec3 extent = total_box.max - total_box.min;
    int axis = 0; // Par défaut X
    if (extent.y() > extent.x() && extent.y() > extent.z())
      axis = 1; // Y est le plus long
    else if (extent.z() > extent.x() && extent.z() > extent.y())
      axis = 2; // Z est le plus long

    // Comparateur
    auto comparator = [axis](const std::shared_ptr<Hittable> &a,
                             const std::shared_ptr<Hittable> &b) {
      AABB box_a, box_b;
      if (!a->bounding_box(box_a) || !b->bounding_box(box_b))
        return false; // Sécurité
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
      // Tri sur place (In-place sort) de la section du vecteur
      std::sort(objects.begin() + start, objects.begin() + end, comparator);

      size_t mid = start + object_span / 2;

      // Récursion : on repasse la même référence 'objects'
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
    if (!box.hit(r, t_min, t_max))
      return false;

    bool hit_left = left->hit(r, t_min, t_max, rec);
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
  Real env_visible_scale = 1.0f;
  Real env_direct_scale = 1.0f;
  Real env_indirect_scale = 1.0f;

  // Pour l'Importance Sampling
  std::vector<Real> marginal_CDF; // Probabilité de choisir une ligne Y
  std::vector<std::vector<Real>>
      conditional_CDFs; // Probabilité de choisir X sachant Y

  EnvironmentMap(const std::vector<Real> &d, int w, int h)
      : data(d), width(w), height(h) {
    build_cdf();
  }

  void set_scales(Real vis, Real direct, Real indirect) {
    env_visible_scale = vis;
    env_direct_scale = direct;
    env_indirect_scale = indirect;
  }

  // Trouve la direction du pixel le plus lumineux
  // Retourne une paire : {Direction, IntensitéMax}
  std::pair<Vec3, Vec3> find_sun_hotspot() const {
    Real max_lum = -1.0f;
    int best_x = 0;
    int best_y = 0;
    Vec3 best_color(0, 0, 0);

    for (int y = 0; y < height; ++y) {
      for (int x = 0; x < width; ++x) {
        // Récupération manuelle (inlining simple)
        int idx = (y * width + x) * 3;
        Real r = data[idx];
        Real g = data[idx + 1];
        Real b = data[idx + 2];

        // Luminance simple
        Real lum = 0.2126f * r + 0.7152f * g + 0.0722f * b;

        if (lum > max_lum) {
          max_lum = lum;
          best_x = x;
          best_y = y;
          best_color = Vec3(r, g, b);
        }
      }
    }

    // Conversion (x,y) -> (u,v) -> Direction (Inverse de sample())
    // On centre le pixel (+0.5)
    Real u = (best_x + 0.5f) / width;
    Real v = (best_y + 0.5f) / height;

    Real theta = v * PI;          // v va de 0 à 1, theta de 0 à PI
    Real phi = (u * 2 * PI) - PI; // u va de 0 à 1, phi de -PI à +PI

    Real sin_theta = std::sin(theta);
    Real cos_theta = std::cos(theta);
    Real sin_phi = std::sin(phi);
    Real cos_phi = std::cos(phi);

    // Même convention que ton code existant (Y-up)
    Vec3 dir(sin_theta * cos_phi, cos_theta, -sin_theta * sin_phi);

    return {unit_vector(dir), best_color};
  }

  // Calculer la luminosité perçue d'un pixel
  Real get_luminance(int x, int y) const {
    int idx = (y * width + x) * 3;
    Real r = data[idx];
    Real g = data[idx + 1];
    Real b = data[idx + 2];
    return 0.2126f * r + 0.7152f * g + 0.0722f * b;
  }

  void build_cdf() {
    marginal_CDF.resize(height + 1);
    conditional_CDFs.resize(height, std::vector<Real>(width + 1));

    Real total_integral = 0.0f;

    for (int y = 0; y < height; ++y) {
      // Facteur sin(theta) pour corriger la distorsion de la sphère (les pôles
      // sont plus petits)
      Real v = (y + 0.5f) / height;
      Real theta = v * PI;
      Real sin_theta = std::sin(theta);

      Real row_integral = 0.0f;
      conditional_CDFs[y][0] = 0.0f;

      for (int x = 0; x < width; ++x) {
        // Luminosité pondérée par l'aire sur la sphère
        Real importance = get_luminance(x, y) * sin_theta;
        row_integral += importance;
        conditional_CDFs[y][x + 1] = row_integral;
      }

      // Normalisation de la ligne (CDF conditionnelle)
      if (row_integral > 0) {
        for (int x = 1; x <= width; ++x)
          conditional_CDFs[y][x] /= row_integral;
      } else {
        // Ligne noire : probabilité uniforme (fallback)
        for (int x = 1; x <= width; ++x)
          conditional_CDFs[y][x] = (Real)x / width;
      }

      total_integral += row_integral;
      marginal_CDF[y + 1] = total_integral;
    }

    // Normalisation de la colonne marginale
    if (total_integral > 0) {
      for (int y = 1; y <= height; ++y)
        marginal_CDF[y] /= total_integral;
    } else {
      for (int y = 1; y <= height; ++y)
        marginal_CDF[y] = (Real)y / height;
    }
  }

  // Échantillonne une direction importante (vers le soleil/lumière)
  // Retourne la direction et met à jour la probabilité (pdf)
  Vec3 sample_direction(Real &pdf) const {
    // 1. Choisir une ligne Y selon la distribution marginale
    Real r1 = random_real();
    auto it_y = std::lower_bound(marginal_CDF.begin(), marginal_CDF.end(), r1);
    int y = std::max(0, (int)(it_y - marginal_CDF.begin()) - 1);

    // 2. Choisir un pixel X dans cette ligne selon la distribution
    // conditionnelle
    Real r2 = random_real();
    auto it_x = std::lower_bound(conditional_CDFs[y].begin(),
                                 conditional_CDFs[y].end(), r2);
    int x = std::max(0, (int)(it_x - conditional_CDFs[y].begin()) - 1);

    // 3. Convertir (x,y) en UV puis en Direction
    Real u = (x + random_real()) / width;
    Real v = (y + random_real()) / height;

    Real theta = v * PI;
    Real phi = (u * 2 * PI) - PI;

    Real sin_theta = std::sin(theta);
    Real cos_theta = std::cos(theta);
    Real sin_phi = std::sin(phi);
    Real cos_phi = std::cos(phi);

    // Attention aux axes: Y is up dans ton code
    Vec3 dir(sin_theta * cos_phi, cos_theta, -sin_theta * sin_phi);

    // 4. Calculer la PDF (Densité de probabilité) de cette direction
    // PDF = (Probabilité de choisir ce pixel) / (Aire solide du pixel)
    // Probabilité pixel ~ luminance * sin(theta) / TotalIntegral
    // Aire solide pixel ~ (2*PI^2 * sin(theta)) / (Width * Height)

    Real pixel_lum = get_luminance(x, y);
    // Note: on recalcule approximativement la PDF basée sur la luminance
    // Une méthode rigoureuse utiliserait les valeurs du CDF, mais ceci est
    // suffisant pour le NEE

    // Calcul de la somme totale brute (pour normaliser)
    // Astuce : marginal_CDF.back() contient la somme totale *avant*
    // normalisation si on ne divise pas. Mais ici on a normalisé. On peut
    // approximer la PDF simplement :

    // PDF_solid_angle = (pixel_probability) / (sin_theta * 2 * PI * PI / (W*H))
    // C'est complexe à faire exact.
    // Simplification robuste pour le NEE :

    Real pdf_uv = (pixel_lum * sin_theta); // Proportionnel
    // On doit normaliser par l'intégrale totale qu'on n'a pas stockée
    // explicitement post-normalisation C'est le piège classique.

    // APPROCHE SIMPLE : On retourne une PDF géométrique pour l'instant
    // Si on veut faire du "vrai" Monte Carlo, il faut la valeur exacte du PDF.
    // Voici la valeur exacte extraite des CDFs :

    Real prob_y =
        marginal_CDF[y + 1] - marginal_CDF[y]; // Prob d'être dans cette rangée
    Real prob_x_given_y = conditional_CDFs[y][x + 1] -
                          conditional_CDFs[y][x]; // Prob d'être ce pixel
    Real prob_pixel = prob_y * prob_x_given_y;

    if (sin_theta == 0)
      pdf = 0;
    else {
      Real safe_sin =
          std::max(sin_theta, 1e-5f); // Évite la division par quasi-zéro
      pdf = prob_pixel * (width * height) / (2 * PI * PI * safe_sin);
    }

    return unit_vector(dir);
  }

  Vec3 sample(const Vec3 &dir, int mode) const {
    if (dir.length_squared() < 1e-6f)
      return Vec3(0, 0, 0);

    Real strength = 1.0f;
    // Selection du bon multiplicateur selon le mode d'appel
    if (mode == 0)
      strength = env_visible_scale; // Vue Camera
    else if (mode == 1)
      strength = env_direct_scale; // NEE
    else if (mode == 2)
      strength = env_indirect_scale; // GI

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
               const EnvironmentMap *env_map, int depth,
               bool allow_emission = true) {

  // 1. Limite de rebond
  if (depth <= 0)
    return Vec3(0, 0, 0);

  // 2. Intersection avec la scène
  HitRecord rec;
  // Note : Epsilon à 0.001f pour éviter l'acné, Infinity pour le max
  if (!world.hit(r, 0.001f, std::numeric_limits<Real>::infinity(), rec)) {
    // Si on rate tout, on touche le fond (Environment Map)
    if (env_map && allow_emission) {
      // Si primaire (caméra) -> Mode 0 (Visible)
      // Sinon (rebond) -> Mode 2 (Indirect)
      int mode = r.is_primary ? 0 : 2;
      return env_map->sample(r.dir, mode);
    }
    return Vec3(0, 0, 0);
  }

  // 3. Emission propre de l'objet touché
  Vec3 emitted = rec.mat_ptr->emit(r, rec, rec.u, rec.v, rec.p);
  if (!allow_emission)
    emitted = Vec3(0, 0, 0); // Empêche le double comptage pour le NEE

  // 4. Scattering (Rebond)
  ScatterRecord srec;
  if (!rec.mat_ptr->scatter(r, rec, srec))
    return emitted; // C'est une lumière ou un objet noir, on s'arrête.

  // 5. Cas Spécial : Miroirs et Verres (Spéculaire pur)
  // On ne peut pas faire de NEE sur un miroir parfait, on suit juste le rayon.
  if (srec.is_specular) {
    return emitted +
           srec.attenuation *
               ray_color(
                   srec.specular_ray, world, lights, env_map, depth - 1,
                   true); // true car on veut voir les lumières dans le miroir
  }

  // =========================================================
  // 6. NEE (Next Event Estimation) - Éclairage Direct
  // =========================================================
  Vec3 direct_light(0, 0, 0);

  // Stratégie de choix : EnvMap OU Lumières géométriques ?
  bool sample_env = false;

  // On vérifie si l'env map contribue vraiment
  bool env_is_active = env_map && (env_map->env_direct_scale > 0.001f);
  bool lights_are_active = !lights.raw_objects.empty();

  // On gère les différents cas entre envMap et lumières géométriques
  if (env_is_active && lights_are_active) {
    // 50/50
    sample_env = random_real() < 0.5f;
  } else if (env_is_active) {
    // EnvMap seule
    sample_env = true;
  } else if (lights_are_active) {
    // Lumières géométriques seule
    sample_env = false;
  } else {
    // Aucune source de lumière directe !
    return emitted + srec.attenuation * ray_color(srec.specular_ray, world,
                                                  lights, env_map, depth - 1,
                                                  false);
  }

  // Préparation des variables
  Ray light_ray;
  Real light_pdf_val = 0.0f;
  bool is_env_sample = false;
  Vec3 potential_light_emission(0, 0, 0);

  // --- A. Génération du rayon vers la lumière ---
  if (sample_env && env_map) {
    // Importance Sampling de l'HDRI
    Real pdf = 0;
    Vec3 dir = env_map->sample_direction(
        pdf); // Direction vers un point brillant du ciel
    light_ray = Ray(rec.p, dir, r.tm, true);
    light_pdf_val = pdf;

    // Compensation du choix 50/50
    if (lights_are_active)
      light_pdf_val *= 0.5f;

    // On connait déjà la couleur du ciel dans cette direction
    potential_light_emission = env_map->sample(dir, 1);
    if (potential_light_emission.length_squared() <= 0)
      light_pdf_val = 0; // Optim

    is_env_sample = true;

  } else if (!lights.raw_objects.empty()) {
    // Sampling d'une lumière géométrique (Sphère, Quad)
    auto light_ray_dir = lights.random(rec.p);
    light_ray = Ray(rec.p, light_ray_dir, r.tm, true);
    light_pdf_val = lights.pdf_value(rec.p, light_ray.dir);

    // Compensation du choix 50/50
    if (env_is_active)
      light_pdf_val *= 0.5f;

    is_env_sample = false;
  }

  // --- B. Validation et Calcul ---
  if (light_pdf_val > 0) {
    // Le BSDF de notre matériau pour cette direction de lumière
    auto scattering_pdf = rec.mat_ptr->scattering_pdf(r, rec, light_ray);

    if (scattering_pdf > 0) {
      // Rayon d'ombre : Est-ce qu'on voit la lumière ?
      Vec3 transmission(1.0f, 1.0f, 1.0f);
      Ray shadow_ray = light_ray;

      bool light_visible = false;

      // Boucle pour traverser les objets transparents (ex: fenêtres)
      // On s'arrête si on touche un objet opaque ou la lumière visée
      for (int i = 0; i < 5; ++i) {
        HitRecord hit_obstacle;
        // On utilise le BVH ici (world.hit est rapide)
        if (world.hit(shadow_ray, 0.001f, std::numeric_limits<Real>::infinity(),
                      hit_obstacle)) {

          if (hit_obstacle.mat_ptr->is_transparent()) {
            // Si on ne visait PAS le ciel (donc on visait une lampe
            // géométrique), on vérifie si l'objet transparent qu'on traverse
            // n'est pas notre lampe invisible!
            if (!is_env_sample) {
              Vec3 emission_found = hit_obstacle.mat_ptr->emit(
                  shadow_ray, hit_obstacle, hit_obstacle.u, hit_obstacle.v,
                  hit_obstacle.p);
              if (emission_found.length_squared() > 0) {
                // BINGO ! On a trouvé la lumière invisible qu'on visait.
                potential_light_emission = emission_found;
                light_visible = true;
                break; // On s'arrête, pas besoin d'aller voir derrière.
              }
            }

            // C'est du verre (ou pas la bonne lumière), on atténue et on
            // continue
            ScatterRecord srec_shadow;
            if (hit_obstacle.mat_ptr->scatter(shadow_ray, hit_obstacle,
                                              srec_shadow)) {

              transmission = transmission * srec_shadow.attenuation;

              // ASTUCE : On vérifie si l'objet émet de la lumière.
              // - Le Verre / Plastique n'émet rien (0,0,0) -> ON APPLIQUE LE
              // HACK (pour créer une légère ombre en atténuant légèrement la
              // transmission)
              // - La Sphère Invisible émet de la lumière -> ON N'APPLIQUE PAS
              Vec3 check_emit = hit_obstacle.mat_ptr->emit(
                  shadow_ray, hit_obstacle, hit_obstacle.u, hit_obstacle.v,
                  hit_obstacle.p);
              if (check_emit.length_squared() == 0) {
                // C'est un objet passif (Verre/Eau), on force une ombre
                // artificielle
                transmission = transmission * DIELECTRIC_SHADOW_TRANSMISSION;
              }
            }
            // On avance le rayon un poil après l'obstacle
            shadow_ray = Ray(hit_obstacle.p + 0.001f * shadow_ray.dir,
                             shadow_ray.dir, shadow_ray.tm, true);
          } else {
            // Obstacle Opaque ou Lumière
            if (is_env_sample) {
              // Si on visait le ciel et qu'on touche quelque chose d'opaque,
              // c'est raté.
              light_visible = false;
            } else {
              // Si on visait une lampe, est-ce que c'est elle qu'on a touchée ?
              auto li_emit = hit_obstacle.mat_ptr->emit(
                  shadow_ray, hit_obstacle, hit_obstacle.u, hit_obstacle.v,
                  hit_obstacle.p);
              if (li_emit.length_squared() > 0) {
                potential_light_emission = li_emit;
                light_visible = true;
              }
            }
            break; // Fin du rayon
          }
        } else {
          // On n'a rien touché
          if (is_env_sample) {
            // Si on visait le ciel et qu'on touche rien, c'est gagné !
            light_visible = true;
          }
          break;
        }
      }

      // --- C. Contribution finale ---
      if (light_visible) {
        direct_light = potential_light_emission * srec.attenuation *
                       scattering_pdf * transmission / light_pdf_val;
      }
    }
  }

  // 7. Eclairage Indirect (Récursif)
  // Important : allow_emission = false pour ne pas recompter les lumières qu'on
  // vient de sampler au dessus
  Vec3 indirect = srec.attenuation * ray_color(srec.specular_ray, world, lights,
                                               env_map, depth - 1, false);

  // 8. Clamp pour éviter les pixels nucléaires (Fireflies)
  // On ne touche pas à l'émission directe ni à la lumière directe (soleil)
  // On ne compresse que l'indirect (les rebonds "fous")

  indirect.e[0] = soft_clamp(indirect.x(), FIREFLY_CLAMP_LIMIT);
  indirect.e[1] = soft_clamp(indirect.y(), FIREFLY_CLAMP_LIMIT);
  indirect.e[2] = soft_clamp(indirect.z(), FIREFLY_CLAMP_LIMIT);

  return emitted + direct_light + indirect;
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

  void add_mesh(nb::ndarray<float, nb::shape<-1, 3>> vertices,
                nb::ndarray<int, nb::shape<-1, 3>> indices,
                nb::ndarray<float, nb::shape<-1, 3>> normals, // <--- NOUVEAU
                std::string mat_type, const Vec3 &color, Real fuzz = 0.0f,
                Real ir = 1.5f) {

    // 1. Création du matériau (On réutilise la logique existante)
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
    else
      mat = std::make_shared<Lambertian>(Vec3(0.5, 0.5, 0.5)); // Fallback gris

    auto v_view = vertices.view();
    auto i_view = indices.view();
    auto n_view = normals.view();

    size_t num_triangles = i_view.shape(0);

    // 3. Boucle de génération des triangles
    for (size_t k = 0; k < num_triangles; ++k) {
      // On récupère les 3 indices du triangle k
      int idx0 = i_view(k, 0);
      int idx1 = i_view(k, 1);
      int idx2 = i_view(k, 2);

      // On va chercher les sommets correspondants
      Vec3 v0(v_view(idx0, 0), v_view(idx0, 1), v_view(idx0, 2));
      Vec3 v1(v_view(idx1, 0), v_view(idx1, 1), v_view(idx1, 2));
      Vec3 v2(v_view(idx2, 0), v_view(idx2, 1), v_view(idx2, 2));

      Vec3 n0(n_view(idx0, 0), n_view(idx0, 1), n_view(idx0, 2));
      Vec3 n1(n_view(idx1, 0), n_view(idx1, 1), n_view(idx1, 2));
      Vec3 n2(n_view(idx2, 0), n_view(idx2, 1), n_view(idx2, 2));

      auto tri = std::make_shared<Triangle>(v0, v1, v2, n0, n1, n2, mat);
      world.add(tri);

      // Si c'est une lumière, on l'ajoute aussi à la liste des émetteurs pour
      // le NEE
      if (mat_type == "light") {
        lights.add(tri);
      }
    }
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

  void set_env_levels(Real env_background, Real env_direct,
                      Real env_indirect = 1.0f) {
    if (background) {
      background->set_scales(env_background, env_direct, env_indirect);
    }
  }

  // Retourne un tuple (Direction, Couleur) pour Python
  std::pair<Vec3, Vec3> get_env_sun_info() {
    if (background) {
      return background->find_sun_hotspot();
    }
    return {Vec3(0, 1, 0), Vec3(0, 0, 0)};
  }

  // Changez le type de retour : nb::ndarray -> nb::dict
  nb::dict render(int width, int height, int spp, int depth, int n_threads) {

    if (world.owned_objects.empty()) {
      world_bvh = std::make_shared<HittableList>();
    } else {
      world_bvh = std::make_shared<BVHNode>(world);
    }

    total_scanlines = height;
    completed_scanlines = 0;

    size_t num_pixels = (size_t)width * height;
    float *beauty = new float[num_pixels * 3];
    float *albedo = new float[num_pixels * 3];
    float *normal = new float[num_pixels * 3];

    try {
      {
        nb::gil_scoped_release release;
        if (n_threads > 0)
          omp_set_num_threads(n_threads);

#pragma omp parallel for schedule(dynamic)
        for (int j = 0; j < height; ++j) {
          for (int i = 0; i < width; ++i) {

            Vec3 acc_color(0, 0, 0);
            Vec3 acc_albedo(0, 0, 0);
            Vec3 acc_normal(0, 0, 0);

            for (int s = 0; s < spp; ++s) {
              auto u = (i + random_real()) / (width - 1);
              auto v = (j + random_real()) / (height - 1);
              Ray r = camera->get_ray(u, v);
              r.is_primary = true; // Important pour InvisibleLight

              // 1. Beauty Pass (Calcul complet)
              acc_color += ray_color(r, *world_bvh, lights, background.get(),
                                     depth, true);

              // 2. Feature Buffers (Premier impact seulement)
              HitRecord rec;
              if (world_bvh->hit(r, 0.001f,
                                 std::numeric_limits<Real>::infinity(), rec)) {
                acc_albedo += rec.mat_ptr->get_albedo(rec);
                // Mapping normale [-1, 1] -> [0, 1] pour l'image
                acc_normal += 0.5f * (unit_vector(rec.normal) + Vec3(1, 1, 1));
              }
              // Si on touche le fond, on laisse noir (0,0,0), OIDN gère très
              // bien ça.
            }

            int idx = ((height - 1 - j) * width + i) * 3;

            beauty[idx + 0] = acc_color.x() / spp;
            beauty[idx + 1] = acc_color.y() / spp;
            beauty[idx + 2] = acc_color.z() / spp;

            albedo[idx + 0] = acc_albedo.x() / spp;
            albedo[idx + 1] = acc_albedo.y() / spp;
            albedo[idx + 2] = acc_albedo.z() / spp;

            normal[idx + 0] = acc_normal.x() / spp;
            normal[idx + 1] = acc_normal.y() / spp;
            normal[idx + 2] = acc_normal.z() / spp;
          }
          completed_scanlines++;
        }
      }
    } catch (...) {
      delete[] beauty;
      delete[] albedo;
      delete[] normal;
      throw;
    }

    // Encapsulation pour Python (Memory Management)
    nb::capsule owner_b(beauty, [](void *p) noexcept { delete[] (float *)p; });
    nb::capsule owner_a(albedo, [](void *p) noexcept { delete[] (float *)p; });
    nb::capsule owner_n(normal, [](void *p) noexcept { delete[] (float *)p; });

    size_t shape[3] = {(size_t)height, (size_t)width, 3ul};

    nb::dict res;
    res["color"] = nb::ndarray<nb::numpy, float>(beauty, 3, shape, owner_b);
    res["albedo"] = nb::ndarray<nb::numpy, float>(albedo, 3, shape, owner_a);
    res["normal"] = nb::ndarray<nb::numpy, float>(normal, 3, shape, owner_n);

    return res;
  }

  // Retourne un Numpy Array (H, W, 3) directement utilisable par
  // OpenCV/Matplotlib
  nb::ndarray<nb::numpy, float> render_preview(int width, int height,
                                               int n_threads) {

    // 1. Vérifications de sécurité
    if (!camera) {
      throw std::runtime_error("Camera not set! Call set_camera first.");
    }

    // On s'assure que le BVH est construit (comme dans render())
    if (!world_bvh) {
      if (world.owned_objects.empty()) {
        world_bvh = std::make_shared<HittableList>();
      } else {
        world_bvh = std::make_shared<BVHNode>(world);
      }
    }

    size_t num_pixels = (size_t)width * height;
    float *buffer = new float[num_pixels * 3];

    try {
      // 2. Libérer le GIL Python pour permettre le multithreading fluide
      nb::gil_scoped_release release;

      if (n_threads > 0)
        omp_set_num_threads(n_threads);

#pragma omp parallel for schedule(dynamic)
      for (int j = 0; j < height; ++j) {
        for (int i = 0; i < width; ++i) {

          // UV centrés pixels
          auto u = (i + 0.5f) / width;
          auto v = (j + 0.5f) / height;

          Ray r = camera->get_ray(u, v);
          // Important : en preview, pas de shadow rays, on considère tout comme
          // primaire
          r.is_primary = true;

          HitRecord rec;
          Vec3 pixel_color;

          // Intersection rapide (BVH)
          if (world_bvh->hit(r, 0.001f, std::numeric_limits<Real>::infinity(),
                             rec)) {
            // --- MODE NORMALES ---
            // Visualisation de la géométrie (r,g,b) = (nx, ny, nz) mappé en
            // [0,1]
            pixel_color = 0.5f * (unit_vector(rec.normal) + Vec3(1, 1, 1));
          } else {
            // --- MODE FOND ---
            // Si une map HDRI est chargée, on l'utilise (rapide)
            if (background) {
              // 1. On échantillonne la HDRI (Mode 0 = Visible)
              Vec3 hdri_color = background->sample(r.dir, 0);

              // 2. TONE MAPPING SIMPLIFIÉ (Reinhard)
              // Les HDRIs ont des valeurs > 1.0 (le soleil peut être à 20.0).
              // Si on ne fait rien, tout sera blanc. On compresse doucement : x
              // / (1+x)
              pixel_color = Vec3(hdri_color.x() / (1.0f + hdri_color.x()),
                                 hdri_color.y() / (1.0f + hdri_color.y()),
                                 hdri_color.z() / (1.0f + hdri_color.z()));
            } else {
              // Fallback : Dégradé par défaut si pas de map chargée
              Vec3 unit_dir = unit_vector(r.dir);
              auto t = 0.5f * (unit_dir.y() + 1.0f);
              pixel_color = (1.0f - t) * Vec3(1.0f, 1.0f, 1.0f) +
                            t * Vec3(0.5f, 0.7f, 1.0f);
            }
          }

          // Écriture dans le buffer (Flip vertical pour compatibilité standard)
          int idx = ((height - 1 - j) * width + i) * 3;

          buffer[idx + 0] = pixel_color.x();
          buffer[idx + 1] = pixel_color.y();
          buffer[idx + 2] = pixel_color.z();
        }
      }
    } catch (...) {
      delete[] buffer;
      throw;
    }

    // 3. Encapsulation Nanobind (Zéro copie vers Python)
    nb::capsule owner(buffer, [](void *p) noexcept { delete[] (float *)p; });
    size_t shape[3] = {(size_t)height, (size_t)width, 3ul};

    return nb::ndarray<nb::numpy, float>(buffer, 3, shape, owner);
  }

  float get_progress() const {
    int t = total_scanlines.load();
    if (t == 0)
      return 0.0f;
    return (float)completed_scanlines.load() / t;
  }

  // Pick Focus Distance (Click-to-Focus)
  std::tuple<float, float, float, float>
  pick_focus_distance(int width, int height, int mouse_x, int mouse_y) {
    if (!camera)
      return {-1.0f, 0.0f, 0.0f, 0.0f};

    // Ensure BVH
    if (!world_bvh) {
      if (world.owned_objects.empty())
        world_bvh = std::make_shared<HittableList>();
      else
        world_bvh = std::make_shared<BVHNode>(world);
    }

    // UV calculé comme dans render_preview
    // Attention: OpenCV (et la plupart des UI) ont (0,0) en haut à gauche.
    // Notre moteur de rendu dans la boucle for j=0..h traite j=0 comme le haut
    // (cf render_preview). Donc mouse_y correspond bien à j.

    auto u = (mouse_x + 0.5f) / width;
    // CORRECTION: Inversion de l'axe Y pour correspondre à la caméra (v=0 en
    // bas, v=1 en haut) OpenCV mouse_y=0 (Haut) -> v=1
    auto v = 1.0f - ((mouse_y + 0.5f) / height);

    Ray r = camera->get_ray(u, v);
    r.is_primary = true;

    HitRecord rec;
    // On cherche l'intersection
    if (world_bvh->hit(r, 0.001f, std::numeric_limits<Real>::infinity(), rec)) {
      // FIX IMPORTANT: rec.t dépend de la longueur du vecteur direction du
      // rayon. Si la direction n'est pas normalisée (ce qui est le cas avec
      // focus_dist), rec.t change quand focus_dist change. Il faut retourner la
      // distance Euclidienne REELLE independent de la caméra.
      float euclidean_dist = (rec.p - r.orig).length();
      return {euclidean_dist, (float)rec.p.x(), (float)rec.p.y(),
              (float)rec.p.z()};
    }

    return {-1.0f, 0.0f, 0.0f, 0.0f}; // Sky / Void
  }
};

NB_MODULE(cpp_engine, m) {
  nb::class_<PyScene>(m, "Engine")
      .def(nb::init<>())
      .def("add_sphere", &PyScene::add_sphere, nb::arg("center"),
           nb::arg("radius"), nb::arg("mat_type"), nb::arg("color"),
           nb::arg("fuzz") = 0.0f, nb::arg("ir") = 1.5f)
      .def("add_invisible_sphere_light", &PyScene::add_invisible_sphere_light)
      .def("add_checker_sphere", &PyScene::add_checker_sphere)
      .def("add_quad", &PyScene::add_quad)
      .def("add_mesh", &PyScene::add_mesh,
           "Ajoute un mesh avec normales (Vertices Nx3, Indices Mx3, Normals "
           "Nx3)",
           nb::arg("vertices"), nb::arg("indices"), nb::arg("normals"),
           nb::arg("mat_type"), nb::arg("color"), nb::arg("fuzz") = 0.0f,
           nb::arg("ir") = 1.5f)
      .def("set_camera", &PyScene::set_camera)
      .def("set_environment", &PyScene::set_environment)
      .def("set_env_levels", &PyScene::set_env_levels,
           nb::arg("env_background_level"), // Ce que je vois
           nb::arg("env_direct_level"),     // Ce qui crée les ombres
           nb::arg("env_indirect_level") =
               1.0f) // Ce qui éclaire les coins (défaut 1.0)
      .def("get_progress", &PyScene::get_progress)
      .def("render", &PyScene::render, nb::arg("width"), nb::arg("height"),
           nb::arg("spp"), nb::arg("depth"), nb::arg("n_threads") = 0)
      .def("get_env_sun_info", &PyScene::get_env_sun_info)
      .def("pick_focus_distance", &PyScene::pick_focus_distance,
           "Retourne (dist, x, y, z) du premier obstacle sous la souris",
           nb::arg("width"), nb::arg("height"), nb::arg("mouse_x"),
           nb::arg("mouse_y"))
      .def("render_preview", &PyScene::render_preview,
           "Rendu temps réel (Normales)", nb::arg("width"), nb::arg("height"),
           nb::arg("n_threads") = 0);

  nb::class_<Vec3>(m, "Vec3")
      .def(nb::init<Real, Real, Real>())
      .def("x", &Vec3::x)
      .def("y", &Vec3::y)
      .def("z", &Vec3::z);
}