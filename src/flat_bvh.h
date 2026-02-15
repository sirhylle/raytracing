#pragma once

// ===============================================================================================
// MODULE: FLAT BVH (Cache-Optimized Linear BVH)
// ===============================================================================================
//
// DESCRIPTION:
//   A linearized BVH stored as a flat array for cache-optimal traversal.
//   Drop-in replacement for BVHNode via the Hittable interface.
//
// DESIGN:
//   1. Build: constructs a standard BVHNode tree (reuses existing SAH/midpoint)
//   2. Flatten: DFS walk writes nodes into a contiguous std::vector<FlatNode>
//   3. Traversal: iterative stack-based, indexes into the flat array
//
// MEMORY LAYOUT:
//   - Left child is always at (current_index + 1) — no pointer needed
//   - Right child offset is stored explicitly
//   - Leaves store an index + count into a separate primitives array
//   - Each FlatNode is 32 bytes (vs ~80+ for BVHNode with shared_ptrs)
//
// ===============================================================================================

#include "bvh.h"
#include "common.h"
#include "geometry.h"
#include "hittable.h"

#include <cstdint>
#include <iostream>
#include <vector>

class FlatBVH : public Hittable {
public:
  // Re-export SplitMethod from BVHNode for API compatibility
  using SplitMethod = BVHNode::SplitMethod;

  // -----------------------------------------------------------------------------------------
  // FLAT NODE (32 bytes, cache-line friendly)
  // -----------------------------------------------------------------------------------------
  struct FlatNode {
    AABB box;              // 24 bytes: bounding box
    uint32_t second_child; // 4 bytes:  offset to right child (left = idx+1)
    uint16_t num_prims;    // 2 bytes:  0 = internal node, >0 = leaf
    uint8_t split_axis;    // 1 byte:   axis for ordered traversal
    uint8_t flags;         // 1 byte:   bit 0 = all_opaque
  };
  static_assert(sizeof(FlatNode) == 32, "FlatNode must be 32 bytes");

  // -----------------------------------------------------------------------------------------
  // DATA
  // -----------------------------------------------------------------------------------------
  std::vector<FlatNode> nodes;
  std::vector<Hittable *> primitives; // raw ptrs to leaf objects

  // Keep shared_ptrs alive (ownership)
  std::vector<std::shared_ptr<Hittable>> owned_prims;

  bool use_ordered = false;
  bool root_all_opaque = true;

  // -----------------------------------------------------------------------------------------
  // CONSTRUCTOR: Build tree then flatten
  // -----------------------------------------------------------------------------------------
  FlatBVH(const HittableList &list,
          SplitMethod method = SplitMethod::Midpoint) {

    size_t n = list.owned_objects.size();
    if (n == 0)
      return;

    // Step 1: Build standard BVHNode tree (reuses existing tested code)
    BVHNode tree(list, method);

    // Step 2: Reserve approximate space (2*n - 1 nodes for n primitives)
    nodes.reserve(2 * n);
    primitives.reserve(n);
    owned_prims = list.owned_objects; // keep ownership

    // Step 3: DFS-flatten the tree
    flatten(&tree);

    // Step 4: Set adaptive traversal flag (same threshold as BVHNode)
    use_ordered = (n > BVHNode::ORDERED_THRESHOLD);
    root_all_opaque = tree.all_opaque;

    // std::cout << "[FlatBVH] " << nodes.size() << " nodes, " <<
    // primitives.size()
    //           << " primitives, " << (nodes.size() * sizeof(FlatNode))
    //           << " bytes" << std::endl;
  }

  // -----------------------------------------------------------------------------------------
  // HIT: Dispatch between simple and ordered traversal
  // -----------------------------------------------------------------------------------------
  virtual bool hit(const Ray &r, Real t_min, Real t_max,
                   HitRecord &rec) const override {
    if (nodes.empty())
      return false;
    if (use_ordered)
      return hit_ordered(r, t_min, t_max, rec);
    else
      return hit_simple(r, t_min, t_max, rec);
  }

  virtual bool bounding_box(AABB &output_box) const override {
    if (nodes.empty())
      return false;
    output_box = nodes[0].box;
    return true;
  }

  bool is_opaque() const override { return root_all_opaque; }

private:
  // -----------------------------------------------------------------------------------------
  // FLATTEN: DFS walk of BVHNode tree → linear array
  // -----------------------------------------------------------------------------------------
  // Returns the index of the node just written.
  uint32_t flatten(const BVHNode *node) {
    uint32_t my_index = static_cast<uint32_t>(nodes.size());
    nodes.push_back(FlatNode{});
    FlatNode &flat = nodes[my_index];

    flat.box = node->box;
    flat.split_axis = static_cast<uint8_t>(node->split_axis);
    flat.flags = node->all_opaque ? 1 : 0;

    bool left_is_leaf = node->left_is_leaf;
    bool right_is_leaf = node->right_is_leaf;

    // Case: both children are leaves (bottom of tree)
    if (left_is_leaf && right_is_leaf) {
      // Store left primitive
      uint32_t left_prim_idx = static_cast<uint32_t>(primitives.size());
      primitives.push_back(node->left_raw);
      primitives.push_back(node->right_raw);
      flat.second_child = left_prim_idx; // reuse as prim_start
      flat.num_prims = 2;
      return my_index;
    }

    // Case: left is leaf, right is internal
    if (left_is_leaf) {
      // Store left as single-prim leaf, then process right subtree
      // We make left a leaf node and right a subtree
      // Actually, flatten expects binary internal nodes. Let's handle this:
      // Create a leaf for left child
      uint32_t left_idx = static_cast<uint32_t>(nodes.size());
      nodes.push_back(FlatNode{});
      {
        AABB left_box;
        node->left_raw->bounding_box(left_box);
        FlatNode &left_flat = nodes[left_idx];
        left_flat.box = left_box;
        left_flat.second_child = static_cast<uint32_t>(primitives.size());
        left_flat.num_prims = 1;
        left_flat.split_axis = 0;
        left_flat.flags = node->left_raw->is_opaque() ? 1 : 0;
        primitives.push_back(node->left_raw);
      }

      // Recurse right
      uint32_t right_idx =
          flatten(static_cast<const BVHNode *>(node->right_raw));
      flat.second_child = right_idx;
      flat.num_prims = 0; // internal
      return my_index;
    }

    // Case: right is leaf, left is internal
    if (right_is_leaf) {
      // Recurse left (which becomes idx+1 implicitly)
      flatten(static_cast<const BVHNode *>(node->left_raw));

      // Create leaf for right child
      uint32_t right_idx = static_cast<uint32_t>(nodes.size());
      nodes.push_back(FlatNode{});
      {
        AABB right_box;
        node->right_raw->bounding_box(right_box);
        FlatNode &right_flat = nodes[right_idx];
        right_flat.box = right_box;
        right_flat.second_child = static_cast<uint32_t>(primitives.size());
        right_flat.num_prims = 1;
        right_flat.split_axis = 0;
        right_flat.flags = node->right_raw->is_opaque() ? 1 : 0;
        primitives.push_back(node->right_raw);
      }

      flat.second_child = right_idx;
      flat.num_prims = 0; // internal
      return my_index;
    }

    // Case: both children are internal BVH nodes
    // Left child is always at my_index + 1 (DFS order)
    flatten(static_cast<const BVHNode *>(node->left_raw));

    // Right child — store its index
    uint32_t right_idx = flatten(static_cast<const BVHNode *>(node->right_raw));
    flat.second_child = right_idx;
    flat.num_prims = 0; // internal
    return my_index;
  }

  // -----------------------------------------------------------------------------------------
  // SIMPLE TRAVERSAL (flat array, no ordering)
  // -----------------------------------------------------------------------------------------
  bool hit_simple(const Ray &r, Real t_min, Real t_max, HitRecord &rec) const {
    constexpr int MAX_STACK = 64;
    uint32_t stack[MAX_STACK];
    int stack_ptr = 0;
    bool any_hit = false;

    stack[stack_ptr++] = 0; // root

    while (stack_ptr > 0) {
      uint32_t idx = stack[--stack_ptr];
      const FlatNode &node = nodes[idx];

      if (!node.box.hit(r, t_min, t_max))
        continue;

      if (node.num_prims > 0) {
        // Leaf: test primitives
        for (uint16_t i = 0; i < node.num_prims; ++i) {
          if (primitives[node.second_child + i]->hit(r, t_min, t_max, rec)) {
            any_hit = true;
            t_max = rec.t;
          }
        }
      } else {
        // Internal: push right, then left (left popped first = DFS)
        stack[stack_ptr++] = node.second_child; // right child
        stack[stack_ptr++] = idx + 1;           // left child (always next)
      }
    }
    return any_hit;
  }

  // -----------------------------------------------------------------------------------------
  // ORDERED TRAVERSAL (flat array, front-to-back via split_axis)
  // -----------------------------------------------------------------------------------------
  bool hit_ordered(const Ray &r, Real t_min, Real t_max, HitRecord &rec) const {
    constexpr int MAX_STACK = 64;
    uint32_t stack[MAX_STACK];
    int stack_ptr = 0;
    bool any_hit = false;

    stack[stack_ptr++] = 0; // root

    while (stack_ptr > 0) {
      uint32_t idx = stack[--stack_ptr];
      const FlatNode &node = nodes[idx];

      if (!node.box.hit(r, t_min, t_max))
        continue;

      if (node.num_prims > 0) {
        // Leaf: test primitives
        for (uint16_t i = 0; i < node.num_prims; ++i) {
          if (primitives[node.second_child + i]->hit(r, t_min, t_max, rec)) {
            any_hit = true;
            t_max = rec.t;
          }
        }
      } else {
        // Internal: order children by ray direction
        uint32_t left_idx = idx + 1;
        uint32_t right_idx = node.second_child;

        // If ray goes in negative direction along split axis,
        // right child is nearer → push left first (popped last)
        if (r.dir[node.split_axis] < 0) {
          stack[stack_ptr++] = left_idx;  // far (popped last)
          stack[stack_ptr++] = right_idx; // near (popped first)
        } else {
          stack[stack_ptr++] = right_idx; // far
          stack[stack_ptr++] = left_idx;  // near
        }
      }
    }
    return any_hit;
  }
};
