#pragma once

#include <algorithm>
#include <cmath>
#include <iostream>
#include <limits>
#include <memory>
#include <random>
#include <vector>

// ===============================================================================================
// CONFIGURATION GLOBALE & CONSTANTES
// ===============================================================================================

using Real = float;
const Real PI = 3.1415926535897932385f;
const Real INFINITY_REAL = std::numeric_limits<Real>::infinity();

// 1. Gestion du faux soleil (InvisibleLight) dans les reflets
const bool VISIBLE_IN_REFLECTIONS = true;

// 2. Intensité de l'ombre des objets transparents (Transparent Shadows)
// Facteur de transmission pour les fausses caustiques.
// 1.0f = Transmission complète (Ombre très claire / colorée). Réaliste pour du
// verre fin. 0.0f = Pas de transmission (Ombre noire). Comme un objet opaque.
//
// RECOMMANDATIONS :
// - 0.50f - 0.70f : Rendu "artistique" avec des ombres bien visibles mais
// transparentes.
// - 0.80f - 0.95f : Rendu réaliste pour du verre clair (laisse passer presque
// toute la lumière).
const Real DIELECTRIC_SHADOW_TRANSMISSION = 0.8f;

// 3. Epsilon pour éviter l'acné (Self-Intersection)
// Offset pour éviter qu'un rayon ne re-intersecte la surface d'où il part.
//
// COMPROMIS :
// - Trop petit : "Shadow Acne" (points noirs sur la surface).
// - Trop grand : "Peter Panning" (l'ombre se détache de l'objet) ou fuites de
// lumière.
//
// IMPACT DE L'ÉCHELLE (SCALE) :
// La valeur idéale dépend de la taille moyenne des objets dans la scène
// (~1/10000).
// - Scène "Unit" (Objets ~1.0, Dist ~10.0)      : EPSILON ~ 0.001f (ou 1e-4) ->
// Standard.
// - Scène "Macro" (Objets ~100.0, Dist ~1000.0) : EPSILON ~ 0.1f -> Sinon
// erreurs de précision float.
const Real EPSILON = 0.001f;

// 4. Gestion des Fireflies (Lucioles)
// Limite l'intensité maximale d'un échantillon indirect pour réduire le bruit
// (variance).
//
// COMPROMIS :
// - Trop petit : Image stable rapidement mais terne (perte d'énergie, éclats
// étouffés).
// - Trop grand : Physiquement correct (HDR) mais risque de pixels blancs
// (fireflies) persistants.
//
// RECOMMANDATIONS :
// - 10.0f - 20.0f   : Clamp agressif, image très propre rapidement.
// - 50.0f - 100.0f  : Bon compromis qualité/temps.
// - > 1000.0f       : Virtuellement désactivé.
const Real FIREFLY_CLAMP_LIMIT = 100.0f;

// Utilitaire de compression douce (Tone mapping local)
inline Real soft_clamp(Real x, Real limit) { return x * limit / (x + limit); }

// ===============================================================================================
// UTILITAIRES ALÉATOIRES (Thread Safe)
// ===============================================================================================

inline Real random_real() {
  static thread_local std::mt19937 generator{std::random_device{}()};
  static thread_local std::uniform_real_distribution<Real> distribution(0.0f,
                                                                        1.0f);
  return distribution(generator);
}

inline Real random_real(Real min, Real max) {
  return min + (max - min) * random_real();
}

// ===============================================================================================
// VECTEURS (Vec3)
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

  Vec3 &operator/=(Real t) { return *this *= (1.0f / t); }

  Real length_squared() const {
    return e[0] * e[0] + e[1] * e[1] + e[2] * e[2];
  }
  Real length() const { return std::sqrt(length_squared()); }
};

// Opérateurs Vec3
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

// Helpers Géométriques
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
// RAYON (Ray)
// ===============================================================================================

struct Ray {
  Vec3 orig;
  Vec3 dir;
  Vec3 inv_dir;
  Real tm;         // Temps (pour le motion blur)
  bool is_shadow;  // Optimisation: est-ce un rayon d'ombre ?
  bool is_primary; // Est-ce un rayon lancé depuis la caméra ?

  Ray() : tm(0), is_shadow(false), is_primary(false) {}
  Ray(const Vec3 &origin, const Vec3 &direction, Real time = 0.0f,
      bool shadow = false, bool primary = false)
      : orig(origin), dir(direction), tm(time), is_shadow(shadow),
        is_primary(primary) {
    // On pré-calcule l'inverse pour accélérer le test AABB
    inv_dir = Vec3(1.0f / dir.x(), 1.0f / dir.y(), 1.0f / dir.z());
  }

  Vec3 at(Real t) const { return orig + t * dir; }
};

// ===============================================================================================
// BOUNDING BOX (AABB)
// ===============================================================================================

struct AABB {
  Vec3 min, max;

  AABB() {}
  AABB(const Vec3 &a, const Vec3 &b) : min(a), max(b) {}

  // Méthode "Slab" optimisée (SIMD friendly)
  bool hit(const Ray &r, Real t_min, Real t_max) const {
    for (int a = 0; a < 3; a++) {
      auto invD = r.inv_dir[a];
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

inline AABB surrounding_box(const AABB &box0, const AABB &box1) {
  Vec3 small(std::fmin(box0.min.x(), box1.min.x()),
             std::fmin(box0.min.y(), box1.min.y()),
             std::fmin(box0.min.z(), box1.min.z()));
  Vec3 big(std::fmax(box0.max.x(), box1.max.x()),
           std::fmax(box0.max.y(), box1.max.y()),
           std::fmax(box0.max.z(), box1.max.z()));
  return AABB(small, big);
}

// ===============================================================================================
// BASE ORTHONORMÉE (ONB)
// ===============================================================================================
// Permet de passer de l'espace Local (Tangent Space) à l'espace Monde.
// Indispensable pour le sampling GGX et le Normal Mapping.
struct ONB {
  Vec3 axis[3];

  ONB() {}

  Vec3 operator[](int i) const { return axis[i]; }
  Vec3 &operator[](int i) { return axis[i]; }

  Vec3 u() const { return axis[0]; }
  Vec3 v() const { return axis[1]; }
  Vec3 w() const { return axis[2]; }

  // Transforme un vecteur local (ex: échantillon GGX) vers le monde
  Vec3 local(Real a, Real b, Real c) const {
    return a * u() + b * v() + c * w();
  }

  Vec3 local(const Vec3 &a) const {
    return a.x() * u() + a.y() * v() + a.z() * w();
  }

  // Construit la base à partir de la normale (Z)
  // Méthode de Duff et al. (Building an Orthonormal Basis, Revisited)
  // Plus robuste que les anciennes méthodes basées sur cross(n, up).
  void build_from_w(const Vec3 &n) {
    axis[2] = unit_vector(n);
    Vec3 a = (std::fabs(w().x()) > 0.9f) ? Vec3(0, 1, 0) : Vec3(1, 0, 0);
    axis[1] = unit_vector(cross(w(), a));
    axis[0] = cross(w(), v());
  }
};

// ===============================================================================================
// MATRICE 4x4 (Pour les Instances)
// ===============================================================================================

struct Matrix4 {
  Real m[4][4];

  Matrix4() {
    for (int i = 0; i < 4; i++)
      for (int j = 0; j < 4; j++)
        m[i][j] = (i == j) ? 1.0f : 0.0f;
  }

  // Transforme un Point (w=1) -> applique Translation
  Vec3 point(const Vec3 &p) const {
    Real x = p.x(), y = p.y(), z = p.z();
    return Vec3(m[0][0] * x + m[0][1] * y + m[0][2] * z + m[0][3],
                m[1][0] * x + m[1][1] * y + m[1][2] * z + m[1][3],
                m[2][0] * x + m[2][1] * y + m[2][2] * z + m[2][3]);
  }

  // Transforme un Vecteur (w=0) -> ignore Translation
  Vec3 vector(const Vec3 &v) const {
    Real x = v.x(), y = v.y(), z = v.z();
    return Vec3(m[0][0] * x + m[0][1] * y + m[0][2] * z,
                m[1][0] * x + m[1][1] * y + m[1][2] * z,
                m[2][0] * x + m[2][1] * y + m[2][2] * z);
  }

  Matrix4 transpose() const {
    Matrix4 res;
    for (int i = 0; i < 4; i++)
      for (int j = 0; j < 4; j++)
        res.m[i][j] = m[j][i];
    return res;
  }
};

// ===============================================================================================
// UTILITAIRES POST-PROCESS (Tone Mapping)
// ===============================================================================================

// Narkowicz 2015 / ACES approximation (Même qu'en Python)
inline Vec3 aces_filmic(const Vec3 &x) {
  Real a = 2.51f;
  Real b = 0.03f;
  Real c = 2.43f;
  Real d = 0.59f;
  Real e = 0.14f;

  // Application composante par composante
  Real r = (x.x() * (a * x.x() + b)) / (x.x() * (c * x.x() + d) + e);
  Real g = (x.y() * (a * x.y() + b)) / (x.y() * (c * x.y() + d) + e);
  Real bl = (x.z() * (a * x.z() + b)) / (x.z() * (c * x.z() + d) + e);

  // Clamp 0..1 par sécurité
  return Vec3(std::fmin(std::fmax(r, 0.0f), 1.0f),
              std::fmin(std::fmax(g, 0.0f), 1.0f),
              std::fmin(std::fmax(bl, 0.0f), 1.0f));
};