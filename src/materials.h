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
#include "sampler.h"
#include "texture.h"

// ===============================================================================================
// CONSTANTS: VISUAL TWEAKS
// ===============================================================================================

// For Transparent Shadow Attenuation (Softer Shadows)
// Power: Controls the gradient curve. Lower = wider/softer.
// Max Opacity: Clamps the maximum darkness of the shadow edge.
const Real SHADOW_FRESNEL_POWER = 1.1f;
const Real SHADOW_FRESNEL_MAX_OPACITY = 0.15f;

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

inline Vec3 sample_ggx_ndf(const Vec3 &u,
                           Real roughness) { // u is Vec3 to match get_2d()
                                             // return type which is Vec3 (z=0)
  Real r1 = u.x();
  Real r2 = u.y();
  Real alpha = roughness * roughness;

  Real phi = 2.0f * PI * r1;
  Real cos_theta =
      std::sqrt((1.0f - r2) / (1.0f + (alpha * alpha - 1.0f) * r2));
  Real sin_theta = std::sqrt(1.0f - cos_theta * cos_theta);

  // Spherical to Cartesian (in Tangent Space)
  return Vec3(sin_theta * std::cos(phi), sin_theta * std::sin(phi), cos_theta);
}

// Cosine Weighted Hemisphere Sampling
inline Vec3 sample_cosine_weighted(const Vec3 &n, const Vec3 &u) { // Added u
  Real r1 = u.x();
  Real r2 = u.y();
  Real phi = 2.0f * PI * r1;
  Real sqrt_r2 = std::sqrt(r2);
  Vec3 local(std::cos(phi) * sqrt_r2, std::sin(phi) * sqrt_r2,
             std::sqrt(1.0f - r2));

  ONB onb;
  onb.build_from_w(n);
  return onb.local(local);
}

// OREN-NAYAR DIFFUSE MODEL (Qualitative Approximation)
// Description:
//   Simulates rough diffuse surfaces (clay, skin, fabric) by modeling
//   microfacets as Lambertian V-cavities. Source: "Generalization of Lambert's
//   Reflectance Model" (Oren & Nayar, 1994)
//
// Parameters:
//   n: Surface Normal
//   v: View Vector (from surface to camera) - Normalized
//   l: Light Vector (from surface to light) - Normalized
//   roughness: Surface Roughness [0..1]
//   albedo: Diffuse Color
inline Vec3 eval_oren_nayar(const Vec3 &n, const Vec3 &v, const Vec3 &l,
                            Real roughness, const Vec3 &albedo) {

  Real n_dot_l = dot(n, l);
  Real n_dot_v = dot(n, v);

  if (n_dot_l <= 0.0f || n_dot_v <= 0.0f)
    return Vec3(0, 0, 0);

  Real sigma2 = roughness * roughness;

  // A and B coefficients (Approximation)
  Real A = 1.0f - 0.5f * (sigma2 / (sigma2 + 0.33f));
  Real B = 0.45f * (sigma2 / (sigma2 + 0.09f));

  // Sine and Tangent terms
  // geometric term = max(0, cos(phi_diff)) * sin(alpha) * tan(beta)

  // We need vectors in the tangent plane to compute cos(phi_diff)
  // Project V and L onto tangent plane
  Vec3 v_perp = unit_vector(v - n * n_dot_v);
  Vec3 l_perp = unit_vector(l - n * n_dot_l);

  // Cosine of difference of azimuthal angles
  Real cos_phi_diff = dot(v_perp, l_perp);
  // Clamp to [0, 1] effectively (max(0, cos))
  if (cos_phi_diff < 0.0f)
    cos_phi_diff = 0.0f;

  // Alpha and Beta
  // alpha = max(theta_i, theta_r)
  // beta = min(theta_i, theta_r)
  // We have cosines. acos is expensive.
  // Use identity: sin(acos(x)) = sqrt(1-x^2)
  // sin(alpha) = sqrt(1 - min_cos^2)
  // tan(beta) = sin(beta) / cos(beta) = sqrt(1 - max_cos^2) / max_cos

  Real cos_theta_i = n_dot_l;
  Real cos_theta_r = n_dot_v;

  Real sin_theta_i =
      std::sqrt(std::max(0.0f, 1.0f - cos_theta_i * cos_theta_i));
  Real sin_theta_r =
      std::sqrt(std::max(0.0f, 1.0f - cos_theta_r * cos_theta_r));

  Real sin_alpha, tan_beta;

  if (cos_theta_i < cos_theta_r) {
    // theta_i > theta_r -> alpha = theta_i, beta = theta_r
    sin_alpha = sin_theta_i;
    tan_beta = sin_theta_r / std::max(1e-4f, cos_theta_r);
  } else {
    // theta_r > theta_i -> alpha = theta_r, beta = theta_i
    sin_alpha = sin_theta_r;
    tan_beta = sin_theta_i / std::max(1e-4f, cos_theta_i);
  }

  // Final Radiance
  // L = (rho/pi) * cos_theta_i * (A + B * max(0, cos(phi_diff)) * sin(alpha) *
  // tan(beta))

  Vec3 result =
      (albedo / PI) * n_dot_l * (A + (B * cos_phi_diff * sin_alpha * tan_beta));

  return result;
}

// ===============================================================================================
// CLASSE DE BASE MATERIAL
// ===============================================================================================

class Material {
public:
  virtual bool scatter(const Ray &r_in, const HitRecord &rec,
                       ScatterRecord &srec, Sampler &sampler) const {
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
  Real dispersion;   // 0=No Dispersion, >0=Rainbow Effect

  std::shared_ptr<Texture> albedo_map;
  std::shared_ptr<Texture> roughness_map;
  std::shared_ptr<Texture> metallic_map;
  std::shared_ptr<Texture> normal_map;

  GgxMaterial(const Vec3 &a, Real r, Real m, Real i = 1.5f, Real t = 0.0f,
              Real d = 0.0f)
      : albedo(a), roughness(r), metallic(m), ior(i), transmission(t),
        dispersion(d), albedo_map(nullptr), roughness_map(nullptr), metallic_map(nullptr), normal_map(nullptr) {}

  // Helper properties resolver
  inline void resolve_properties(const HitRecord &rec, Vec3 &out_albedo, Real &out_roughness, Real &out_metallic, Vec3 &out_normal) const {
    Vec3 tex_albedo = albedo_map ? albedo_map->value(rec.u, rec.v, rec.p) : Vec3(1, 1, 1);
    out_albedo = albedo * tex_albedo;
    
    Real tex_rough = roughness_map ? roughness_map->value(rec.u, rec.v, rec.p).x() : 1.0f;
    out_roughness = std::max(0.0f, std::min(1.0f, roughness * tex_rough));
    
    Real tex_metal = metallic_map ? metallic_map->value(rec.u, rec.v, rec.p).x() : 1.0f;
    out_metallic = std::max(0.0f, std::min(1.0f, metallic * tex_metal));

    out_normal = rec.normal;
    if (normal_map) {
        Vec3 n_color = normal_map->value(rec.u, rec.v, rec.p);
        Vec3 ts_n = n_color * 2.0f - Vec3(1.0f, 1.0f, 1.0f);
        ONB onb;
        onb.build_from_w(out_normal);
        out_normal = unit_vector(onb.local(ts_n));
    }
  }

  virtual Vec3 get_albedo(const HitRecord &rec) const override {
    Vec3 out_a, out_n; Real out_r, out_m;
    resolve_properties(rec, out_a, out_r, out_m, out_n);
    return out_a;
  }

  virtual bool is_transparent() const override { return transmission > 0.001f; }

  virtual Vec3 shadow_attenuation(const Ray &r_in,
                                  const HitRecord &rec) const override {
    Vec3 out_albedo, out_normal; Real out_roughness, out_metallic;
    resolve_properties(rec, out_albedo, out_roughness, out_metallic, out_normal);

    // Volumetric Absorption (Beer's Law) + Fresnel + Metallic Blend

    // 1. Fresnel Loss (Reflection)
    Vec3 unit_direction = unit_vector(r_in.dir);
    Real cos_theta = std::fmin(dot(-unit_direction, out_normal), 1.0f);
    Real refraction_ratio = rec.front_face ? (1.0f / ior) : ior;
    Real R = fresnel_dielectric_exact(cos_theta, refraction_ratio);

    // 2. Base Throughput
    Real R_shadow =
        std::min(std::pow(R, SHADOW_FRESNEL_POWER), SHADOW_FRESNEL_MAX_OPACITY);

    Vec3 throughput = Vec3(1.0f, 1.0f, 1.0f) * transmission *
                      (1.0f - R_shadow) * (1.0f - out_metallic);

    // 3. Volumetric Absorption (Beer's Law)
    if (!rec.front_face) {
      throughput.e[0] *= std::pow(out_albedo.x(), rec.t);
      throughput.e[1] *= std::pow(out_albedo.y(), rec.t);
      throughput.e[2] *= std::pow(out_albedo.z(), rec.t);
    }
    return throughput;
  }

  // New Evaluation function for NEE (BSDF * cos_theta)
  virtual BsdfComponents
  eval_bsdf_components(const Ray &r_in, const HitRecord &rec,
                       const Vec3 &scattered_dir) const override {
    
    Vec3 final_albedo, normal; Real final_roughness, final_metallic;
    resolve_properties(rec, final_albedo, final_roughness, final_metallic, normal);

    Vec3 l = unit_vector(scattered_dir);
    Vec3 v = unit_vector(-r_in.dir);
    Vec3 n = normal;

    Real n_dot_l = dot(n, l);
    Real n_dot_v = dot(n, v);

    if (n_dot_l <= 0.0f || n_dot_v <= 0.0f)
      return {Vec3(0, 0, 0), Vec3(0, 0, 0)};

    if (transmission > 0.999f && final_metallic < 0.001f) {
      return {Vec3(0, 0, 0), Vec3(0, 0, 0)};
    }

    Vec3 F;
    Vec3 h = unit_vector(v + l);
    Real v_dot_h = std::max(dot(v, h), 0.0f);

    if (final_metallic > 0.0f) {
      Vec3 F0 = final_albedo;
      F = schlick_fresnel_color(v_dot_h, F0);
    } else {
      Real F_diel = fresnel_dielectric_exact(v_dot_h, 1.0f / ior);
      F = Vec3(F_diel, F_diel, F_diel);
    }

    Real n_dot_h = std::max(dot(n, h), 0.0f);
    Real D = ndf_ggx(n_dot_h, final_roughness);
    Real G = geometry_smith(n_dot_l, n_dot_v, final_roughness);

    Vec3 specular = (D * G * F) / (4.0f * std::max(n_dot_v, 0.0001f));

    Vec3 kD = (Vec3(1.0f, 1.0f, 1.0f) - F) * (1.0f - final_metallic);

    Vec3 diffuse;
    if (final_roughness < 0.01f) {
      diffuse = (kD * final_albedo / PI) * n_dot_l;
    } else {
      diffuse = kD * eval_oren_nayar(n, v, l, final_roughness, final_albedo);
    }

    return {diffuse, specular};
  }

  // Legacy kept for compatibility if needed (but we will switch renderer.h)
  virtual Vec3 eval_bsdf(const Ray &r_in, const HitRecord &rec,
                         const Vec3 &scattered_dir) const override {
    auto comps = eval_bsdf_components(r_in, rec, scattered_dir);
    return comps.diffuse + comps.specular;
  }

  virtual Real scattering_pdf(const Ray &r_in, const HitRecord &rec,
                              const Ray &scattered) const override {
    Vec3 final_albedo, normal; Real final_roughness, final_metallic;
    resolve_properties(rec, final_albedo, final_roughness, final_metallic, normal);

    Vec3 n = normal;
    Vec3 v = unit_vector(-r_in.dir);
    Vec3 l = unit_vector(scattered.dir);
    Real n_dot_l = dot(n, l);
    Real n_dot_v = dot(n, v);
    if (n_dot_v < 0) n_dot_v = 0;
    if (n_dot_l <= 0) return 0;

    Real F_lum = 0.0f;
    if (final_metallic > 0.0f) {
      Vec3 F = schlick_fresnel_color(n_dot_v, final_albedo);
      F_lum = (F.x() + F.y() + F.z()) / 3.0f;
    } else {
      F_lum = fresnel_dielectric_exact(n_dot_v, 1.0f / ior);
    }

    Real prob_spec = (1.0f - final_metallic) * F_lum + final_metallic;
    prob_spec = std::max(0.0f, std::min(1.0f, prob_spec));

    if (final_roughness < 0.001f) return 0;

    Real pdf_diffuse = (final_metallic > 0.99f) ? 0.0f : (n_dot_l / PI);

    Vec3 h = unit_vector(v + l);
    Real n_dot_h = std::max(dot(n, h), 0.0f);
    Real v_dot_h = std::max(dot(v, h), 1e-6f);

    Real D = ndf_ggx(n_dot_h, final_roughness);
    Real pdf_spec = D * n_dot_h / (4.0f * v_dot_h);

    return prob_spec * pdf_spec + (1.0f - prob_spec) * pdf_diffuse;
  }

  virtual bool scatter(const Ray &r_in, const HitRecord &rec,
                       ScatterRecord &srec, Sampler &sampler) const override {

    Vec3 final_albedo, normal; Real final_roughness, final_metallic;
    resolve_properties(rec, final_albedo, final_roughness, final_metallic, normal);

    // 1. Transmission (Glass)
    Real eff_transmission = transmission * (1.0f - final_metallic);

    if (eff_transmission > 0.0f && sampler.get_1d() < eff_transmission) {
      srec.is_specular = true;
      srec.attenuation = final_albedo;

      Real picked_ior = ior;
      Vec3 color_filter(1.0f, 1.0f, 1.0f);

      if (dispersion > 0.001f) {
        Real t = sampler.get_1d();
        picked_ior = ior + (t - 0.5f) * 2.0f * dispersion;

        float r_val = 0.0f, g_val = 0.0f, b_val = 0.0f;
        if (t < 0.6666f) r_val = 1.0f - (t * 1.5f);
        float g_dist = std::abs(t - 0.5f);
        if (g_dist < 0.3333f) g_val = 1.0f - (g_dist * 3.0f);
        if (t > 0.3333f) b_val = (t - 0.3333f) * 1.5f;

        color_filter = Vec3(r_val, g_val, b_val);
        srec.attenuation = srec.attenuation * color_filter * 3.0f;
      }

      Real refraction_ratio = rec.front_face ? (1.0f / picked_ior) : picked_ior;
      Vec3 unit_direction = unit_vector(r_in.dir);

      Vec3 h;
      if (final_roughness < 0.001f) {
        h = normal;
        srec.roughness = 0.0f;
      } else {
        ONB onb;
        onb.build_from_w(normal);
        Vec3 local_h = sample_ggx_ndf(sampler.get_2d(), final_roughness);
        h = onb.local(local_h);
        srec.roughness = final_roughness;
      }

      Real cos_theta = std::fmin(dot(-unit_direction, h), 1.0f);
      Real F = fresnel_dielectric_exact(cos_theta, refraction_ratio);

      Vec3 direction;
      if (sampler.get_1d() < F) {
        direction = reflect(unit_direction, h);
      } else {
        direction = refract(unit_direction, h, refraction_ratio);
        if (direction.length_squared() < 1e-6f)
          direction = reflect(unit_direction, h);
      }

      srec.specular_ray = Ray(rec.p, direction, r_in.tm);
      return true;
    }

    // 2. Opaque PBR Setup
    srec.is_specular = false;
    srec.roughness = final_roughness;

    if (final_roughness < 0.001f) {
      srec.is_specular = true;
    }

    Vec3 v = unit_vector(-r_in.dir);
    Real n_dot_v = std::max(dot(normal, v), 0.0f);

    Real F_lum = 0.0f;
    if (final_metallic > 0.0f) {
      Vec3 F_schlick = schlick_fresnel_color(n_dot_v, final_albedo);
      F_lum = (F_schlick.x() + F_schlick.y() + F_schlick.z()) / 3.0f;
    } else {
      F_lum = fresnel_dielectric_exact(n_dot_v, 1.0f / ior);
    }

    Real prob_spec = (1.0f - final_metallic) * F_lum + final_metallic;
    prob_spec = std::max(0.0f, std::min(1.0f, prob_spec));

    // 3. Stochastic Choice
    if (sampler.get_1d() < prob_spec) {
      // --- SPECULAR PATH (GGX) ---
      ONB onb;
      onb.build_from_w(normal);

      if (final_roughness < 0.001f) {
        Vec3 reflected = reflect(unit_vector(r_in.dir), normal);
        srec.specular_ray = Ray(rec.p, reflected, r_in.tm);
        srec.is_specular = true;
        if (final_metallic > 0.0f)
          srec.attenuation = schlick_fresnel_color(n_dot_v, final_albedo) / prob_spec;
        else
          srec.attenuation = Vec3(1, 1, 1) * (fresnel_dielectric_exact(n_dot_v, 1.0f / ior) / prob_spec);
        return true;
      }

      Vec3 local_h = sample_ggx_ndf(sampler.get_2d(), final_roughness);
      Vec3 h = onb.local(local_h);
      Vec3 l = reflect(-v, h);

      if (dot(l, normal) <= 0.0f) return false;

      srec.specular_ray = Ray(rec.p, l, r_in.tm);

      Real n_dot_l = std::max(dot(normal, l), 0.0001f);
      Real n_dot_h = std::max(dot(normal, h), 0.0001f);
      Real v_dot_h = std::max(dot(v, h), 0.0001f);

      Vec3 F;
      if (final_metallic > 0.0f) F = schlick_fresnel_color(v_dot_h, final_albedo);
      else {
        Real f = fresnel_dielectric_exact(v_dot_h, 1.0f / ior);
        F = Vec3(f, f, f);
      }

      Real G = geometry_smith(n_dot_l, std::max(n_dot_v, 0.0001f), final_roughness);

      Vec3 spec_weight = F * G * v_dot_h / (std::max(n_dot_v, 0.0001f) * n_dot_h);
      srec.attenuation = spec_weight / prob_spec;

    } else {
      // --- DIFFUSE PATH ---
      if (final_metallic > 0.99f) return false;

      Vec3 diff_dir = sample_cosine_weighted(normal, sampler.get_2d());
      srec.specular_ray = Ray(rec.p, diff_dir, r_in.tm);
      Vec3 l = diff_dir;

      if (final_roughness < 0.01f) {
        srec.attenuation = final_albedo * (1.0f - final_metallic);
      } else {
        Vec3 v_in = unit_vector(-r_in.dir);
        Vec3 on_val = eval_oren_nayar(normal, v_in, l, final_roughness, final_albedo);
        Real n_dot_l = dot(normal, l);
        Real pdf = (n_dot_l < 0) ? 0 : (n_dot_l / PI);

        if (pdf > 1e-6f) {
          srec.attenuation = (on_val * (1.0f - final_metallic)) / pdf;
        } else {
          srec.attenuation = Vec3(0, 0, 0);
        }
      }

      Real effective_prob = 1.0f - prob_spec;
      if (effective_prob > 0.001f) {
           srec.attenuation = srec.attenuation / effective_prob;
      }
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
                       ScatterRecord &srec, Sampler &sampler) const override {
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
                       ScatterRecord &srec, Sampler &sampler) const override {
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
                       ScatterRecord &srec, Sampler &sampler) const override {
    srec.is_specular = false;
    srec.attenuation = get_albedo(rec);
    srec.specular_ray = Ray(
        rec.p, sample_cosine_weighted(rec.normal, sampler.get_2d()), r_in.tm);
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