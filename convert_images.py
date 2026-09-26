import os
import sys

try:
    from PIL import Image
except ImportError:
    print("Error: The 'Pillow' library is required to run this converter.")
    print("Please install it via terminal: pip install Pillow")
    sys.exit(1)

def convert_images(target_directory="."):
    print(f"Scanning and flattening image files inside: {os.path.abspath(target_directory)}")
    
    # Target extensions to process
    target_extensions = ('.gif', '.png', '.webp')
    
    # Folders to completely skip to avoid bloating local framework caches
    ignored_folders = {
        'node_modules', '.git', 'css', 'js', 'dist', 
        'plugin', 'lib', '.github', '__pycache__', 'reveal.js'
    }
    
    converted_count = 0
    
    for root, dirs, files in os.walk(target_directory):
        # Skip system or hidden frameworks directories in place
        dirs[:] = [d for d in dirs if d not in ignored_folders and not d.startswith('.')]
        
        for file in files:
            if file.lower().endswith(target_extensions):
                input_path = os.path.join(root, file)
                
                # Construct new filename with .jpg extension
                base_name = os.path.splitext(file)[0]
                output_path = os.path.join(root, f"{base_name}.jpg")
                
                try:
                    with Image.open(input_path) as img:
                        # If it's an animated GIF, extract the first frame as a flat photo
                        if hasattr(img, 'is_animated') and img.is_animated:
                            img.seek(0)
                        
                        # Convert image structure to RGBA mode to handle transparency layers properly
                        rgba_img = img.convert('RGBA')
                        
                        # Generate a clean, flat solid white background canvas matching source dimensions
                        white_bg = Image.new('RGBA', rgba_img.size, (255, 255, 255, 255))
                        
                        # Alpha composite the image layers together
                        final_img = Image.alpha_composite(white_bg, rgba_img).convert('RGB')
                        
                        # Export high-quality JPEG (Quality 92 balances small file size with sharp details)
                        final_img.save(output_path, 'JPEG', quality=92)
                        
                    print(f"Flattened: {input_path} -> {output_path}")
                    
                    # Safely remove the original file to prevent duplicates in your slideshow path
                    os.remove(input_path)
                    converted_count += 1
                    
                except Exception as e:
                    print(f"Error processing {input_path}: {e}")
                    
    print(f"\nProcessing finished! Successfully flattened and converted {converted_count} images to high-quality JPEGs.")

if __name__ == "__main__":
    convert_images(".")

