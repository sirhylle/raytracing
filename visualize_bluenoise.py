import cpp_engine
import numpy as np
from PIL import Image
import os
import imageio.v3 as iio

def visualize_bluenoise():
    print("Visualizing Blue Noise Sampler...")
    
    engine = cpp_engine.Engine()
    
    # Load Blue Noise Texture
    bn_path = "blue_noise.png"
    if os.path.exists(bn_path):
        print(f"Loading {bn_path}...")
        bn_img = iio.imread(bn_path)
        if bn_img.ndim == 3:
            bn_img = bn_img[:, :, 0]
        bn_data = bn_img.astype(np.float32)
        if bn_img.dtype == np.uint8:
            bn_data /= 255.0
        engine.set_blue_noise_texture(np.ascontiguousarray(bn_data))
    else:
        print("Error: blue_noise.png not found!")
        return

    width, height = 512, 512
    spp = 1
    
    # Get sampler image for Sobol (sampler_type=1)
    # get_sampler_image(width, height, sampler_type, spp, dimension_offset)
    print("Generating Sobol + Blue Noise visualization...")
    result = engine.get_sampler_image(width, height, 1, spp, 0)
    
    img_data = np.array(result)
    img = Image.fromarray((np.clip(img_data, 0, 1) * 255).astype(np.uint8))
    img.save("visualize_bluenoise_spp1.png")
    print("Result saved to visualize_bluenoise_spp1.png")

    # Also generate a version without blue noise for comparison if possible?
    # Actually, we can just look at the result. If it's Blue Noise, we'll see it.
    
if __name__ == "__main__":
    visualize_bluenoise()
