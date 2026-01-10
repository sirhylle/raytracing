#pragma once

#include "common.h"
#include "hittable.h"

// Structure pour stocker le résultat du rebond (Scatter)
struct ScatterRecord {
  Ray specular_ray; // Le rayon rebondissant
  bool is_specular; // Est-ce un miroir parfait/verre ? (Si oui, pas de sampling
                    // PDF)
  Vec3 attenuation; // La couleur absorbée (ex: 0.8 pour du gris)
};

// ===============================================================================================
// CLASSE DE BASE MATERIAL
// ===============================================================================================

class Material {
public:
  // Calcule comment le rayon rebondit
  virtual bool scatter(const Ray &r_in, const HitRecord &rec,
                       ScatterRecord &srec) const {
    return false;
  }

  // Probabilité de dispersion (pour le Monte Carlo)
  virtual Real scattering_pdf(const Ray &r_in, const HitRecord &rec,
                              const Ray &scattered) const {
    return 0;
  }

  // Lumière émise (pour les lampes)
  virtual Vec3 emit(const Ray &r_in, const HitRecord &rec, Real u, Real v,
                    const Vec3 &p) const {
    return Vec3(0, 0, 0);
  }

  // Est-ce transparent pour les rayons d'ombre (Shadow Rays) ?
  virtual bool is_transparent() const { return false; }

  // Couleur de base (utile pour les AOV / Denoiser)
  virtual Vec3 get_albedo(const HitRecord &rec) const { return Vec3(0, 0, 0); }

  virtual ~Material() = default;
};

// ===============================================================================================
// MATÉRIAUX STANDARDS
// ===============================================================================================

// 1. LAMBERTIAN (Mat, Diffus, Plâtre, Bois mat)
class Lambertian : public Material {
public:
  Vec3 albedo;
  Lambertian(const Vec3 &a) : albedo(a) {}

  virtual bool scatter(const Ray &r_in, const HitRecord &rec,
                       ScatterRecord &srec) const override {
    srec.is_specular = false;
    srec.attenuation = albedo;
    // Rebond aléatoire diffus (Loi du Cosinus)
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

// 2. METAL (Miroir flouté)
class Metal : public Material {
public:
  Vec3 albedo;
  Real fuzz;
  Metal(const Vec3 &a, Real f) : albedo(a), fuzz(f < 1 ? f : 1) {}

  virtual bool scatter(const Ray &r_in, const HitRecord &rec,
                       ScatterRecord &srec) const override {
    Vec3 reflected = reflect(unit_vector(r_in.dir), rec.normal);
    // On ajoute du flou (fuzz) dans une sphère unitaire
    srec.specular_ray =
        Ray(rec.p, reflected + fuzz * random_in_unit_sphere(), r_in.tm);
    srec.attenuation = albedo;
    srec.is_specular = true;
    // On vérifie qu'on ne rebondit pas à l'intérieur de l'objet par erreur
    return (dot(srec.specular_ray.dir, rec.normal) > 0);
  }

  virtual Vec3 get_albedo(const HitRecord &rec) const override {
    return albedo;
  }
};

// 3. DIELECTRIC (Verre, Eau, Diamant)
class Dielectric : public Material {
public:
  Real ir; // Indice de réfraction (1.5 pour verre, 2.4 diamant)
  Vec3 tint;

  Dielectric(Real index_of_refraction,
             const Vec3 &tint_color = Vec3(1.0f, 1.0f, 1.0f))
      : ir(index_of_refraction), tint(tint_color) {}

  virtual bool is_transparent() const override { return true; }

  virtual bool scatter(const Ray &r_in, const HitRecord &rec,
                       ScatterRecord &srec) const override {
    srec.attenuation = tint;
    srec.is_specular = true; // Pas de sampling PDF pour le verre (trop complexe
                             // pour l'instant)
    Real refraction_ratio = rec.front_face ? (1.0f / ir) : ir;

    Vec3 unit_direction = unit_vector(r_in.dir);
    Real cos_theta = std::fmin(dot(-unit_direction, rec.normal), 1.0f);
    Real sin_theta = std::sqrt(1.0f - cos_theta * cos_theta);

    bool cannot_refract = refraction_ratio * sin_theta > 1.0f;
    Vec3 direction;

    // Approximation de Schlick pour la réflectivité selon l'angle
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

// ===============================================================================================
// MATÉRIAUX SPÉCIAUX
// ===============================================================================================

// 4. DAMIER (Checkerboard)
class LambertianChecker : public Material {
public:
  Vec3 albedo1;
  Vec3 albedo2;
  Real scale;

  LambertianChecker(const Vec3 &a1, const Vec3 &a2, Real s)
      : albedo1(a1), albedo2(a2), scale(s) {}

  virtual Vec3 get_albedo(const HitRecord &rec) const override {
    // Logique XOR pour le damier 3D
    const double s = scale;
    int ix = static_cast<int>(std::floor(s * rec.p.x()));
    int iy = static_cast<int>(std::floor(s * rec.p.y()));
    int iz = static_cast<int>(std::floor(s * rec.p.z()));

    // Fix sol plat : si la normale est verticale, on ignore Y pour éviter le
    // Z-fighting visuel
    bool isPlanar = std::abs(rec.normal.y()) > 0.9;
    bool isOdd;

    if (isPlanar)
      isOdd = (ix ^ iz) & 1;
    else
      isOdd = (ix ^ iy ^ iz) & 1;

    return isOdd ? albedo2 : albedo1;
  }

  virtual bool scatter(const Ray &r_in, const HitRecord &rec,
                       ScatterRecord &srec) const override {
    srec.is_specular = false;
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

// 5. LUMIÈRE DIFFUSE (Lightbulb)
class DiffuseLight : public Material {
public:
  Vec3 emit_color;
  DiffuseLight(const Vec3 &c) : emit_color(c) {}

  virtual bool scatter(const Ray &r_in, const HitRecord &rec,
                       ScatterRecord &srec) const override {
    return false; // Une lumière n'a pas de surface mate, elle absorbe ou émet
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

// 6. LUMIÈRE INVISIBLE (Faux soleil)
class InvisibleLight : public Material {
public:
  Vec3 emit_color;
  InvisibleLight(const Vec3 &c) : emit_color(c) {}

  virtual bool is_transparent() const override { return true; }

  virtual bool scatter(const Ray &r_in, const HitRecord &rec,
                       ScatterRecord &srec) const override {
    // Si activé : On bloque les reflets (rayons secondaires) pour qu'ils voient
    // la lumière
    if (VISIBLE_IN_REFLECTIONS && !r_in.is_primary)
      return false;

    // Sinon (Caméra ou Shadow Ray) : On laisse passer comme du verre parfait
    srec.is_specular = true;
    srec.specular_ray = Ray(rec.p + 0.001f * r_in.dir, r_in.dir, r_in.tm,
                            r_in.is_shadow, r_in.is_primary);
    srec.attenuation = Vec3(1.0f, 1.0f, 1.0f);
    return true;
  }

  virtual Vec3 emit(const Ray &r_in, const HitRecord &rec, Real u, Real v,
                    const Vec3 &p) const override {
    bool should_emit = false;
    // Toujours émettre pour les ombres (c'est le but !)
    if (r_in.is_shadow)
      should_emit = true;
    // Émettre pour les reflets si configuré
    if (VISIBLE_IN_REFLECTIONS && !r_in.is_primary)
      should_emit = true;

    return should_emit ? emit_color : Vec3(0, 0, 0);
  }
};

// 7. PLASTIC (Diffus + Vernis brillant)
class Plastic : public Material {
public:
  Vec3 albedo;
  Real ir;
  Real fuzz;

  Plastic(const Vec3 &a, Real index_of_refraction, Real f)
      : albedo(a), ir(index_of_refraction), fuzz(f) {}

  virtual bool scatter(const Ray &r_in, const HitRecord &rec,
                       ScatterRecord &srec) const override {
    // Calcul Fresnel (Vernis)
    Vec3 unit_direction = unit_vector(r_in.dir);
    Real cos_theta = std::fmin(dot(-unit_direction, rec.normal), 1.0f);
    Real r0 = (1.0f - ir) / (1.0f + ir);
    r0 = r0 * r0;
    Real reflect_prob = r0 + (1.0f - r0) * std::pow((1.0f - cos_theta), 5);

    if (random_real() < reflect_prob) {
      // Rebond spéculaire (Vernis blanc)
      Vec3 reflected = reflect(unit_direction, rec.normal);
      srec.is_specular = true;
      srec.specular_ray =
          Ray(rec.p, reflected + fuzz * random_in_unit_sphere(), r_in.tm);
      srec.attenuation = Vec3(1.0f, 1.0f, 1.0f);
      return true;
    } else {
      // Rebond diffus (Base colorée)
      srec.is_specular =
          true; // On triche un peu ici pour simplifier le path tracing
      srec.attenuation = albedo;
      srec.specular_ray =
          Ray(rec.p, unit_vector(rec.normal + random_unit_vector()), r_in.tm);
      return true;
    }
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