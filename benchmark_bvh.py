
import time
import cpp_engine
import loader
import scenes
from config import RenderConfig

def benchmark(scene_name="mesh2", width=800, height=600, spp=100):
    print(f"--- BENCHMARK: {scene_name} ({width}x{height}, {spp} SPP) ---")
    
    # 1. Setup Engine & Scene
    engine = cpp_engine.Engine()
    builder = loader.SceneBuilder(engine)
    scene = scenes.AVAILABLE_SCENES[scene_name]
    config_data = scene.setup(builder)
    
    # Apply Camera
    def v3(l): return cpp_engine.Vec3(float(l[0]), float(l[1]), float(l[2]))
    aspect = width / height
    vup = config_data.vup if config_data.vup else [0, 1, 0]
    engine.set_camera(v3(config_data.lookfrom), v3(config_data.lookat), v3(vup),
                      float(config_data.vfov), float(aspect), float(config_data.aperture or 0.0), float(config_data.focus_dist or 10.0))
    
    # Load Environment
    if config_data.env_map:
        loader.load_environment(builder, config_data.env_map)

    # 2. Measure Midpoint
    print("Building BVH (Midpoint)...")
    engine.set_build_method(cpp_engine.SplitMethod.Midpoint)
    
    t0 = time.time()
    # First render triggers build
    engine.render_preview(width, height, 0, 0) 
    t_build_mid = time.time() - t0
    print(f"Build Time (Midpoint): {t_build_mid:.4f}s")
    
    t0 = time.time()
    engine.render(width, height, spp, 6, 0)
    t_render_mid = time.time() - t0
    print(f"Render Time (Midpoint): {t_render_mid:.4f}s")

    # 3. Measure SAH
    print("Building BVH (SAH)...")
    engine.set_build_method(cpp_engine.SplitMethod.SAH)
    
    t0 = time.time()
    # First render triggers build
    engine.render_preview(width, height, 0, 0)
    t_build_sah = time.time() - t0
    print(f"Build Time (SAH): {t_build_sah:.4f}s")
    
    t0 = time.time()
    engine.render(width, height, spp, 6, 0)
    t_render_sah = time.time() - t0
    print(f"Render Time (SAH): {t_render_sah:.4f}s")
    
    # Results
    print(f"\n--- RESULTS ---")
    print(f"Midpoint Total: {t_build_mid + t_render_mid:.4f}s")
    print(f"SAH Total:      {t_build_sah + t_render_sah:.4f}s")
    improv = (t_render_mid - t_render_sah) / t_render_mid * 100.0
    print(f"Render Speedup: {improv:.2f}%")

if __name__ == "__main__":
    benchmark("random")
    benchmark("showcase")
    benchmark("mesh1")
    benchmark("mesh2")
