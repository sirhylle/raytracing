#pragma once

#include "common.h"
#include "sampler.h"
#include <algorithm>
#include <cmath>
#include <utility> // pour std::pair
#include <vector>

struct EnvironmentMap {
  std::vector<Real> data;
  int width;
  int height;

  // New unified scales (Pro Workflow)
  Real env_background_scale = 1.0f; // Visible to Camera
  Real env_diffuse_scale = 1.0f;    // Global Illumination
  Real env_specular_scale = 1.0f;   // Reflections
  Real env_exposure = 1.0f;         // Master Intensity

  Real rotation = 0.0f;
  Real clipping_threshold; // Seuil de clipping pour le MIS et le sampling

  // Pour l'Importance Sampling
  std::vector<Real> marginal_CDF; // Probabilité de choisir une ligne Y
  std::vector<std::vector<Real>>
      conditional_CDFs; // Probabilité de choisir X sachant Y

  EnvironmentMap(const std::vector<Real> &d, int w, int h,
                 Real threshold = INFINITY_REAL)
      : data(d), width(w), height(h), clipping_threshold(threshold) {
    build_cdf();
  }

  void set_scales(Real exposure, Real background, Real diffuse, Real specular) {
    env_exposure = exposure;
    env_background_scale = background;
    env_diffuse_scale = diffuse;
    env_specular_scale = specular;
  }

  // Setter pour la rotation (reçoit des degrés)
  void set_rotation(Real degrees) { rotation = degrees * (PI / 180.0f); }

  // Setter pour le clipping
  void set_clipping_threshold(Real t) {
    clipping_threshold = t;
    build_cdf();
  }

  // Trouve la direction du pixel le plus lumineux (Pour le soleil auto)
  std::pair<Vec3, Vec3> find_sun_hotspot() const {
    Real max_lum = -1.0f;
    int best_x = 0;
    int best_y = 0;
    Vec3 best_color(0, 0, 0);

    for (int y = 0; y < height; ++y) {
      for (int x = 0; x < width; ++x) {
        int idx = (y * width + x) * 3;
        Real r = data[idx];
        Real g = data[idx + 1];
        Real b = data[idx + 2];
        Real lum = 0.2126f * r + 0.7152f * g + 0.0722f * b;

        if (lum > max_lum) {
          max_lum = lum;
          best_x = x;
          best_y = y;
          best_color = Vec3(r, g, b);
        }
      }
    }

    Real u = (best_x + 0.5f) / width;
    Real v = (best_y + 0.5f) / height;
    Real theta = v * PI;
    Real phi_texture = (u * 2 * PI) - PI;
    Real phi_world = phi_texture - rotation;

    Real sin_theta = std::sin(theta);
    Real cos_theta = std::cos(theta);
    Real sin_phi = std::sin(phi_world);
    Real cos_phi = std::cos(phi_world);

    Vec3 dir(sin_theta * cos_phi, cos_theta, -sin_theta * sin_phi);
    return {unit_vector(dir), best_color};
  }

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
      Real v = (y + 0.5f) / height;
      Real theta = v * PI;
      Real sin_theta = std::sin(theta);

      Real row_integral = 0.0f;
      conditional_CDFs[y][0] = 0.0f;

      for (int x = 0; x < width; ++x) {
        Real raw_lum = get_luminance(x, y);

        // Safety: Filter NaNs/Infs in the source data immediately
        if (!std::isfinite(raw_lum))
          raw_lum = 0.0f;

        Real clipped_lum = std::min(raw_lum, clipping_threshold);
        Real importance = clipped_lum * sin_theta;
        row_integral += importance;
        conditional_CDFs[y][x + 1] = row_integral;
      }

      if (row_integral > 0) {
        for (int x = 1; x <= width; ++x)
          conditional_CDFs[y][x] /= row_integral;
      } else {
        for (int x = 1; x <= width; ++x)
          conditional_CDFs[y][x] = (Real)x / width;
      }

      total_integral += row_integral;
      marginal_CDF[y + 1] = total_integral;
    }

    if (total_integral > 0) {
      for (int y = 1; y <= height; ++y)
        marginal_CDF[y] /= total_integral;
    } else {
      for (int y = 1; y <= height; ++y)
        marginal_CDF[y] = (Real)y / height;
    }
  }

  // Importance Sampling
  Vec3 sample_direction(Sampler &sampler, Real &pdf) const {
    Real r1 = sampler.get_1d();
    auto it_y = std::lower_bound(marginal_CDF.begin(), marginal_CDF.end(), r1);
    int y = std::max(0, (int)(it_y - marginal_CDF.begin()) - 1);

    Real r2 = sampler.get_1d();
    auto it_x = std::lower_bound(conditional_CDFs[y].begin(),
                                 conditional_CDFs[y].end(), r2);
    int x = std::max(0, (int)(it_x - conditional_CDFs[y].begin()) - 1);

    // Sub-pixel jitter?
    // The original code used (x + random) / width.
    Real u = (x + sampler.get_1d()) / width;
    Real v = (y + sampler.get_1d()) / height;

    Real theta = v * PI;
    Real phi_texture = (u * 2 * PI) - PI;
    Real phi_world = phi_texture - rotation;

    Real sin_theta = std::sin(theta);
    Real cos_theta = std::cos(theta);
    Real sin_phi = std::sin(phi_world);
    Real cos_phi = std::cos(phi_world);

    Vec3 dir(sin_theta * cos_phi, cos_theta, -sin_theta * sin_phi);

    Real pixel_lum = get_luminance(x, y);

    // Approximatif mais suffisant pour le NEE
    if (sin_theta == 0)
      pdf = 0;
    else {
      Real safe_sin = std::max(sin_theta, 1e-5f);
      Real prob_y = marginal_CDF[y + 1] - marginal_CDF[y];
      Real prob_x_given_y = conditional_CDFs[y][x + 1] - conditional_CDFs[y][x];
      Real prob_pixel = prob_y * prob_x_given_y;

      pdf = prob_pixel * (width * height) / (2 * PI * PI * safe_sin);
    }

    return unit_vector(dir);
  }

  // Calculate PDF for a given direction (Needed for MIS)
  Real pdf_value(const Vec3 &dir) const {
    if (dir.length_squared() < 1e-6f)
      return 0.0f;
    Vec3 unit_dir = unit_vector(dir);

    auto theta = std::acos(unit_dir.y());
    auto phi_world = std::atan2(-unit_dir.z(), unit_dir.x()) + PI;
    Real phi_texture = phi_world + rotation;

    Real u = phi_texture / (2 * PI);
    Real v = theta / PI;

    int x = static_cast<int>(u * width) % width;
    int y = static_cast<int>(v * height);
    if (x < 0)
      x += width;
    y = std::max(0, std::min(y, height - 1));

    Real sin_theta = std::sin(theta);
    if (sin_theta <= 0)
      return 0.0f;

    Real prob_y = marginal_CDF[y + 1] - marginal_CDF[y];
    Real prob_x_given_y = conditional_CDFs[y][x + 1] - conditional_CDFs[y][x];
    Real prob_pixel = prob_y * prob_x_given_y;

    return prob_pixel * (width * height) / (2 * PI * PI * sin_theta);
  }

  Vec3 sample(const Vec3 &dir, int mode) const {
    if (dir.length_squared() < 1e-6f)
      return Vec3(0, 0, 0);

    Real weight = 1.0f;
    // Mode 0: Background/Primary
    // Mode 1: Diffuse/Illumination
    // Mode 2: Specular/Reflections
    if (mode == 0)
      weight = env_background_scale;
    else if (mode == 1)
      weight = env_diffuse_scale;
    else if (mode == 2)
      weight = env_specular_scale;

    // Apply Global Exposure
    weight *= env_exposure;

    if (weight <= 0)
      return Vec3(0, 0, 0);

    auto unit_dir = unit_vector(dir);
    auto theta = std::acos(unit_dir.y());
    auto phi_world = std::atan2(-unit_dir.z(), unit_dir.x()) + PI;

    Real phi_texture = phi_world + rotation;

    Real u = phi_texture / (2 * PI);
    Real v = theta / PI;

    Real px = u * width - 0.5f;
    Real py = v * height - 0.5f;
    int x0 = static_cast<int>(std::floor(px));
    int y0 = static_cast<int>(std::floor(py));
    Real fx = px - x0;
    Real fy = py - y0;

    auto get_pixel = [&](int x, int y) {
      x = (x % width + width) % width;
      y = std::max(0, std::min(y, height - 1));
      int idx = (y * width + x) * 3;
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

    Vec3 raw_radiance = (c0 * (1.0f - fy) + c1 * fy) * weight;

    // Application du clipping
    if (mode != 0 && clipping_threshold < INFINITY_REAL) {
      Real max_val = clipping_threshold * weight;
      Real r = std::min(raw_radiance.x(), max_val);
      Real g = std::min(raw_radiance.y(), max_val);
      Real b = std::min(raw_radiance.z(), max_val);

      // Safety: If raw was NaN or Inf, std::min might behave unexpectedly or
      // propagate it. We force finite checks.
      if (!std::isfinite(r))
        r = 0.0f;
      if (!std::isfinite(g))
        g = 0.0f;
      if (!std::isfinite(b))
        b = 0.0f;

      return Vec3(r, g, b);
    }

    // Safety for non-clipped values
    if (!std::isfinite(raw_radiance.x()) || !std::isfinite(raw_radiance.y()) ||
        !std::isfinite(raw_radiance.z())) {
      return Vec3(0, 0, 0);
    }

    return raw_radiance;
  }

  // New: Sample Raw HDR color without scales (for Diffuse/Specular split)
  // New: Sample Raw HDR color without scales (for Diffuse/Specular split)
  Vec3 sample_raw(const Vec3 &dir) const {
    // Explicit implementation because simple sample() applies global exposure
    // and scales. We want the RAW pixel data here (unscaled) because we apply
    // exposure/scales separately in NEE.
    if (dir.length_squared() < 1e-6f)
      return Vec3(0, 0, 0);

    auto unit_dir = unit_vector(dir);
    auto theta = std::acos(unit_dir.y());
    auto phi_world = std::atan2(-unit_dir.z(), unit_dir.x()) + PI;
    Real phi_texture = phi_world + rotation;

    Real u = phi_texture / (2 * PI);
    Real v = theta / PI;
    Real px = u * width - 0.5f;
    Real py = v * height - 0.5f;
    int x0 = static_cast<int>(std::floor(px));
    int y0 = static_cast<int>(std::floor(py));
    Real fx = px - x0;
    Real fy = py - y0;

    auto get_pixel = [&](int x, int y) {
      x = (x % width + width) % width;
      y = std::max(0, std::min(y, height - 1));
      int idx = (y * width + x) * 3;
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
    Vec3 raw = c0 * (1.0f - fy) + c1 * fy;

    // Clipping is generally desirable even for raw
    if (clipping_threshold < INFINITY_REAL) {
      Real max_val = clipping_threshold; // No scale applied
      return Vec3(std::min(raw.x(), max_val), std::min(raw.y(), max_val),
                  std::min(raw.z(), max_val));
    }
    return raw;
  }
};