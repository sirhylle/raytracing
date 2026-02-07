#pragma once

#include "common.h"
#include <vector>

// ===============================================================================================
// SAMPLER INTERFACE
// ===============================================================================================

class Sampler {
public:
  virtual ~Sampler() = default;

  // Resets the sampler for a new pixel
  virtual void start_pixel(int x, int y) = 0;

  // Resets the sampler for a new sample within the current pixel
  virtual void start_sample(int sample_index) = 0;

  // Returns a 1D float sample in [0, 1)
  virtual float get_1d() = 0;

  // Returns a 2D float sample in [0, 1) x [0, 1)
  virtual Vec3 get_2d() { return Vec3(get_1d(), get_1d(), 0.0f); }

  virtual std::unique_ptr<Sampler> clone() const = 0;
};

// ===============================================================================================
// GEOMETRIC SAMPLING HELPERS
// ===============================================================================================

inline Vec3 random_in_unit_sphere(Sampler &sampler) {
  for (int i = 0; i < 100; ++i) {
    auto p =
        Vec3(sampler.get_1d() * 2.0f - 1.0f, sampler.get_1d() * 2.0f - 1.0f,
             sampler.get_1d() * 2.0f - 1.0f);
    if (p.length_squared() < 1)
      return p;
  }
  return Vec3(0, 0, 0);
}

inline Vec3 random_unit_vector(Sampler &sampler) {
  return unit_vector(random_in_unit_sphere(sampler));
}

inline Vec3 random_in_unit_disk(Sampler &sampler) {
  for (int i = 0; i < 100; ++i) {
    auto p =
        Vec3(sampler.get_1d() * 2.0f - 1.0f, sampler.get_1d() * 2.0f - 1.0f, 0);
    if (p.length_squared() < 1)
      return p;
  }
  return Vec3(0, 0, 0);
}

// ===============================================================================================
// BLUE NOISE STORAGE
// ===============================================================================================

struct BlueNoiseTexture {
  std::vector<float> data;
  int width = 0;
  int height = 0;

  bool is_valid() const { return !data.empty() && width > 0 && height > 0; }

  float get(int x, int y) const {
    if (!is_valid())
      return 0.0f;
    x = x % width;
    y = y % height;
    return data[y * width + x];
  }
};

static BlueNoiseTexture global_blue_noise;

// ===============================================================================================
// RANDOM SAMPLER (White Noise) - Legacy behavior
// ===============================================================================================

class RandomSampler : public Sampler {
public:
  void start_pixel(int x, int y) override {
    // No state needed for pure random
  }

  void start_sample(int sample_index) override {
    // No state needed
  }

  float get_1d() override { return random_real(); }

  std::unique_ptr<Sampler> clone() const override {
    return std::make_unique<RandomSampler>();
  }
};

#include "sobol.h"

class SobolSampler : public Sampler {
private:
  unsigned long long current_index;
  unsigned current_dimension;
  unsigned scramble;

public:
  void start_pixel(int x, int y) override {
    // Robust TEA hash for scrambling (Tiny Encryption Algorithm)
    unsigned v0 = (unsigned)x, v1 = (unsigned)y;
    unsigned sum = 0;
    for (int i = 0; i < 16; i++) {
      sum += 0x9e3779b9;
      v0 += ((v1 << 4) + 0xa341316c) ^ (v1 + sum) ^ ((v1 >> 5) + 0xc8013ea4);
      v1 += ((v0 << 4) + 0xad90777d) ^ (v0 + sum) ^ ((v0 >> 5) + 0x7e95761e);
    }

    if (global_blue_noise.is_valid()) {
      // Use Blue Noise to "dither" the scramble.
      // We XOR the TEA hash with the blue noise value.
      // This preserves the blue noise spatial property while the TEA hash
      // ensures that we don't see the 128x128 tile repeat exactly.
      float bn = global_blue_noise.get(x, y);
      unsigned bn_val = (unsigned)(bn * 4294967295.0f);
      v0 ^= bn_val;
    }

    scramble = v0;
  }

  void start_sample(int sample_index) override {
    // IMPORTANT: We use index + 1 because index 0 in Sobol sequence returns the
    // scramble value for ALL dimensions, which causes infinite loops in
    // rejection sampling.
    current_index = (unsigned long long)(sample_index + 1);
    current_dimension = 0;
  }

  static inline unsigned fast_hash(unsigned x) {
    x = ((x >> 16) ^ x) * 0x45d9f3b;
    x = ((x >> 16) ^ x) * 0x45d9f3b;
    x = (x >> 16) ^ x;
    return x;
  }

  float get_1d() override {
    // We decorrelate dimensions by hashing the dimension index and XORing with
    // the pixel scramble. This ensures that the MSBs are different for each
    // channel.
    unsigned d_scramble = scramble ^ fast_hash(current_dimension);
    float val = sobol::sample(current_index, current_dimension, d_scramble);
    current_dimension++;
    // Sobol sequence up to 1024 dimensions.
    if (current_dimension >= 1024)
      current_dimension = 0;
    return val;
  }

  std::unique_ptr<Sampler> clone() const override {
    return std::make_unique<SobolSampler>();
  }
};
