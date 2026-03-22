import os
import requests
import time
import csv
import argparse
import re
import sys
import glob
from datetime import datetime
from PIL import Image
from google import genai
from google.genai import types

from dotenv import load_dotenv
load_dotenv()


# --- CONFIGURATION ---
LOCAL_ART_DIR = os.path.expanduser("~/herald-automation/artimage_tool/gallery")
RAW_DIR = "/home/paul/TabloidProject/website/public/images/raw"
WEB_BASE_DIR = "/home/paul/TabloidProject/website"
OUTPUT_DIR = os.path.expanduser("~/herald-automation/outputs")
LOGO_PATH = "/home/paul/TabloidProject/website/public/images/ELYU_Herald_Colored.png"

# --- THE HERALD STYLE BLOCK ---
STYLE_BLOCK = """Professional black-and-white editorial newspaper illustration. 
Clean, confident line art with medium line weight on a pristine, unblemished white paper background. 
Use a single spot color only to emphasize the main subject. 
Minimal shading, high contrast, ample white space. 
Centered composition with empty margins. 
Single subject only. No background clutter. No text, no symbols, no markings in the corners."""

def harvest_herald_data():
    """Finds the latest .md file and extracts Prompt from text + Slug from filename."""
    outputs_path = os.path.expanduser("~/herald-automation/outputs/*.md")
    list_of_files = glob.glob(outputs_path)
    
    if not list_of_files:
        return None, "manual_art", None

    # 1. Grab the most recent file
    latest_file = max(list_of_files, key=os.path.getmtime)
    file_name = os.path.basename(latest_file)
    
    # 2. Derive & Trim Slug from Filename
    # Strip prefixes and extensions, replace underscores with hyphens for splitting
    clean_name = file_name.replace("web_", "").replace(".md", "").replace("_", "-")
    
    if len(clean_name) > 20:
        # If it's a mouthful, take the first 3 words
        name_parts = clean_name.split("-")
        slug = "_".join(name_parts[:3])
    else:
        # If it's short (like 'la-union-gas'), just swap the hyphens for underscores
        slug = clean_name.replace("-", "_")

    # Ensure slug isn't empty if the filename was weird
    slug = slug or "herald_art"

    try:
        with open(latest_file, 'r') as f:
            content = f.read()
            # Look for the prompt at the end of the file
            prompt_match = re.search(r"IMAGE_PROMPT:\s*(.*)", content, re.IGNORECASE)
            # Still look for a SLUG: tag just in case it exists to override
            slug_match = re.search(r"SLUG:\s*([\w-]+)", content, re.IGNORECASE)
            
            if prompt_match:
                prompt = prompt_match.group(1).strip()
            if slug_match:
                slug = slug_match.group(1).strip().replace("-", "_")
                
    except Exception as e:
        print(f"⚠️ Error reading file content: {e}")

    return prompt, slug, file_name

def select_model():
    print("\n🎨 --- ELYU HERALD ART DEPARTMENT ---")
    print("1. [E]conomy (SiliconFlow / Flux.1-schnell) - $0.0014")
    print("2. [P]remium (Gemini / Imagen 4.0) - $0.0200")
    choice = input("\nWhich engine shall we use? (1/2): ").strip().lower()
    return "PREMIUM" if choice in ['2', 'p'] else "ECONOMY"

def generate_gemini_image(prompt):
    """The Premium Engine: Imagen 4.0 Fast (March 2026 Version)"""
    api_key = os.getenv('GEMINI_API_KEY')
    client = genai.Client(api_key=api_key)
    
    try:
        response = client.models.generate_images(
            model='imagen-4.0-fast-generate-001',
            prompt=prompt,
            config=types.GenerateImagesConfig(
                number_of_images=1,
                aspect_ratio="1:1",
                # The safest 'Production' defaults for 2026:
                person_generation="allow_adult",
                safety_filter_level="block_low_and_above"
            )
        )
        if response.generated_images:
            return response.generated_images[0].image.image_bytes
        
        print("⚠️ Gemini blocked the image. Try describing the SCENE instead of naming PEOPLE.")
        return None

    except Exception as e:
        print(f"\n🚀 --- HERALD AUDIT LOG ---")
        print(f"Server Details: {getattr(e, 'details', str(e))}")
        print(f"---------------------------\n")
        return None

def generate_siliconflow_image(prompt):
    """The Economy Engine: Powered by Flux.1-schnell"""
    api_key = os.getenv('SILICONFLOW_API_KEY')
    url = "https://api.siliconflow.com/v1/images/generations"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    
    payload = {
        "model": "black-forest-labs/FLUX.1-schnell",
        "prompt": prompt,
        "negative_prompt": "signature, watermark, text, letters, name, scribble, artist name, border",
        "batch_size": 1
    }
    
    try:
        res = requests.post(url, json=payload, headers=headers)
        res.raise_for_status()
        img_url = res.json()['images'][0]['url']
        return requests.get(img_url).content
    except Exception as e:
        print(f"💰 SiliconFlow Failure: {e}")
        return None

def add_logo_watermark(image_path):
    """Stamps the ELYU Herald logo on the bottom right."""
    if not os.path.exists(LOGO_PATH):
        return
    try:
        img = Image.open(image_path).convert("RGBA")
        logo = Image.open(LOGO_PATH).convert("RGBA")
        # Scale logo to 15% width
        width = int(img.width * 0.15)
        height = int(logo.height * (width / logo.width))
        logo = logo.resize((width, height), Image.Resampling.LANCZOS)
        # Position with 20px margin
        img.alpha_composite(logo, (img.width - width - 20, img.height - height - 20))
        img.convert("RGB").save(image_path)
    except Exception as e:
        print(f"⚠️ Watermark skip: {e}")

def save_and_optimize(img_bytes, article_name, is_premium):
    timestamp = datetime.now().strftime("%H%M%S")
    base_filename = f"{article_name}_{timestamp}"
    
    # 1. Save Raw PNGs
    for path in [LOCAL_ART_DIR, RAW_DIR]:
        os.makedirs(path, exist_ok=True)
        file_path = os.path.join(path, f"{base_filename}.png")
        with open(file_path, 'wb') as f:
            f.write(img_bytes)
        add_logo_watermark(file_path)

    # 2. Mogrify to Web JPG (Resize for Astro performance)
    print("📦 Optimizing for web...")
    os.system(f"cd {WEB_BASE_DIR} && mogrify -path public/images/ -resize 600x -format jpg public/images/raw/{base_filename}.png")
    
    # 3. Clipboard & Ledger
    web_path = f"/images/{base_filename}.jpg"
    os.system(f"echo -n '{web_path}' | xclip -selection clipboard")
    
    cost = f"{0.020000:.6f}" if is_premium else f"{0.001400:.6f}"
    log_file = os.path.join(OUTPUT_DIR, "gemini_cost_log.csv")
    with open(log_file, "a", newline="") as f:
        csv.writer(f).writerow([
            datetime.now().strftime("%Y-%m-%d %H:%M"), 
            "imagen-4.0" if is_premium else "flux.1", 
            "VISUAL", "", "", "", "", "", cost
        ])
    
    # --- PREPARE DATA FOR THE BOX ---
    model_name = "Imagen 4.0 (Premium)" if is_premium else "Flux.1 (Economy)"
    
    # --- THE SUCCESS BOX ---
    box_width = 60
    print("\n" + "╔" + "═" * (box_width - 2) + "╗")
    print(f"║ {'🎨 HERALD ART DEPARTMENT - JOB COMPLETE':^{box_width-4}} ║")
    print("╠" + "═" * (box_width - 2) + "╣")
    print(f"║  📂 Path:  {web_path:<46} ║")
    print(f"║  🤖 Model: {model_name:<46} ║")
    print(f"║  💰 Cost:  {cost:<46} ║")
    print(f"║  📋 Status: Copied to Clipboard! {' ':<23} ║")
    print("╚" + "═" * (box_width - 2) + "╝\n")

def main():
    parser = argparse.ArgumentParser(description="ELYU Herald Art Department")
    parser.add_argument('--manual', action='store_true', help="Force Manual Entry")
    args = parser.parse_args()

    # --- 1. THE HARVEST & PREVIEW ---
    if not args.manual:
        user_prompt, name, source_file = harvest_herald_data()
        
        if not user_prompt:
            print("❌ Error: No IMAGE_PROMPT found in the latest article. Switching to manual...")
            args.manual = True
        else:
            print(f"\n📂 [FILE DETECTED]: {source_file}")
            print(f"🏷️ [SLUG]: {name}")
            print(f"📝 [PROMPT]: {user_prompt}")
            
            confirm = input("\nProceed with this? (y)es / (n)o, edit it / (q)uit: ").strip().lower()
            
            if confirm == 'q':
                print("🛑 Operation cancelled.")
                sys.exit()
            elif confirm == 'n':
                print("✍️ [INTERVENTION] Enter your improved description:")
                user_prompt = input(">> ").strip()
                if not user_prompt:
                    print("❌ No prompt entered. Aborting.")
                    sys.exit()
            # If 'y' or Enter, we proceed with the harvested data
    
    if args.manual:
        name = input("\nArticle reference name (slug): ").strip() or "manual_art"
        user_prompt = input("Describe the scene: ").strip()

    # --- 2. ENGINE & STYLE (Financial Control) ---
    engine = select_model() # Calls your original select_model()
    is_premium = (engine == "PREMIUM")

    print("\n🎭 --- STYLE SELECTION ---")
    print("1. [H]erald Style (Sox-Strict Illustration)")
    print("2. [F]reestyle (Pure Prompt - No Restrictions)")
    style_choice = input("Choice (1/2): ").strip().lower()
    
    if style_choice in ['2', 'f']:
        final_prompt = user_prompt
        print("🚀 Freestyle Mode enabled...")
    else:
        final_prompt = f"{STYLE_BLOCK}\n\nScene: {user_prompt}"
        print("✍️ Applying Herald Style Block...")

    # --- 3. GENERATION & HANDOFF ---
    print(f"🎨 Generating with {engine}...")
    
    if is_premium:
        data = generate_gemini_image(final_prompt)
    else:
        data = generate_siliconflow_image(final_prompt)

    if data:
        # This triggers your original save_and_optimize (Watermark, Mogrify, xclip)
        save_and_optimize(data, name, is_premium)
    else:
        print("❌ Art creation failed. No funds spent.")

if __name__ == "__main__":
    main()