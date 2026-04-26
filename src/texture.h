#pragma once

// ===============================================================================================
// MODULE: TEXTURES
// ===============================================================================================
//
// DESCRIPTION:
//   Abstract Texture interface and implementations for PBR Materials.
//   - SolidColor : A constant color/value texture.
//   - ImageTexture : A 2D image mapped over UV coordinates (0-1).
//
// ===============================================================================================

#include "common.h"
#include <vector>
#include <algorithm>
#include <cmath>

class Texture {
public:
  virtual ~Texture() = default;
  virtual Vec3 value(Real u, Real v, const Vec3& p) const = 0;
};

// ===============================================================================================
// SOLID COLOR TEXTURE
// ===============================================================================================
class SolidColor : public Texture {
private:
  Vec3 color_value;

public:
  SolidColor() : color_value(1.0f, 1.0f, 1.0f) {}
  SolidColor(Vec3 c) : color_value(c) {}
  SolidColor(Real red, Real green, Real blue) : SolidColor(Vec3(red, green, blue)) {}
  SolidColor(Real val) : color_value(val, val, val) {} // Shortcut for roughness/metallic

  virtual Vec3 value(Real u, Real v, const Vec3& p) const override {
    return color_value;
  }
};

// ===============================================================================================
// IMAGE TEXTURE
// ===============================================================================================
class ImageTexture : public Texture {
private:
  std::vector<float> data; // RGB Float32 pixel data
  int width, height;

public:
  ImageTexture() : data(0), width(0), height(0) {}

  ImageTexture(const std::vector<float>& d, int w, int h)
      : data(d), width(w), height(h) {}

  virtual Vec3 value(Real u, Real v, const Vec3& p) const override {
    // If we have no texture data, return solid white (neutral multiplier).
    if (data.empty())
        return Vec3(1, 1, 1);

    // Clamp UVs to [0,1] or wrap around (repeat). Lets repeat.
    u = u - std::floor(u);
    v = v - std::floor(v);

    auto i = static_cast<int>(u * width);
    auto j = static_cast<int>(v * height);

    // Clamp integer to safe range
    if (i >= width)  i = width - 1;
    if (j >= height) j = height - 1;

    // Flip V to match standard image coordinates (0,0 at top-left)
    // Most renderers expect V=0 at bottom, but Python imageio reads row 0 first (top).
    // The previous code for environment didn't flip, we'll keep it standard.

    int pixel_index = (j * width + i) * 3;

    if (pixel_index + 2 < data.size()) {
        return Vec3(data[pixel_index], data[pixel_index + 1], data[pixel_index + 2]);
    }
    
    // Fallback error color (magenta)
    return Vec3(1, 0, 1);
  }
};
