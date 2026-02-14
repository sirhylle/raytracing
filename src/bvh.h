#pragma once

// ===============================================================================================
// MODULE: ACCELERATION STRUCTURE (BVH)
// ===============================================================================================
//
// DESCRIPTION:
//   Implements volume hierarchy (BVH) to accelerate ray-scene intersections.
//   Instead of testing a ray against every object (O(N)), we test against a
//   tree of bounding boxes. If a ray misses a node's box, we can skip all its
//   children (O(log N)).
//
// ALGORITHM:
//   - Construction (Top-Down):
//     1. Compute the bounding box of the current set of objects.
//     2. Choose a splitting axis (e.g., the longest dimension of the box).
//     3. Sort objects along this axis.
//     4. Split into two halves (Left/Right) and recurse.
//
//   - Traversal:
//     1. Check intersection with the node's AABB. If miss, return false.
//     2. If hit, recurse into Left child.
//     3. Then recurse into Right child, but OPTIMIZED: pass the hit distance
//     't' from the left
//        child as the new 't_max' for the right child. This culls objects that
//        are further away.
//
// ===============================================================================================

#include "common.h"
#include "geometry.h" // Nécessaire car BVHNode prend une HittableList en entrée
#include "hittable.h"

#include <algorithm>
#include <iostream>
#include <memory>
#include <vector>

class BVHNode : public Hittable {
public:
  std::shared_ptr<Hittable> left;
  std::shared_ptr<Hittable> right;
  AABB box;

  enum class SplitMethod { Midpoint, SAH };

  // 1. Constructeur Public
  BVHNode(const HittableList &list,
          SplitMethod method = SplitMethod::Midpoint) {
    auto objects = list.owned_objects;
    build(objects, 0, objects.size(), method);
  }

  // 2. Constructeur privé pour la récursion
  BVHNode(std::vector<std::shared_ptr<Hittable>> &objects, size_t start,
          size_t end, SplitMethod method) {
    build(objects, start, end, method);
  }

private:
  void build(std::vector<std::shared_ptr<Hittable>> &objects, size_t start,
             size_t end, SplitMethod method) {
    if (method == SplitMethod::SAH) {
      build_sah(objects, start, end);
    } else {
      // Default: Midpoint (Object Median)
      build_midpoint(objects, start, end, method);
    }
  }

  // --- MIDPOINT SPLIT (Legacy / Fast Build) ---
  void build_midpoint(std::vector<std::shared_ptr<Hittable>> &objects,
                      size_t start, size_t end, SplitMethod method) {
    // 1. Compute total bounding box
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
    int axis = 0;
    if (extent.y() > extent.x() && extent.y() > extent.z())
      axis = 1;
    else if (extent.z() > extent.x() && extent.z() > extent.y())
      axis = 2;

    auto comparator = [axis](const std::shared_ptr<Hittable> &a,
                             const std::shared_ptr<Hittable> &b) {
      AABB box_a, box_b;
      if (!a->bounding_box(box_a) || !b->bounding_box(box_b))
        return false;
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
      left = std::make_shared<BVHNode>(objects, start, mid, method);
      right = std::make_shared<BVHNode>(objects, mid, end, method);
    }

    AABB box_left, box_right;
    if (!left || !right || !left->bounding_box(box_left) ||
        !right->bounding_box(box_right))
      std::cerr << "Erreur: Création BVH Midpoint.\n";

    box = surrounding_box(box_left, box_right);
  }

  // --- SAH SPLIT (Binning) ---
  struct Bin {
    AABB bounds;
    int count = 0;
  };

  void build_sah(std::vector<std::shared_ptr<Hittable>> &objects, size_t start,
                 size_t end) {
    // 1. Compute Bounds of geometry
    AABB total_box;
    AABB centroid_box; // For binning
    bool first = true;
    for (size_t i = start; i < end; ++i) {
      AABB temp_box;
      if (objects[i]->bounding_box(temp_box)) {
        total_box = first ? temp_box : surrounding_box(total_box, temp_box);
        Vec3 center = 0.5f * (temp_box.min + temp_box.max);
        if (first) {
          centroid_box = AABB(center, center);
        } else {
          centroid_box.min = min_vec(centroid_box.min, center);
          centroid_box.max = max_vec(centroid_box.max, center);
        }
        first = false;
      }
    }
    box = total_box; // Set node bounds immediately

    size_t count = end - start;
    if (count == 1) {
      left = right = objects[start];
      return;
    }

    // Check if centroids are degenerate (all objects at same spot)
    Vec3 extent = centroid_box.max - centroid_box.min;
    int axis = 0;
    if (extent.y() > extent.x() && extent.y() > extent.z())
      axis = 1;
    else if (extent.z() > extent.x() && extent.z() > extent.y())
      axis = 2;

    if (extent[axis] < 1e-6f) {
      // Degenerate case: Fallback to simple split
      size_t mid = start + count / 2;
      // Sort arbitrarily to ensure determinism
      auto comparator = [](const std::shared_ptr<Hittable> &a,
                           const std::shared_ptr<Hittable> &b) {
        return a.get() < b.get();
      };
      std::sort(objects.begin() + start, objects.begin() + end, comparator);
      left = std::make_shared<BVHNode>(objects, start, mid, SplitMethod::SAH);
      right = std::make_shared<BVHNode>(objects, mid, end, SplitMethod::SAH);
      return;
    }

    // 2. Binning
    constexpr int NUM_BINS = 16;
    Bin bins[NUM_BINS];

    for (size_t i = start; i < end; ++i) {
      AABB t_box;
      objects[i]->bounding_box(t_box);
      Vec3 center = 0.5f * (t_box.min + t_box.max);

      // Map centroid to [0, NUM_BINS-1]
      float k1 = NUM_BINS * (1.0f - 1e-6f) *
                 (center[axis] - centroid_box.min[axis]) / extent[axis];
      int bin_idx = static_cast<int>(k1);
      if (bin_idx < 0)
        bin_idx = 0;
      if (bin_idx >= NUM_BINS)
        bin_idx = NUM_BINS - 1;

      bins[bin_idx].count++;
      if (bins[bin_idx].count == 1)
        bins[bin_idx].bounds = t_box;
      else
        bins[bin_idx].bounds = surrounding_box(bins[bin_idx].bounds, t_box);
    }

    // 3. Evaluate Split Costs (Sweep)
    // We can split AFTER bin 0, 1, ..., NUM_BINS-2. (NUM_BINS-1 planes)
    Real leftArea[NUM_BINS - 1];
    Real rightArea[NUM_BINS - 1];
    int leftCount[NUM_BINS - 1];
    int rightCount[NUM_BINS - 1];
    AABB leftBox, rightBox;
    int leftSum = 0, rightSum = 0;

    // Left to Right Sweep
    bool leftValid = false;
    for (int i = 0; i < NUM_BINS - 1; ++i) {
      if (bins[i].count > 0) {
        leftSum += bins[i].count;
        leftBox = leftValid ? surrounding_box(leftBox, bins[i].bounds)
                            : bins[i].bounds;
        leftValid = true;
      }
      leftArea[i] = leftValid ? surface_area(leftBox) : 0.0f;
      leftCount[i] = leftSum;
    }

    // Right to Left Sweep
    bool rightValid = false;
    for (int i = NUM_BINS - 2; i >= 0; --i) {
      if (bins[i + 1].count > 0) {
        rightSum += bins[i + 1].count;
        rightBox = rightValid ? surrounding_box(rightBox, bins[i + 1].bounds)
                              : bins[i + 1].bounds;
        rightValid = true;
      }
      rightArea[i] = rightValid ? surface_area(rightBox) : 0.0f;
      rightCount[i] = rightSum;
    }

    // Find Best Split
    Real minCost = INFINITY_REAL;
    int bestSplit = -1;

    Real totalArea = surface_area(total_box);
    if (totalArea <= 1e-8f)
      totalArea = 1e-8f; // Safety

    // Cost of NO split (Leaf)
    Real intersection_cost = 2.0f; // Bias towards splitting
    Real leafCost = (Real)count * intersection_cost;

    for (int i = 0; i < NUM_BINS - 1; ++i) {
      // If all objects are on one side, this split is useless
      if (leftCount[i] == 0 || rightCount[i] == 0)
        continue;

      Real cost = 1.0f +
                  (leftArea[i] / totalArea) * leftCount[i] * intersection_cost +
                  (rightArea[i] / totalArea) * rightCount[i] *
                      intersection_cost; // +1 for traversal overhead

      if (cost < minCost) {
        minCost = cost;
        bestSplit = i;
      }
    }

    // 4. Partition or Leaf?
    if (minCost >= leafCost && count < 8) {
      // Make leaf (simplified structure: leaf must hold 1 object?
      // In this implementation, BVHNode is the structure.
      // If we stop recursing, 'left' and 'right' members are used to hold
      // children. BUT wait, this specific BVHNode implementation separates
      // 'Leaf' (holds 1 obj in left/right?) NO. 'left' and 'right' are
      // Hittables. If 'left' is a Triangle, it's a leaf. If 'left' is a
      // BVHNode, it's a node.

      // If we have 'count' objects, we CANNOT make a leaf if count > 1 (or 2).
      // Because BVHNode only has 2 pointers. We can't store a vector of 8
      // objects.

      // LIMITATION:
      // The current BVHNode structure is a strict binary tree where each node
      // has exactly two children (left/right). We cannot store a list of
      // objects in a leaf node. Therefore, we must recurse until we isolate 1
      // or 2 objects, prohibiting the creation of "fat leaves" with count < 8.
      // The condition `minCost >= leafCost` is thus largely ignored for counts
      // > 2.
    }

    // Force split if count > 2, regardless of cost?
    // Yes, unless we introduce a list-holding leaf.
    // Since we don't, we must ignore the 'make leaf' decision if count > 2.
    // But we can choose the BEST split (SAH) or fallback to Midpoint.

    if (bestSplit == -1) {
      // Fallback to midpoint if SAH failed to find a separation (e.g. all
      // centers in one bin)
      build_midpoint(objects, start, end, SplitMethod::SAH);
      return;
    }

    // Partition objects based on the best split bin
    // std::partition reorders elements
    auto it = std::partition(objects.begin() + start, objects.begin() + end,
                             [=](const std::shared_ptr<Hittable> &obj) {
                               AABB t_box;
                               obj->bounding_box(t_box);
                               Vec3 center = 0.5f * (t_box.min + t_box.max);
                               float k1 =
                                   NUM_BINS * (1.0f - 1e-6f) *
                                   (center[axis] - centroid_box.min[axis]) /
                                   extent[axis];
                               int bin_idx = static_cast<int>(k1);
                               if (bin_idx < 0)
                                 bin_idx = 0;
                               if (bin_idx >= NUM_BINS)
                                 bin_idx = NUM_BINS - 1;
                               return bin_idx <= bestSplit;
                             });

    size_t mid = std::distance(objects.begin(), it);

    // Recursive Build
    left = std::make_shared<BVHNode>(objects, start, mid, SplitMethod::SAH);
    right = std::make_shared<BVHNode>(objects, mid, end, SplitMethod::SAH);

    // Re-compute bbox to be tight
    AABB box_left, box_right;
    left->bounding_box(box_left);
    right->bounding_box(box_right);
    box = surrounding_box(box_left, box_right);
  }

  static inline Real surface_area(const AABB &b) {
    Vec3 e = b.max - b.min;
    return 2.0f * (e.x() * e.y() + e.y() * e.z() + e.z() * e.x());
  }

  static inline Vec3 min_vec(const Vec3 &a, const Vec3 &b) {
    return Vec3(std::min(a.x(), b.x()), std::min(a.y(), b.y()),
                std::min(a.z(), b.z()));
  }
  static inline Vec3 max_vec(const Vec3 &a, const Vec3 &b) {
    return Vec3(std::max(a.x(), b.x()), std::max(a.y(), b.y()),
                std::max(a.z(), b.z()));
  }

  // ---------------------------------------------------------------------------------------------
  // ALGORITHM: TRAVERSAL
  // ---------------------------------------------------------------------------------------------
  virtual bool hit(const Ray &r, Real t_min, Real t_max,
                   HitRecord &rec) const override {
    // 1. Box Test: If the ray misses the bounding box, we can skip the entire
    // subtree.
    if (!box.hit(r, t_min, t_max))
      return false;

    // 2. Check Children
    // We recursively check the Left child.
    bool hit_left = left->hit(r, t_min, t_max, rec);

    // Then check Right child.
    // OPTIMIZATION: If we hit the left child at distance 'rec.t', we clamp
    // 't_max' for the right child search. We only care about objects CLOSER
    // than the one we just found.
    bool hit_right = right->hit(r, t_min, hit_left ? rec.t : t_max, rec);

    return hit_left || hit_right;
  }

  virtual bool bounding_box(AABB &output_box) const override {
    output_box = box;
    return true;
  }
};