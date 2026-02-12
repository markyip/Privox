from PIL import Image, ImageDraw
import os

def generate_icon():
    # Asset Dir
    assets_dir = os.path.join(os.path.dirname(os.getcwd()), "assets") # Assuming run from scripts/
    # Actually just assume relative to executable or absolute path provided?
    # Let's use absolute path relative to this script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(script_dir)
    assets_dir = os.path.join(root_dir, "assets")
    
    if not os.path.exists(assets_dir):
        os.makedirs(assets_dir)
        
    size = (256, 256)
    # Background: Dark Blue/Grey (20, 20, 28) matches "Privox" vibe? Or just black/transparent?
    # Reference image has dark bg.
    bg_color = (25, 25, 35, 255) 
    bar_color = (255, 255, 255, 255)
    
    # Create Base Image
    image = Image.new("RGBA", size, bg_color)
    draw = ImageDraw.Draw(image)
    
    # Waveform Bars: 4 bars
    # "W" shape: Tall, Short, Tall, Medium?
    # Or M shape: Short, Tall, Tall, Short?
    # Let's do: Medium, Low, High, Medium.
    # Like a voice wave.
    
    num_bars = 4
    bar_width_ratio = 0.15 # 15% of width
    gap_ratio = 0.08      # 8% gap
    
    bar_w = int(size[0] * bar_width_ratio)
    gap = int(size[0] * gap_ratio)
    
    total_w = (num_bars * bar_w) + ((num_bars - 1) * gap)
    start_x = (size[0] - total_w) // 2
    
    # Heights relative to center (0.5)
    # Let's say max height is 80%
    heights = [0.6, 0.4, 0.8, 0.5] 
    
    center_y = size[1] // 2
    
    for i, h_ratio in enumerate(heights):
        h = int(size[1] * h_ratio)
        x = start_x + i * (bar_w + gap)
        y_top = center_y - (h // 2)
        y_bottom = center_y + (h // 2)
        
        # Draw Rounded Bar (Pill)
        # Top Circle
        draw.ellipse((x, y_top, x + bar_w, y_top + bar_w), fill=bar_color)
        # Bottom Circle
        draw.ellipse((x, y_bottom - bar_w, x + bar_w, y_bottom), fill=bar_color)
        # Rect
        draw.rectangle((x, y_top + (bar_w//2), x + bar_w, y_bottom - (bar_w//2)), fill=bar_color)

    # Save to both name variations
    for name in ["privox", "app_icon"]:
        png_path = os.path.join(assets_dir, f"{name}.png")
        image.save(png_path)
        ico_path = os.path.join(assets_dir, f"{name}.ico")
        image.save(ico_path, format="ICO", sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
        print(f"Saved PNG/ICO for: {name}")

if __name__ == "__main__":
    generate_icon()
