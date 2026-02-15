"""
Benchmark: AABB Hit Performance
================================
Measures render time before/after branchless AABB optimization.
Uses scenes with high BVH traversal pressure (many objects = many AABB tests).

Usage:
  uv run benchmark_aabb.py              # Full benchmark (3 scenes × 3 runs)
  uv run benchmark_aabb.py --quick      # Quick check (1 scene × 1 run)

Instructions:
  1. Run BEFORE applying the branchless AABB change → save the output.
  2. Apply the change, rebuild (pip install -e . --no-build-isolation).
  3. Run AGAIN → compare timings.
"""

import time
import sys
import statistics
import numpy as np
import cpp_engine
import loader
import scenes
from config import EnvironmentSettings


def setup_scene(scene_name, width, height):
    """Set up engine + scene, return ready engine."""
    engine = cpp_engine.Engine()
    builder = loader.SceneBuilder(engine)
    scene = scenes.AVAILABLE_SCENES[scene_name]
    config_data = scene.setup(builder)

    def v3(l): return cpp_engine.Vec3(float(l[0]), float(l[1]), float(l[2]))
    aspect = width / height
    vup = config_data.vup if config_data.vup else [0, 1, 0]
    engine.set_camera(
        v3(config_data.lookfrom), v3(config_data.lookat), v3(vup),
        float(config_data.vfov), float(aspect),
        float(config_data.aperture or 0.0),
        float(config_data.focus_dist or 10.0)
    )

    # Environment: wrap SceneConfig fields into EnvironmentSettings
    env_source = config_data.environment
    if env_source is not None:
        env_settings = EnvironmentSettings(
            source=env_source,
            exposure=getattr(config_data, 'env_exposure', 1.0),
            background=getattr(config_data, 'env_background', 1.0),
            diffuse=getattr(config_data, 'env_diffuse', 0.5),
            specular=getattr(config_data, 'env_specular', 0.5),
            auto_sun=getattr(config_data, 'auto_sun', False),
            sun_intensity=getattr(config_data, 'auto_sun_intensity', 50.0),
            sun_radius=getattr(config_data, 'auto_sun_radius', 50.0),
            sun_dist=getattr(config_data, 'auto_sun_dist', 1000.0),
        )
        loader.load_environment(builder, env_settings)

    # Use SAH for consistent traversal cost
    engine.set_build_method(cpp_engine.SplitMethod.SAH)
    return engine, builder


def benchmark_scene(scene_name, width=960, height=720, spp=128, depth=6, runs=3):
    """Benchmark a single scene, returns list of render times."""
    print(f"\n{'='*60}")
    print(f"  Scene: {scene_name}  |  {width}x{height}  |  {spp} SPP  |  {runs} runs")
    print(f"{'='*60}")

    engine, builder = setup_scene(scene_name, width, height)

    obj_count = len(builder.registry)
    print(f"  Objects: {obj_count}")

    # Warmup (triggers BVH build + cache warmup)
    print("  Warmup...", end=" ", flush=True)
    engine.render(width, height, 1, depth, 0)
    print("done.")

    # Benchmark runs
    times = []
    for i in range(runs):
        t0 = time.perf_counter()
        engine.render(width, height, spp, depth, 0)
        t = time.perf_counter() - t0
        times.append(t)
        mrays = (width * height * spp) / t / 1e6
        print(f"  Run {i+1}/{runs}: {t:.3f}s  ({mrays:.1f} Mrays/s)")

    # Stats
    avg = statistics.mean(times)
    std = statistics.stdev(times) if len(times) > 1 else 0
    best = min(times)
    print(f"  ─── Average: {avg:.3f}s  (±{std:.3f}s)  |  Best: {best:.3f}s")
    return times


def main():
    quick = "--quick" in sys.argv

    print("╔══════════════════════════════════════════════════════════════╗")
    print("║           AABB HIT BENCHMARK (Before / After)              ║")
    print("╠══════════════════════════════════════════════════════════════╣")
    print("║  Tip: Run once BEFORE the change, once AFTER.              ║")
    print("║  Compare the 'Average' and 'Best' times.                   ║")
    print("╚══════════════════════════════════════════════════════════════╝")

    if quick:
        configs = [
            ("random", 480, 360, 64, 6, 1),
        ]
    else:
        configs = [
            # (scene, width, height, spp, depth, runs)
            # random: ~400 spheres, heavy BVH pressure
            ("random",   960, 720, 128, 6, 3),
            # cornell: few objects but deep bounces (glass, reflections)
            ("cornell",  960, 720, 128, 6, 3),
            # showcase: ~80+ mixed spheres with HDRI lighting
            ("showcase", 960, 720, 128, 6, 3),
        ]

    all_results = {}
    for scene_name, w, h, spp, depth, runs in configs:
        try:
            times = benchmark_scene(scene_name, w, h, spp, depth, runs)
            all_results[scene_name] = times
        except Exception as e:
            print(f"  ⚠ SKIPPED ({e})")
            import traceback
            traceback.print_exc()

    # Summary
    print(f"\n{'='*60}")
    print("  SUMMARY")
    print(f"{'='*60}")
    total_avg = 0
    for name, times in all_results.items():
        avg = statistics.mean(times)
        best = min(times)
        total_avg += avg
        mrays = (960 * 720 * 128) / best / 1e6
        print(f"  {name:12s}  avg={avg:.3f}s  best={best:.3f}s  ({mrays:.1f} Mrays/s)")
    if all_results:
        print(f"  {'TOTAL':12s}  avg={total_avg:.3f}s")
    print(f"{'='*60}")
    print("  Save this output, then compare with the post-optimization run.")


if __name__ == "__main__":
    main()
