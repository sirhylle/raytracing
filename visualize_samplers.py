import cpp_engine
import numpy as np
from PIL import Image
import os

def generate_comparison():
    print("Generating Sampler Noise Comparison (High Precision)...")
    engine = cpp_engine.Engine()
    
    width, height = 512, 512
    
    samplers = [
        ("Random", 0),
        ("Sobol", 1)
    ]
    
    # Test SPP 1 and SPP 16
    spp_counts = [1, 16]
    
    for spp in spp_counts:
        for name, s_type in samplers:
            print(f"  Visualizing {name} noise at SPP {spp}...")
            img_data = engine.get_sampler_image(width, height, s_type, spp, 0)
            
            # Convert to 8-bit image
            img = Image.fromarray((img_data * 255).astype(np.uint8))
            filename = f"sampler_noise_{name.lower()}_spp{spp}.png"
            img.save(filename)
            print(f"  Saved to {filename}")

if __name__ == "__main__":
    generate_comparison()
