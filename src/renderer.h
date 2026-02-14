#pragma once

// ===============================================================================================
// MODULE: PATH TRACING CORE
// ===============================================================================================
//
// DESCRIPTION:
//   This is the heart of the rendering engine. It implements a Unidirectional
//   Path Tracer with Next Event Estimation (NEE).
//
// ===============================================================================================

#include "common.h"
#include "environment.h"
#include "geometry.h"
#include "hittable.h"
#include "materials.h"
#include "sampler.h"

// Helper: Power Heuristic
inline Real power_heuristic(Real pdf_f, Real pdf_g) {
  Real f2 = pdf_f * pdf_f;
  Real g2 = pdf_g * pdf_g;
  Real den = f2 + g2;
  if (den < 1e-10f)
    return 0.0f;
  return f2 / den;
}

// -----------------------------------------------------------------------------------------------
// ALGORITHM: DIRECT LIGHT SAMPLING (Next Event Estimation)
// -----------------------------------------------------------------------------------------------
inline Vec3 sample_direct_light(const Ray &r, const HitRecord &rec,
                                const ScatterRecord &srec,
                                const Hittable &world,
                                const HittableList &lights,
                                const EnvironmentMap *env_map,
                                Sampler &sampler) {
  Vec3 direct_light(0, 0, 0);

  // Strategy: 50/50 EnvMap vs Geometric Lights
  bool sample_env = false;

  // Determine Environment Mode based on Surface Roughness
  // Roughness < 0.2 means the surface is Glossy/Specular -> Use Specular Scale
  // Roughness >= 0.2 means the surface is Diffuse/Matte -> Use Diffuse Scale
  int env_mode = (srec.roughness < 0.2f) ? 2 : 1;
  Real active_scale = (env_mode == 2) ? env_map->env_specular_scale
                                      : env_map->env_diffuse_scale;

  bool env_is_active = env_map && (active_scale > 0.001f);
  bool lights_are_active = !lights.raw_objects.empty();

  if (env_is_active && lights_are_active) {
    sample_env = sampler.get_1d() < 0.5f;
  } else if (env_is_active) {
    sample_env = true;
  } else if (lights_are_active) {
    sample_env = false;
  } else {
    return Vec3(0, 0, 0);
  }

  // --- A. Generate Light Sample ---
  Ray light_ray;
  Real light_pdf_val = 0.0f;
  bool is_env_sample = false;
  Vec3 potential_light_emission(0, 0, 0);

  if (sample_env && env_map) {
    // Importance Sampling HDRI
    Vec3 dir = env_map->sample_direction(sampler, light_pdf_val);
    light_ray = Ray(rec.p, dir, r.tm, true);

    if (lights_are_active)
      light_pdf_val *= 0.5f;

    potential_light_emission = env_map->sample(dir, env_mode);
    if (potential_light_emission.length_squared() <= 0)
      light_pdf_val = 0;
    is_env_sample = true;

  } else if (!lights.raw_objects.empty()) {
    // Sampling Geometric Light
    auto light_ray_dir = lights.random(rec.p, sampler);
    light_ray = Ray(rec.p, light_ray_dir, r.tm, true);
    light_pdf_val = lights.pdf_value(rec.p, light_ray.dir);

    if (env_is_active)
      light_pdf_val *= 0.5f;
    is_env_sample = false;
  }

  // --- B. Validation & MIS Calculation ---
  if (light_pdf_val > 0) {
    // 1. Evaluate BSDF components separately
    auto bsdf_comps = rec.mat_ptr->eval_bsdf_components(r, rec, light_ray.dir);

    // Check if any component contributes
    if ((bsdf_comps.diffuse.length_squared() > 0 ||
         bsdf_comps.specular.length_squared() > 0)) {

      // 2. Calculate Scattering PDF (p_bsdf) for MIS
      Real bsdf_pdf = rec.mat_ptr->scattering_pdf(r, rec, light_ray);

      // 3. Shadow Ray
      Vec3 transmission(1.0f, 1.0f, 1.0f);
      Ray shadow_ray = light_ray;
      bool light_visible = false;

      // Traversal Logic (Handles transparent shadows)
      for (int i = 0; i < 5; ++i) {
        HitRecord hit_obstacle;
        if (world.hit(shadow_ray, EPSILON, INFINITY_REAL, hit_obstacle)) {
          if (hit_obstacle.mat_ptr->is_transparent()) {

            // NOTE: Deterministic Shadow Throughput for Transparency
            // We follow the user request: Shadow intensity depends on
            // Transmission. Using standard Beer's Law approximation for thin
            // surfaces (Throughput = Albedo * Transmission) No more stochastic
            // scatter or arbitrary constants.

            // 1. Light Check (Transparent object IS the light?)
            if (!is_env_sample) {
              Vec3 emission_found = hit_obstacle.mat_ptr->emit(
                  shadow_ray, hit_obstacle, 0, 0, hit_obstacle.p);
              if (emission_found.length_squared() > 0) {
                potential_light_emission = emission_found; // Geometric Light
                light_visible = true;
                break;
              }
            }

            // 2. Attenuation
            Vec3 attenuation = hit_obstacle.mat_ptr->shadow_attenuation(
                shadow_ray, hit_obstacle);

            // If completely opaque (attenuation 0), stop.
            // Note: shadow_attenuation() returns (0,0,0) for opaque materials.
            if (attenuation.length_squared() < 1e-6f) {
              transmission = Vec3(0, 0, 0);
              break;
            }

            transmission = transmission * attenuation;

            // Advance Ray
            shadow_ray = Ray(hit_obstacle.p + EPSILON * shadow_ray.dir,
                             shadow_ray.dir, shadow_ray.tm, true);
          } else {
            // Opaque Obstacle
            if (is_env_sample) {
              light_visible = false;
            } else {
              // Sampled Geom Light?
              auto li_emit = hit_obstacle.mat_ptr->emit(
                  shadow_ray, hit_obstacle, hit_obstacle.u, hit_obstacle.v,
                  hit_obstacle.p);
              if (li_emit.length_squared() > 0) {
                potential_light_emission = li_emit;
                light_visible = true;
              }
            }
            break;
          }
        } else {
          // Hit Nothing -> Sky
          if (is_env_sample)
            light_visible = true;
          break;
        }
      }

      // 4. Final Contribution with MIS Weight and Split BSDF Scales
      if (light_visible) {
        Real w_mis = power_heuristic(light_pdf_val, bsdf_pdf);

        Vec3 final_bsdf_contrib;
        if (is_env_sample) {
          // Fetch RAW light (unscaled!)
          // We resample RAW from direction for accuracy, bypassing the previous
          // 'sample()' baked scale.
          Vec3 raw_light = env_map->sample_raw(light_ray.dir);
          // Apply Exposure
          raw_light = raw_light * env_map->env_exposure;

          // Combine components with their respective scales
          final_bsdf_contrib =
              (bsdf_comps.diffuse * env_map->env_diffuse_scale) +
              (bsdf_comps.specular * env_map->env_specular_scale);

          direct_light = raw_light * final_bsdf_contrib * transmission *
                         (w_mis / light_pdf_val);

        } else {
          // Geometric Light (No extra scales, just emission)
          final_bsdf_contrib = bsdf_comps.diffuse + bsdf_comps.specular;
          direct_light = potential_light_emission * final_bsdf_contrib *
                         transmission * (w_mis / light_pdf_val);
        }
      }
    }
  }

  return direct_light;
}

// -----------------------------------------------------------------------------------------------
// ALGORITHM: PATH TRACING RECURSION (MIS Aware)
// -----------------------------------------------------------------------------------------------
inline Vec3 ray_color(const Ray &r, const Hittable &world,
                      const HittableList &lights, const EnvironmentMap *env_map,
                      int depth, Sampler &sampler,
                      Real prev_bsdf_pdf = 1.0f, // PDF of the ray generation
                      Real prev_roughness = 1.0f // Roughness of previous bounce
) {

  // 1. Bounce Limit
  if (depth <= 0)
    return Vec3(0, 0, 0);

  // 2. Scene Intersection
  HitRecord rec;
  if (!world.hit(r, EPSILON, INFINITY_REAL, rec)) {
    // --- BACKGROUND / ENV MAP HIT ---
    if (env_map) {
      // Logic for Environment Scale (Visual Split)
      // Mode 0 (Visible) : Primary Rays.
      // Mode 1 (Direct)  : Sky lighting Diffuse/Rough surfaces (Illumination).
      // Mode 2 (Reflect) : Sky appearing in Mirrors/Glossy reflections.

      int mode = 0;
      if (r.is_primary) {
        mode = 0; // Visible Background
      } else if (prev_roughness < 0.2f) {
        mode = 2; // Reflections
      } else {
        mode = 1; // Illumination
      }

      Vec3 L_e = env_map->sample(r.dir, mode);

      // NOTE: Primary Rays must not be weighted by MIS.
      // They are "Dirac" observations from the camera (Strategy 1 with 100%
      // weight). If we apply MIS, the huge PDF of the unclipped sun (Strategy
      // 2) will crush the BSDF/Camera weight to zero -> Black Sun.
      if (r.is_primary || prev_roughness < 0.001f)
        return L_e;

      // Calculate what the Light PDF would have been for this direction
      Real light_pdf = 0.0f;

      Real active_scale = (mode == 2) ? env_map->env_specular_scale
                                      : env_map->env_diffuse_scale;
      if (mode == 0)
        active_scale = env_map->env_background_scale;

      bool env_is_active = active_scale > 0.001f;
      bool lights_are_active = !lights.raw_objects.empty();

      if (env_is_active) {
        light_pdf = env_map->pdf_value(r.dir);
        if (lights_are_active)
          light_pdf *= 0.5f;
      }

      Real w_mis = power_heuristic(prev_bsdf_pdf, light_pdf);
      return L_e * w_mis;
    }
    return Vec3(0, 0, 0);
  }

  // 3. Emission Hit
  Vec3 emitted = rec.mat_ptr->emit(r, rec, rec.u, rec.v, rec.p);
  if (emitted.length_squared() > 0) {
    if (prev_roughness < 0.001f || r.is_primary)
      return emitted;

    // Active Check using Diffuse/Specular scales
    bool env_is_active = env_map && (env_map->env_diffuse_scale > 0.001f ||
                                     env_map->env_specular_scale > 0.001f);
    bool lights_are_active = !lights.raw_objects.empty();

    if (lights_are_active) {
      Real p_light = lights.pdf_value(r.orig, r.dir);
      if (env_is_active)
        p_light *= 0.5f;

      Real w_mis = power_heuristic(prev_bsdf_pdf, p_light);
      return emitted * w_mis;
    }
    return emitted;
  }

  // 4. Scattering & BSDF Sampling
  ScatterRecord srec;
  if (!rec.mat_ptr->scatter(r, rec, srec, sampler))
    return Vec3(0, 0, 0);

  // 5. Specular Optimization
  if (srec.is_specular) {
    return srec.attenuation * ray_color(srec.specular_ray, world, lights,
                                        env_map, depth - 1, sampler, 1.0f,
                                        srec.roughness);
  }

  // 6. Direct Light (Next Event Estimation)
  Vec3 direct_light =
      sample_direct_light(r, rec, srec, world, lights, env_map, sampler);

  // 7. Indirect Light (Recursive Step)
  Real bsdf_pdf = rec.mat_ptr->scattering_pdf(r, rec, srec.specular_ray);

  Vec3 indirect = srec.attenuation * ray_color(srec.specular_ray, world, lights,
                                               env_map, depth - 1, sampler,
                                               bsdf_pdf, srec.roughness);

  // 8. Output
  Vec3 total = direct_light + indirect;

  // Firefly Clamp
  total.e[0] = firefly_clamp(total.x(), FIREFLY_CLAMP_LIMIT);
  total.e[1] = firefly_clamp(total.y(), FIREFLY_CLAMP_LIMIT);
  total.e[2] = firefly_clamp(total.z(), FIREFLY_CLAMP_LIMIT);

  return total;
}