#pragma once

// ===============================================================================================
// MODULE: MATERIALS (PBR / GGX)
// ===============================================================================================
//
// DESCRIPTION:
//   Physically Based Rendering (PBR) Materials based on the Cook-Torrance BRDF.
//   Replaces legacy Lambertian/Metal materials with a unified model.
//
//   FEATURES:
//   - Albedo    : Base Color.
//   - Metallic  : 0.0 (Dielectric) -> 1.0 (Conductor).
//   - Roughness : 0.0 (Mirror) -> 1.0 (Rough/Matte).
//   - IOR       : Index of Refraction (for dielectrics).
//
// ===============================================================================================

#include "common.h"
#include "hittable.h"

// Structure pour stocker le résultat du rebond (Scatter)
struct ScatterRecord {
  Ray specular_ray; // Le rayon rebondissant
  bool is_specular; // Si Vrai, on ignore le NEE (Miroir parfait). Si Faux, on
                    // peut sampler (Rough).
  Vec3 attenuation; // La couleur absorbée ou le throughput BSDF
  Real roughness;   // New: Roughness of the bounce (0=Mirror, 1=Matte)
};

// ===============================================================================================
// HELPER MATHS PBR (COOK-TORRANCE)
// ===============================================================================================

// EXACT FRESNEL FOR DIELECTRICS (Unpolarized)
// Returns reflection coefficient [0..1]
inline Real fresnel_dielectric_exact(Real cos_theta_i, Real ior_ratio) {
  // cos_theta_i is clamped to [0,1] before calling
  Real sin2_theta_t =
      ior_ratio * ior_ratio * (1.0f - cos_theta_i * cos_theta_i);

  // Total Internal Reflection
  if (sin2_theta_t > 1.0f)
    return 1.0f;

  Real cos_theta_t = std::sqrt(1.0f - sin2_theta_t);

  Real r_parl = (ior_ratio * cos_theta_i - cos_theta_t) /
                (ior_ratio * cos_theta_i + cos_theta_t);
  Real r_perp = (cos_theta_i - ior_ratio * cos_theta_t) /
                (cos_theta_i + ior_ratio * cos_theta_t);

  return 0.5f * (r_parl * r_parl + r_perp * r_perp);
}

// Schlick fallback for conductors (Metals) because we use F0 approximation
// there
inline Vec3 schlick_fresnel_color(Real cosine, const Vec3 &F0) {
  return F0 + (Vec3(1, 1, 1) - F0) * std::pow(1.0f - cosine, 5.0f);
}

// Distribution GGX/Trowbridge-Reitz
// D(h) = alpha^2 / (pi * ((n.h)^2 * (alpha^2 - 1) + 1)^2)
inline Real ndf_ggx(Real cos_theta_h, Real roughness) {
  Real alpha = roughness * roughness;
  if (alpha < 1e-6f)
    alpha = 1e-6f; // Prevent alpha=0 singularity
  Real alpha2 = alpha * alpha;
  Real den = cos_theta_h * cos_theta_h * (alpha2 - 1.0f) + 1.0f;
  return alpha2 / (PI * den * den + 1e-10f); // Safety epsilon
}

// ... (Geometry functions unchanged) ...

// ...

// Geometry Smith (Schlick-GGX)
// k = alpha^2 / 2
inline Real geometry_schlick_ggx(Real cos_theta, Real k) {
  return cos_theta / (cos_theta * (1.0f - k) + k);
}

inline Real geometry_smith(Real cos_theta_n, Real cos_theta_v, Real roughness) {
  Real alpha = roughness * roughness;
  Real k = alpha / 2.0f;
  Real ggx1 = geometry_schlick_ggx(cos_theta_n, k);
  Real ggx2 = geometry_schlick_ggx(cos_theta_v, k);
  return ggx1 * ggx2;
}

// Generates a Half-Vector contained in the GGX distribution
// Returns H in vector space (must be transformed by ONB)
inline Vec3 sample_ggx_ndf(const Vec3 &n, Real roughness) {
  Real r1 = random_real();
  Real r2 = random_real();
  Real alpha = roughness * roughness;

  Real phi = 2.0f * PI * r1;
  Real cos_theta =
      std::sqrt((1.0f - r2) / (1.0f + (alpha * alpha - 1.0f) * r2));
  Real sin_theta = std::sqrt(1.0f - cos_theta * cos_theta);

  // Spherical to Cartesian (in Tangent Space)
  return Vec3(sin_theta * std::cos(phi), sin_theta * std::sin(phi), cos_theta);
}

// Cosine Weighted Hemisphere Sampling
inline Vec3 sample_cosine_weighted(const Vec3 &n) {
  Real r1 = random_real();
  Real r2 = random_real();
  Real phi = 2.0f * PI * r1;
  Real sqrt_r2 = std::sqrt(r2);
  Vec3 local(std::cos(phi) * sqrt_r2, std::sin(phi) * sqrt_r2,
             std::sqrt(1.0f - r2));

  ONB onb;
  onb.build_from_w(n);
  return onb.local(local);
}

// ===============================================================================================
// CLASSE DE BASE MATERIAL
// ===============================================================================================

class Material {
public:
  virtual bool scatter(const Ray &r_in, const HitRecord &rec,
                       ScatterRecord &srec) const {
    return false;
  }

  virtual Vec3 eval_bsdf(const Ray &r_in, const HitRecord &rec,
                         const Vec3 &scattered_dir) const {
    return Vec3(0, 0, 0); // Default: No scattering evaluation
  }

  virtual Real scattering_pdf(const Ray &r_in, const HitRecord &rec,
                              const Ray &scattered) const {
    Real cos = dot(rec.normal, unit_vector(scattered.dir));
    return cos < 0 ? 0 : cos / PI;
  }

  // struct to hold separated BSDF components
  struct BsdfComponents {
    Vec3 diffuse;
    Vec3 specular;
  };

  virtual BsdfComponents eval_bsdf_components(const Ray &r_in,
                                              const HitRecord &rec,
                                              const Vec3 &scattered_dir) const {
    // Default fallback: everything is diffuse
    Vec3 total = eval_bsdf(r_in, rec, scattered_dir);
    return {total, Vec3(0, 0, 0)};
  }

  virtual Vec3 emit(const Ray &r_in, const HitRecord &rec, Real u, Real v,
                    const Vec3 &p) const {
    return Vec3(0, 0, 0);
  }

  virtual bool is_transparent() const { return false; }

  // NEW: Calculates absorption/throughput for Shadow Rays
  virtual Vec3 shadow_attenuation(const Ray &r_in, const HitRecord &rec) const {
    return Vec3(0, 0, 0);
  }

  virtual Vec3 get_albedo(const HitRecord &rec) const { return Vec3(0, 0, 0); }
  virtual ~Material() = default;
};

// ===================================
// PBR MATERIAL (Standard Surface / GGX)
// ===================================

class GgxMaterial : public Material {
public:
  Vec3 albedo;
  Real roughness;    // 0=Smooth, 1=Rough
  Real metallic;     // 0=Dielectric, 1=Metal
  Real ior;          // Index of Refraction (for Dielectric)
  Real transmission; // 0=Opaque, 1=Transmissive

  GgxMaterial(const Vec3 &a, Real r, Real m, Real i = 1.5f, Real t = 0.0f)
      : albedo(a), roughness(r), metallic(m), ior(i), transmission(t) {}

  virtual Vec3 get_albedo(const HitRecord &rec) const override {
    return albedo;
  }

  virtual bool is_transparent() const override { return transmission > 0.001f; }

  virtual Vec3 shadow_attenuation(const Ray &r_in,
                                  const HitRecord &rec) const override {
    // Volumetric Absorption (Beer's Law) + Fresnel + Metallic Blend

    // 1. Fresnel Loss (Reflection)
    Vec3 unit_direction = unit_vector(r_in.dir);
    Real cos_theta = std::fmin(dot(-unit_direction, rec.normal), 1.0f);
    Real refraction_ratio = rec.front_face ? (1.0f / ior) : ior;
    Real R = fresnel_dielectric_exact(cos_theta, refraction_ratio);

    // 2. Base Throughput
    // Transmission factor reduced by reflection (1-R) and metal opacity (1-M)
    Vec3 throughput =
        Vec3(1.0f, 1.0f, 1.0f) * transmission * (1.0f - R) * (1.0f - metallic);

    // 3. Volumetric Absorption (Beer's Law)
    // Only applied when EXITING the medium (Back Face), as 'rec.t' represents
    // the distance traveled inside.
    if (!rec.front_face) {
      // We assume Albedo represents the color at distance = 1.0 unit
      // Absorption = Albedo^Distance
      throughput.e[0] *= std::pow(albedo.x(), rec.t);
      throughput.e[1] *= std::pow(albedo.y(), rec.t);
      throughput.e[2] *= std::pow(albedo.z(), rec.t);
    }
    // If Entering (Front Face), absorption is 0, just Fresnel/Base applied.

    return throughput;
  }

  // New Evaluation function for NEE (BSDF * cos_theta)
  virtual BsdfComponents
  eval_bsdf_components(const Ray &r_in, const HitRecord &rec,
                       const Vec3 &scattered_dir) const override {
    Vec3 l = unit_vector(scattered_dir);
    Vec3 v = unit_vector(-r_in.dir);
    Vec3 n = rec.normal;

    Real n_dot_l = dot(n, l);
    Real n_dot_v = dot(n, v);

    // Below horizon -> 0
    if (n_dot_l <= 0.0f || n_dot_v <= 0.0f)
      return {Vec3(0, 0, 0), Vec3(0, 0, 0)};

    // 1. Transmission ignored in NEE
    if (transmission > 0.999f && metallic < 0.001f) {
      return {Vec3(0, 0, 0), Vec3(0, 0, 0)};
    }

    // 2. Diffuse / Specular Mix

    // Calculate Fresnel
    Vec3 F;
    Vec3 h = unit_vector(v + l);
    Real v_dot_h = std::max(dot(v, h), 0.0f);

    if (metallic > 0.0f) {
      // Conductor: Use Schlick with F0 = Albedo
      Vec3 F0 = albedo;
      F = schlick_fresnel_color(v_dot_h, F0);
    } else {
      // Dielectric: Use Exact Fresnel
      Real F_diel = fresnel_dielectric_exact(v_dot_h, 1.0f / ior);
      F = Vec3(F_diel, F_diel, F_diel);
    }

    // GGX Terms
    Real n_dot_h = std::max(dot(n, h), 0.0f);
    Real D = ndf_ggx(n_dot_h, roughness);
    Real G = geometry_smith(n_dot_l, n_dot_v, roughness);

    // Cook-Torrance Specular BRDF * cos(theta_l)
    Vec3 specular = (D * G * F) / (4.0f * std::max(n_dot_v, 0.0001f));

    // Diffuse Term (Lambert)
    // Energy conservation: kD = (1-F)(1-Metal).
    Vec3 kD = (Vec3(1.0f, 1.0f, 1.0f) - F) * (1.0f - metallic);
    Vec3 diffuse = (kD * albedo / PI) * n_dot_l;

    return {diffuse, specular};
  }

  // Legacy kept for compatibility if needed (but we will switch renderer.h)
  virtual Vec3 eval_bsdf(const Ray &r_in, const HitRecord &rec,
                         const Vec3 &scattered_dir) const override {
    auto comps = eval_bsdf_components(r_in, rec, scattered_dir);
    return comps.diffuse + comps.specular;
  }

  // PDF Calculation for MIS
  virtual Real scattering_pdf(const Ray &r_in, const HitRecord &rec,
                              const Ray &scattered) const override {
    Vec3 n = rec.normal;
    Vec3 v = unit_vector(-r_in.dir);
    Vec3 l = unit_vector(scattered.dir);
    Real n_dot_l = dot(n, l);
    Real n_dot_v = dot(n, v);
    if (n_dot_v < 0)
      n_dot_v = 0;

    if (n_dot_l <= 0)
      return 0;

    // Calculate Mix Probability (Must match scatter!)
    Real F_lum = 0.0f;
    if (metallic > 0.0f) {
      Vec3 F = schlick_fresnel_color(n_dot_v, albedo);
      F_lum = (F.x() + F.y() + F.z()) / 3.0f;
    } else {
      F_lum = fresnel_dielectric_exact(n_dot_v, 1.0f / ior);
    }

    Real prob_spec = (1.0f - metallic) * F_lum + metallic;

    // Limits
    if (prob_spec < 0.0f)
      prob_spec = 0.0f;
    if (prob_spec > 1.0f)
      prob_spec = 1.0f;
    // Note: In scatter we check for effectively zero/one.
    // If very rough or very smooth?
    if (roughness < 0.001f)
      return 0; // Dirac delta, pdf is infinite/undefined for specific ray

    // Diffuse PDF
    Real pdf_diffuse = (metallic > 0.99f) ? 0.0f : (n_dot_l / PI);

    // Specular PDF (GGX)
    // p_h = D * cos_theta_h
    // p_l = p_h / (4 * v.h)
    Vec3 h = unit_vector(v + l);
    Real n_dot_h = std::max(dot(n, h), 0.0f);
    Real v_dot_h = std::max(dot(v, h), 0.0f);

    Real D = ndf_ggx(n_dot_h, roughness);
    Real safe_v_dot_h = std::max(v_dot_h, 1e-6f);
    Real pdf_spec = D * n_dot_h / (4.0f * safe_v_dot_h);

    return prob_spec * pdf_spec + (1.0f - prob_spec) * pdf_diffuse;
  }

  virtual bool scatter(const Ray &r_in, const HitRecord &rec,
                       ScatterRecord &srec) const override {

    // 1. Transmission (Glass)
    Real eff_transmission = transmission * (1.0f - metallic);

    if (eff_transmission > 0.0f && random_real() < eff_transmission) {
      srec.is_specular = true;
      srec.attenuation = albedo;

      Real refraction_ratio = rec.front_face ? (1.0f / ior) : ior;
      Vec3 unit_direction = unit_vector(r_in.dir);

      // GGX Microfacet Refraction (The Pro Way)
      // Instead of refracting via the geometric normal 'rec.normal',
      // we sample a microfacet normal 'h' based on roughness.

      Vec3 h;
      if (roughness < 0.001f) {
        h = rec.normal;
        srec.roughness = 0.0f;
      } else {
        // Sample GGX Normal using ONB
        ONB onb;
        onb.build_from_w(rec.normal);
        Vec3 local_h = sample_ggx_ndf(rec.normal, roughness);
        h = onb.local(local_h);
        srec.roughness = roughness;
      }

      // Ensure h is in the same hemisphere as proper normal relative to ray (?)
      // Actually standard GGX sampling gives h in +Z.
      // If ray is coming from inside, we might need to flip logic?
      // Standard Refract function handles normal direction usually.

      // Calculate Fresnel on Microfacet H
      Real cos_theta = std::fmin(dot(-unit_direction, h), 1.0f);
      Real F = fresnel_dielectric_exact(cos_theta, refraction_ratio);

      Vec3 direction;
      // Note: fresnel_dielectric_exact handles TIR inside (returns 1.0)

      // Stochastic Fresnel choice
      if (random_real() < F) {
        // Reflect off microfacet
        direction = reflect(unit_direction, h);
      } else {
        // Refract via microfacet
        direction = refract(unit_direction, h, refraction_ratio);
        // If refract returns (0,0,0) due to TIR (though fresnel should have
        // caught it), fallback to reflect
        if (direction.length_squared() < 1e-6f)
          direction = reflect(unit_direction, h);
      }

      srec.specular_ray = Ray(rec.p, direction, r_in.tm);
      return true;
    }

    // 2. Opaque PBR Setup
    // NO THRESHOLDS. ALWAYS FALSE (unless delta).
    srec.is_specular = false;

    // Pass roughness for next bounce logic
    srec.roughness = roughness;

    // Exception: If Roughness is virtually zero.
    if (roughness < 0.001f) {
      srec.is_specular = true;
    }

    Vec3 v = unit_vector(-r_in.dir);
    Real n_dot_v = dot(rec.normal, v);
    if (n_dot_v < 0)
      n_dot_v = 0;

    // Specular Probability
    // Dielectric: Exact Fresnel at current angle
    // Metal: Schlick with Albedo
    Real F_lum = 0.0f;

    if (metallic > 0.0f) {
      Vec3 F_schlick = schlick_fresnel_color(n_dot_v, albedo);
      F_lum = (F_schlick.x() + F_schlick.y() + F_schlick.z()) / 3.0f;
    } else {
      // Dielectric
      F_lum = fresnel_dielectric_exact(n_dot_v, 1.0f / ior);
    }

    // Mix
    Real prob_spec = (1.0f - metallic) * F_lum +
                     metallic; // Metal is 100% specular lobe (colored)

    // 3. Stochastic Choice
    if (random_real() < prob_spec) {
      // --- SPECULAR PATH (GGX) ---
      ONB onb;
      onb.build_from_w(rec.normal);

      if (roughness < 0.001f) {
        // Mirror
        Vec3 reflected = reflect(unit_vector(r_in.dir), rec.normal);
        srec.specular_ray = Ray(rec.p, reflected, r_in.tm);
        srec.is_specular = true;
        // Weight = F / p = F / F = 1.
        // Actually for metal F is colored.
        if (metallic > 0.0f)
          srec.attenuation = schlick_fresnel_color(n_dot_v, albedo) / prob_spec;
        else
          srec.attenuation =
              Vec3(1, 1, 1) *
              (fresnel_dielectric_exact(n_dot_v, 1.0f / ior) / prob_spec);
        return true;
      }

      Vec3 local_h = sample_ggx_ndf(rec.normal, roughness);
      Vec3 h = onb.local(local_h);
      Vec3 l = reflect(-v, h);

      if (dot(l, rec.normal) <= 0.0f)
        return false;

      srec.specular_ray = Ray(rec.p, l, r_in.tm);

      // BRDF Terms
      Real n_dot_l = std::max(dot(rec.normal, l), 0.0001f);
      Real n_dot_h = std::max(dot(rec.normal, h), 0.0001f);
      Real v_dot_h = std::max(dot(v, h), 0.0001f);

      Vec3 F;
      if (metallic > 0.0f)
        F = schlick_fresnel_color(v_dot_h, albedo);
      else {
        Real f = fresnel_dielectric_exact(v_dot_h, 1.0f / ior);
        F = Vec3(f, f, f);
      }

      Real G = geometry_smith(n_dot_l, std::max(n_dot_v, 0.0001f), roughness);

      // Weight = (F * G * v.h) / (n.v * n.h)
      // Dividing by prob_spec
      Vec3 spec_weight =
          F * G * v_dot_h / (std::max(n_dot_v, 0.0001f) * n_dot_h);
      srec.attenuation = spec_weight / prob_spec;

    } else {
      // --- DIFFUSE PATH ---
      if (metallic > 0.99f)
        return false;

      Vec3 diff_dir = sample_cosine_weighted(rec.normal);
      srec.specular_ray = Ray(rec.p, diff_dir, r_in.tm);

      // kD = (1-F)(1-M)
      // F is approximated by F_lum/prob used for splitting?
      // Standard is to just return Albedo and assume split handles kD/kS
      // separation approximately Exact PBR: weight = (1-F) * Albedo / (1 -
      // prob_spec)

      // If we used F_lum to split, then (1-prob) is approx (1-F).
      // So Albedo is technically correct.
      // But we must multiply by (1-Metallic).

      srec.attenuation = albedo * (1.0f - metallic); // / (1-prob) ?
      // If prob is small, we are here often. weight matches.
      // If prob is large, we are here rarely. weight should be higher?
      // Let's rely on standard Albedo return for now which assumes split
      // variance reduction.

      // Wait, if prob_spec=0.9 and we land here (0.1 chance), we should boost
      // the signal?
      srec.attenuation = srec.attenuation / (1.0f - prob_spec);
    }

    return true;
  }
};

// ===============================================================================================
// MATÉRIAUX SPÉCIAUX (Compatibilité)
// ===============================================================================================

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

class InvisibleLight : public Material {
public:
  Vec3 emit_color;
  InvisibleLight(const Vec3 &c) : emit_color(c) {}
  virtual bool is_transparent() const override { return true; }
  virtual Vec3 shadow_attenuation(const Ray &r_in,
                                  const HitRecord &rec) const override {
    return Vec3(1.0f, 1.0f, 1.0f);
  }
  virtual bool scatter(const Ray &r_in, const HitRecord &rec,
                       ScatterRecord &srec) const override {
    if (VISIBLE_IN_REFLECTIONS && !r_in.is_primary && !r_in.is_shadow)
      return false;
    srec.is_specular = true;
    srec.specular_ray = Ray(rec.p + 0.001f * r_in.dir, r_in.dir, r_in.tm,
                            r_in.is_shadow, r_in.is_primary);
    srec.attenuation = Vec3(1.0f, 1.0f, 1.0f);
    srec.roughness = 0.0f; // Perfect transmission/specular
    return true;
  }
  virtual Vec3 emit(const Ray &r_in, const HitRecord &rec, Real u, Real v,
                    const Vec3 &p) const override {
    bool should_emit = false;
    if (r_in.is_shadow)
      should_emit = true;
    if (VISIBLE_IN_REFLECTIONS && !r_in.is_primary)
      should_emit = true;
    return should_emit ? emit_color : Vec3(0, 0, 0);
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
    const double s = scale;
    int ix = static_cast<int>(std::floor(s * rec.p.x()));
    int iy = static_cast<int>(std::floor(s * rec.p.y()));
    int iz = static_cast<int>(std::floor(s * rec.p.z()));
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
    srec.roughness = 1.0f; // Matte
    return true;
  }

  // Exact evaluation for NEE
  virtual Vec3 eval_bsdf(const Ray &r_in, const HitRecord &rec,
                         const Vec3 &scattered_dir) const override {
    Vec3 albedo = get_albedo(rec);
    Real cosine = dot(rec.normal, unit_vector(scattered_dir));
    if (cosine < 0)
      return Vec3(0, 0, 0);
    return albedo * (cosine / PI);
  }

  virtual Real scattering_pdf(const Ray &r_in, const HitRecord &rec,
                              const Ray &scattered) const override {
    auto cosine = dot(rec.normal, unit_vector(scattered.dir));
    return cosine < 0 ? 0 : cosine / PI;
  }
};