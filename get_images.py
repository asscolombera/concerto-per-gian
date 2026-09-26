import os
import json

def get_images(target_directory="."):
    # Supported web formats
    valid_extensions = ('.jpg', '.jpeg', '.png', '.webp', '.gif', '.svg')
    image_paths = []
    
    # Folders to completely skip during recursion to save time and memory
    ignored_folders = {
        'node_modules', '.git', 'css', 'js', 'dist', 
        'plugin', 'lib', '.github', '__pycache__', 'reveal.js', 'slides'
    }
    
    for root, dirs, files in os.walk(target_directory):
        # Modifying dirs in-place tells os.walk to skip these folders entirely
        dirs[:] = [d for d in dirs if d not in ignored_folders and not d.startswith('.')]
        
        for file in files:
            if file.lower().endswith(valid_extensions):
                clean_path = os.path.join(root, file).replace('\\', '/')
                
                # Strip leading './' for clean relative web URLs
                if clean_path.startswith('./'):
                    clean_path = clean_path[2:]
                    
                image_paths.append(clean_path)
                
    image_paths.sort()
    
    # Export as a JavaScript payload instead of raw JSON
    output_file = 'images.js'
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("// Generated automatically by get_images.py\n")
        f.write("window.slideshowImages = ")
        json.dump(image_paths, f, indent=2)
        f.write(";\n")
        
    print(f" Success! Discovered {len(image_paths)} images.")
    print(f"Saved local JavaScript module manifest to: {output_file}")

if __name__ == "__main__":
    get_images(".")

