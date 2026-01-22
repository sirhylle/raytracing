# Path Tracing: A Step-by-Step Guide

This document explains the **Path Tracing** algorithm as implemented in this engine. It is designed for readers who want to understand *what happens* when a pixel is rendered, without diving into the C++ implementation.

---

## 1. The Big Picture

Path Tracing is a method to simulate how light travels in a real environment. Instead of "tracing" rays from the light source to the camera (which would be inefficient because most rays never hit the camera), we do the reverse: **we trace rays from the camera into the world**.

For every pixel on your screen, the engine asks: *"If I look through this pixel, what do I see?"*

The color of a single pixel is calculated by averaging hundreds or thousands of **samples** (rays). The more samples, the smoother the image (less noise).

---

## 2. The Sampling Loop (The "Monte Carlo" Part)

This is the most critical concept to understand. The engine does NOT just calculate `ray_color()` once per pixel.

**For every single pixel, we run the entire process below hundreds or thousands of times.**

Each time we run it, we make slightly different random choices:
- We pick a slightly different position inside the pixel (Anti-Aliasing).
- We pick a slightly different point on the lens (Depth of Field).
- We pick a totally different bounce direction when hitting a wall (Diffuse reflection).

**The Final Pixel Color is the AVERAGE of all these random tries.**
`Final_Color = (Try_1 + Try_2 + ... + Try_1000) / 1000`


---

## 3. The Lifecycle of a Single Ray

The core function `ray_color()` calculates the light energy (radiance) carried by **one specific path**. This process is recursive.

### Step 1: Ray Generation (Camera)
*Random Choice #1 (Pixel Position) & #2 (Lens Position)*
1. We pick a random sub-pixel offset. If we didn't, edges would look jagged (aliased).
2. We simulate a lens by picking a random start point on the aperture.
3. We cast a ray from this lens point towards the pixel's focal plane.


### Step 2: Intersection (BVH)
The ray flies into the scene. It needs to know: *"What is the first object I hit?"*
- We check efficient Bounding Boxes (BVH) to skip empty space.
- Eventually, we find the closest geometric primitive (Sphere, Triangle, or Quad).
- If we hit nothing, we return the **Background Color** (Environment Map).

### Step 3: Emission
If the ray hits a light source (like a glowing sphere or a lamp), we immediately collect that light. This is `L_e` (Emitted Light).

### Step 4: The Decision (BSDF)
Now the ray is sitting on a surface point `P`. It needs to bounce.
The material determines *how* it bounces:
- **Matte (Lambertian)**: The ray is scattered continuously in a random direction.
- **Metal**: The ray is reflected like a mirror (angle in = angle out), maybe with some fuzziness.
- **Glass (Dielectric)**: The ray might reflect OR pass through (refract), depending on the angle (Fresnel effect).

### Step 5: Direct Lighting (Next Event Estimation)
*This is a crucial optimization.*
Waiting for a ray to randomly bounce into a small light bulb is very slow (it creates noise).
Instead, at every bounce on a matte surface, we **force** a check:
*Random Choice #3 (Light Position)*
1. We pick a random point on a light source (e.g., the Sun or a Quad Light).
2. We cast a "Shadow Ray" towards it.
3. If the shadow ray hits nothing (unobstructed), we calculate the light received and add it immediately.

This is why scenes light up relatively quickly even with few samples.

### Step 6: Indirect Lighting (Recursion)
*Random Choice #4 (Bounce Direction)*
After direct light, the ray must continue to find *indirect* light.
- We pick a **new random direction** based on the material (BSDF). 
  - *Example: For a matte wall, we pick any random upward direction. Each sample will likely pick a different one.*
- We launch a new ray from `P` in that direction.
- We multiply the current accumulated color by the surface color (Albedo).
- **Repeat Step 2.**


### Step 7: Termination (Russian Roulette)
To prevent infinite loops (reflection inside two mirrors), we stop when:
- The ray hits the max depth (e.g., 50 bounces).
- Or via "Russian Roulette": as the ray gets darker (loses energy), we randomly kill it to save computation time.

---

## 4. The Algorithm in Pseudocode

Here is the logic simplified:

```python
function ray_color(Ray r, depth):
    if depth <= 0:
        return Black  # Stop recursion
    
    # 1. Did we hit anything?
    hit_record = world.hit(r)
    if not hit_record:
        return EnvironmentMap(r)  # Sky color

    # 2. Emission (Did we hit a light?)
    emitted = hit_record.material.emit()
    
    # 3. Direct Light Sampling (NEE)
    # Check lights explicitly to reduce noise
    direct_light = 0
    if not is_mirror(hit_record.material):
        light_sample = pick_random_light()
        shadow_ray = Ray(hit_record.point, light_sample.direction)
        if not world.hit(shadow_ray):  # Visible?
            direct_light = light_sample.intensity * material.color

    # 4. Indirect Light (Bounce)
    # Ask material for a new direction
     scattered_ray = hit_record.material.scatter(r)
    
    # Recurse!
    indirect_light = material.color * ray_color(scattered_ray, depth - 1)

    return emitted + direct_light + indirect_light
```

---

## 5. Key Concepts

### BVH (Bounding Volume Hierarchy)
Imagine finding a file in a messy room vs. a filing cabinet.
- **Without BVH**: The ray checks every single triangle in the scene. (Slow!)
- **With BVH**: The scene is organized into boxes inside boxes. If the ray misses the "Kitchen" box, it doesn't bother checking the "Table" or "Chair" inside.

### PDF (Probability Density Function)
When we pick a random direction or a random light, we need to know "how likely" that choice was, to weight the math correctly.
- If we pick a small light far away, the chance is low, but the brightness is high -> It balances out.
- This ensures the image converges to the *physically correct* brightness.

### Accumulation
The engine runs the loop above thousands of times per pixel.
`Pixel_Final_Color = Sum_of_All_Rays / Number_of_Rays`
This averaging process removes the "static" (noise) inherent in random sampling.

### SPP vs. Branching (What means n SPP?)
A common question is: *"Does n SPP mean n rays at every single bounce?"*
**NO.** Path Tracing is a "1-in, 1-out" process (no branching).
- **Camera Step**: We fire n separate rays for the pixel.
- **Bounce Step**: Each of those rays bounces in **ONLY ONE** random direction.
- We rely on the fact that Ray #1 might bounce Left, and Ray #2 might bounce Right.
- If we branched (e.g., 2 rays per bounce), the number of rays would explode exponentially ($2^{depth}$). Path Tracing keeps it linear ($1 \times depth$).
