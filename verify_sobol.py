import cpp_engine
import numpy as np
from PIL import Image
import time

def verify_sobol():
    print("Testing Sobol Sampler performance...")
    
    try:
        # Simple scene setup (minimal)
        scene = cpp_engine.Engine()
        
        # set_camera(from, at, up, vfov, aspect, ap, dist)
        scene.set_camera(cpp_engine.Vec3(0, 0, 3), cpp_engine.Vec3(0, 0, 0), cpp_engine.Vec3(0, 1, 0), 40, 1.0, 0.0, 3.0)
        
        # Add a light sphere
        scene.add_sphere(cpp_engine.Vec3(0, 5, 0), 1.0, "light", cpp_engine.Vec3(10, 10, 10))
        
        # Add a sphere to test materials
        # add_sphere(center, radius, mat_type, color, roughness, metallic, ir, transmission)
        scene.add_sphere(cpp_engine.Vec3(0, 0, -1), 0.5, "standard", cpp_engine.Vec3(0.8, 0.3, 0.3), 0.1, 0.0, 1.5, 0.0)
        
        # Add a floor
        # add_quad(Q, u, v, mat_type, color, roughness, metallic, ir, transmission)
        scene.add_quad(cpp_engine.Vec3(-10, -0.5, -10), cpp_engine.Vec3(20, 0, 0), cpp_engine.Vec3(0, 0, 20), "standard", cpp_engine.Vec3(0.8, 0.8, 0.8), 0.5, 0.0, 1.5, 0.0)
        
        # Set a simple environment (1x1 white)
        env_img = np.array([[[1.0, 1.0, 1.0]]], dtype=np.float32)
        scene.set_environment(env_img)
        
        width, height = 512, 512
        spp = 100
        depth = 50
        
        # Test Sobol (sampler_type=1)
        start_time = time.time()
        print(f"Starting Sobol render ({width}x{height}, {spp} spp)...")
        # render(width, height, spp, depth, n_threads, sampler_type)
        result = scene.render(width, height, spp, depth, 1, 1) # 1 thread, sampler_type=1 (Sobol)
        end_time = time.time()
        print(f"Sobol render completed in {end_time - start_time:.2f} seconds.")
        
        # Save image
        # Note: nanobind ndarray can be converted to numpy array directly if it's compatible
        img_data = np.array(result["color"]) 
        # Render returns (H, W, 3)
        img = Image.fromarray((np.clip(img_data, 0, 1) * 255).astype(np.uint8))
        img.save("verify_sobol_result.png")
        print("Result saved to verify_sobol_result.png")

        # Test Random (sampler_type=0)
        start_time = time.time()
        print(f"Starting Random render ({width}x{height}, {spp} spp)...")
        # render(width, height, spp, depth, n_threads, sampler_type)
        result = scene.render(width, height, spp, depth, 1, 0) # 1 thread, sampler_type=0 (Random)
        end_time = time.time()
        print(f"Random render completed in {end_time - start_time:.2f} seconds.")
        
        # Save image
        # Note: nanobind ndarray can be converted to numpy array directly if it's compatible
        img_data = np.array(result["color"]) 
        # Render returns (H, W, 3)
        img = Image.fromarray((np.clip(img_data, 0, 1) * 255).astype(np.uint8))
        img.save("verify_random_result.png")
        print("Result saved to verify_random_result.png")
        
    except Exception as e:
        print(f"Render failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    verify_sobol()
