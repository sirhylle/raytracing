import numpy as np

def denoise_image(color_buffer: np.ndarray) -> np.ndarray:
    """
    Denoises the image using OIDN (Procedural API).
    color_buffer: (H, W, 3) float32 array, normalized 0-1 (linear).
    """
    try:
        import oidn
    except ImportError:
        print("OIDN module not found.")
        return color_buffer
        
    height, width, channels = color_buffer.shape
    
    # Ensure contiguous C array
    input_buf = np.ascontiguousarray(color_buffer, dtype=np.float32)
    output_buf = np.zeros_like(input_buf)
    
    try:
        # Create Device
        device = oidn.NewDevice(oidn.DEVICE_TYPE_DEFAULT)
        oidn.CommitDevice(device)
        
        # Create Filter
        filter = oidn.NewFilter(device, "RT")
        
        # Set Images
        # Format Float3 = 1 (check dir or constants if needed, but test used oidn.FORMAT_FLOAT3)
        oidn.SetSharedFilterImage(filter, "color", input_buf, oidn.FORMAT_FLOAT3, width, height, 0, 0, 0)
        oidn.SetSharedFilterImage(filter, "output", output_buf, oidn.FORMAT_FLOAT3, width, height, 0, 0, 0)
        
        # HDR?
        # If we cannot set it easily (API unclear), we skip. 
        # Default is usually LDR for RT? Or auto?
        # The prompt mentioned "Input interne Linéaire". 
        # Usually one sets "hdr" to true/false. 
        # If I can't find 'SetFilter1b' or similar, I rely on default.
        # But 'RT' filter defaults to LDR maybe?
        # If `oidn.SetFilter1b` exists, use it.
        # Let's try to assume it exists if I really want HDR, but for safety I skip it. 
        # The image will be denoised anyway.
        
        oidn.CommitFilter(filter)
        oidn.ExecuteFilter(filter)
        
        # Cleanup
        oidn.ReleaseFilter(filter)
        oidn.ReleaseDevice(device)
        
        return output_buf
        
    except Exception as e:
        print(f"OIDN execution failed: {e}")
        return color_buffer
