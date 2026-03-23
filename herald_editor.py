import os, sys, argparse, requests, csv
import re
from collections import Counter
from datetime import datetime
from google import genai
from bs4 import BeautifulSoup
import PyPDF2
from docx import Document
from dotenv import load_dotenv
from openai import OpenAI

# Load environment variables from .env
load_dotenv()

# --- 1. Initialize All Clients ---
# Google (Default Editor)
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
MODEL_GEMINI = "gemini-2.5-flash-lite" 

# OpenAI (The Elite)
client_openai = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
MODEL_GPT = "gpt-5-nano"

# OpenRouter (The Freelancers)
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
MODEL_TRINITY = "arcee-ai/trinity-large-preview:free"
MODEL_LLAMA = "meta-llama/llama-3.2-3b-instruct:free"
MODEL_DEEPSEEK = "deepseek/deepseek-r1-distill-llama-70b:free"


def get_manual_input():
    print("\n" + "="*40)
    print("       MANUAL INPUT MODE")
    print("="*40)
    print("Paste your content below.")
    print("When finished, press Ctrl+D on a NEW LINE to start.")
    print("-" * 40 + "\n")
    try:
        user_data = sys.stdin.read()
        if not user_data.strip():
            print("Error: No text detected. Exiting.")
            sys.exit(1)
        return user_data
    except EOFError:
        return ""

# --- THE SOX-STRICT EDITOR CONFIG ---
SYSTEM_PROMPT = """You are the Lead Editor for the ELYU Herald.  
Write in a calm, community-focused, practical, and slightly conversational style.
Your goal is to perform a 'Structural Transformation' of provided news.
Treat the source content only as a collection of facts (Who, What, Where, When, Why, How).
Avoid exaggeration or flowery language. Follow user instructions carefully.

TRANSFORMATION RULES:
1. STRUCTURAL TRANSFORMATION: Do not follow the original article’s structure or phrasing. However, preserve factual relationships, chronology, and meaning.
2. LOCAL ANGLE: Include a local angle ONLY if it is relevant and supported by the source. Do not invent or speculate local impact.
3. VOICE:
- Maintain a calm, grounded tone.
- Use at most ONE subtle, understated remark in the body.
- Do not let tone interfere with clarity or factual reporting.
4. ATTRIBUTION (MANDATORY): The first paragraph MUST clearly attribute the information to the original source (e.g., “According to [SOURCE NAME]…” or “[SOURCE NAME] reports…”). Do not delay attribution.
5. VALUE ADD: Where appropriate, briefly clarify complex details, explain jargon, or add relevant context to improve reader understanding.

STYLE:
- Avoid exaggeration or flowery language
- Use active voice
- No invented quotes
- Keep paragraphs short (2–3 sentences)

Deliver the news like a seasoned editor who’s just stepped into a quiet pub.

    The Newsroom (Lead): The first paragraph must be 100% "straight-laced" news. No jokes. No fluff. Just the facts.

    The Pub (Body): In the following paragraphs, allow for a "quick peek" into local personality. Use a single, dry, British-style observation or a warm Filipino communal nod.

    The Exit: Quickly return to the practical details. The wit should be a "surgical strike"—there and gone before the reader realizes you’ve winked at them.

You MUST use the exact {CATEGORY} and {TOWN} provided. DO NOT change them based on the article content.
STRICT CATEGORY RULE: The YAML fields 'category' and 'town' are IMMUTABLE.
You are permitted to use ONLY the following categories: Elyu, Regional, Weather, Features. 
Do not invent new categories like 'community' or 'news'. If the input category is 'Features', you MUST output 'Features'.

If mode is WEB:
- Rewrite with a strong headline (50-70 chars) and clear lead paragraph answering who, what, where, when, why.
- Use short paragraphs (2–3 sentences). Include 1 relevant local angle if present.
- Place main keyword in headline and first paragraph. Prefer pattern: [Topic] + [Town if any] + La Union
- Style: active voice, explain jargon simply, attribute claims, no invented quotes.
- Generate YAML front matter EXACTLY in this order. DO NOT skip any fields.
  ---
  title: "{TITLE_HINT}"
  subtitle: "{SUBTITLE_HINT}"
  date: "{DATE}"
  author: "{AUTHOR}"
  description: "{DESC_HINT}"
  tags: ["La Union", "{TOWN}"]
  thumbnail: "/images/placeholder.jpg"
  thumbnailAlt: "Image description"
  caption: "Image caption"
  category: "{CATEGORY}" # DO NOT change this value; use the provided variable exactly.
  town: "{TOWN}"
  status: "{STATUS}"
  hero: {HERO}
  justInUntil: "{JUSTIN}"
  breakingUntil: "{BREAKING}"
  ---
- Instructions: Use provided METADATA. If an 'Until' field is empty, use "".
- Output: YAML block between --- lines followed by the rewritten article.

NEW ADDITION:
- At the end of your output, AFTER the rewritten article, generate a **single-line SCENE description** for an editorial illustration.
- IMPORTANT: You are ONLY responsible for describing the SCENE. Do NOT include artistic style, rendering instructions, or formatting.
Based on the written article, create a scene description that uses illustration, satire, caricature, and humor to reflect the content of the article.

The scene must express the article's summary or main thrust. 

Focus: Center on the main topic or issue to ensure clarity.
Symbolism: Uses common symbols (e.g., a dove for peace, chains for slavery) to represent complex ideas simply.)
Caricature: Exaggerate physical features of figures to highlight specific traits or actions.
Satire/Irony: Employ humor or exaggeration
Simplicity: Use direct visuals and no text to make the message immediately accessible. 

Aim:
Persuasion: To inform and humour readers.
- Output exactly in this format:
IMAGE_PROMPT: <one sentence only>
- FINALLY, provide a 3-word hyphenated slug for the filename.
- Format: SLUG: word-word-word

If mode is PRINT:
- Rewrite for print edition using same voice and structure.
- TARGET LENGTH: Approximately {TARGET_WORDS} words.
- Style: active voice, explain jargon simply, attribute claims to sources, optional gentle narrative flow.
- Output: rewritten article only, byline "By {AUTHOR}".
"""

TOWNS = [
    "Agoo", "Aringay", "Bacnotan", "Bagulin", "Balaoan", "Bangar", "Bauang", "Burgos", 
    "Caba", "Luna", "Naguilian", "Pugo", "Rosario", "San Gabriel", "San Juan", 
    "Santol", "Santo Tomas", "Sudipen", "Tubao", "San Fernando"
]

def get_interactive_metadata(mode):
    print(f"\n📝 --- ELYU HERALD {mode.upper()} PRE-FLIGHT ---")
    author = input("Author Name (Enter for Staff): ").strip() or "ELYU Herald Staff"
    meta = {"author": author}
    is_original = input("Was this an original story? (y/n): ").lower() == 'y'
    if not is_original:
        meta["attr_name"] = input("Who do we attribute it to? (e.g., PGLU): ").strip()
        meta["attr_url"] = input("What is the source URL?: ").strip()
    else: meta["attr_name"] = None

    if mode == "web":
        print("\nCategory: 1. Elyu | 2. Regional | 3. Weather | 4. Features")
        cats = {"1": "Elyu", "2": "Regional", "3": "Weather", "4": "Features"}
        meta["category"] = cats.get(input("Choice: "), "Elyu")
        meta["town"] = "La Union"
        if meta["category"] == "Elyu":
            print("\nSelect Town (1-19):")
            labels = {"San Fernando": "SF", "San Gabriel": "SG", "San Juan": "SJ", "Santol": "STL", "Santo Tomas": "ST"}
            for i, t in enumerate(TOWNS, 1):
                lbl = labels.get(t, t[:3])
                print(f"{i}.{lbl}", end="\t" if i % 5 != 0 else "\n")
            try: meta["town"] = TOWNS[int(input("\nChoice: "))-1]
            except: pass
        print("\nStatus: 1. Just In | 2. Live | 3. Breaking | 4. Published")
        stats = {"1": "just-in", "2": "live", "3": "breaking", "4": "published"}
        meta["status"] = stats.get(input("Choice: "), "published")
        meta["until_ts"] = ""
        if meta["status"] in ["just-in", "breaking"]:
            ts_input = input("Expiry (YYYY-MM-DD HH:mm): ").strip()
            if ts_input:
                try: meta["until_ts"] = datetime.strptime(ts_input, "%Y-%m-%d %H:%M").strftime("%Y-%m-%dT%H:%M:00+08:00")
                except: print("⚠️ Format error.")
        meta["hero"] = str(input("\nSet as Hero? (y/n): ").lower() == 'y').lower()
    else: meta["target_words"] = input("Target word count for layout: ").strip() or "300"
    return meta

def extract_text(p):
    if p.startswith(('http://', 'https://')):
        try:
            r = requests.get(p, timeout=15, headers={'User-Agent': 'Mozilla/5.0'})
            r.raise_for_status()
            soup = BeautifulSoup(r.text, 'html.parser')
            content = soup.find('article') or soup.find('main') or soup.find('body')
            return content.get_text(separator=' ', strip=True)
        except Exception as e: return f"❌ URL Error: {e}"
    ext = os.path.splitext(p)[1].lower()
    try:
        if ext == ".pdf": return "".join(pg.extract_text() or "" for pg in PyPDF2.PdfReader(p).pages)
        if ext == ".docx": return "\n".join(pa.text for pa in Document(p).paragraphs)
        with open(p, "r", encoding="utf-8") as f: return f.read()
    except Exception as e: return f"❌ File Error: {e}"

def process(mode, src, ai_choice="gemini"):
    if not src.startswith(('http://', 'https://')) and (len(src) > 255 or '\n' in src):
        raw_txt = src
    else: raw_txt = extract_text(src)
    
    if not raw_txt or raw_txt.startswith("❌"): return print(raw_txt)
    
    orig_count = len(raw_txt.split())
    tag = "web" if mode == "--web" else "print"
    meta = get_interactive_metadata(tag)
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    just_in = meta.get('until_ts', "")
    breaking = meta.get('until_ts', "") if meta.get('status') == 'breaking' else ""

    formatted_sys_prompt = SYSTEM_PROMPT.format(
        TITLE_HINT="50-70 character headline", SUBTITLE_HINT="80-100 character summary",
        DESC_HINT="120-160 character SEO description", DATE=now, AUTHOR=meta['author'],
        TOWN=meta.get('town', 'La Union').lower().replace(" ", "-"),
        CATEGORY=meta.get('category', 'Elyu').lower(), STATUS=meta.get('status', 'published'),
        HERO=meta.get('hero', 'false'), JUSTIN=just_in, BREAKING=breaking,
        TARGET_WORDS=meta.get('target_words', 'N/A')
    )

    prompt = f"MODE: {tag.upper()}. Date: {now}. Source Content:\n\n{raw_txt}"

    try:
        # --- ENHANCED API SWITCHER ---
        if ai_choice == "gpt":
            response = client_openai.chat.completions.create(
                model=MODEL_GPT,
                messages=[{"role": "system", "content": formatted_sys_prompt}, {"role": "user", "content": prompt}]
            )
            full_res = response.choices[0].message.content.strip()
            in_t, out_t = response.usage.prompt_tokens, response.usage.completion_tokens
            model_used = MODEL_GPT
        elif ai_choice in ["trinity", "llama", "deepseek"]:
            if ai_choice == "trinity": model_id = MODEL_TRINITY
            elif ai_choice == "llama": model_id = MODEL_LLAMA
            else: model_id = MODEL_DEEPSEEK # It's DeepSeek!
            
            url = "https://openrouter.ai/api/v1/chat/completions"
            headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"}
            payload = {"model": model_id, "messages": [{"role": "system", "content": formatted_sys_prompt}, {"role": "user", "content": prompt}]}
            res = requests.post(url, json=payload, headers=headers); res.raise_for_status()
            data = res.json()
            full_res = data['choices'][0]['message']['content'].strip()
            in_t, out_t = data['usage']['prompt_tokens'], data['usage']['completion_tokens']
            model_used = model_id
        else:
            response = client.models.generate_content(
                model=MODEL_GEMINI, contents=prompt,
                config={"system_instruction": formatted_sys_prompt, "temperature": 0.2}
            )
            full_res = response.text.strip()
            in_t, out_t = response.usage_metadata.prompt_token_count, response.usage_metadata.candidates_token_count
            model_used = MODEL_GEMINI

        # --- THE BOUNCER ---
        words = re.findall(r'\w+', raw_txt.lower())
        stopwords = {'the', 'and', 'that', 'with', 'from', 'this', 'your', 'about', 'news', 'original'}
        anchors = [word for word, count in Counter(w for w in words if len(w) > 3 and w not in stopwords).most_common(5)]
        matches = [a for a in anchors if a in full_res.lower()]
        
        if len(matches) < 2:
            print(f"\n🛑 [Sox-Strict Hallucination Alert!]\n   Source Anchors: {', '.join(anchors)}\n   Found: {', '.join(matches) if matches else 'NONE'}")
            if input("⚠️ Save anyway? (y/n): ").lower() != 'y': return print("❌ Aborted.")

        # --- FILING ---
        slug = "untitled-article"
        if "SLUG:" in full_res:
            res_parts = full_res.split("SLUG:")
            final_article, slug_raw = res_parts[0].strip(), res_parts[1].strip().split('\n')[0]
            slug = slug_raw.replace('"', '').replace(':', '').replace(' ', '-').lower()
        else: final_article = full_res

        attr_footer = f"\n\n---\n\n**SOURCE:** [{meta['attr_name']}]({meta['attr_url']})" if meta.get("attr_name") else ""
        script_dir = os.path.dirname(os.path.abspath(__file__))
        out_dir = os.path.join(script_dir, "outputs")
        if not os.path.exists(out_dir): os.makedirs(out_dir)

        new_count = len(final_article.split())
        filename = os.path.join(out_dir, f"{tag}_{slug}.md")
        with open(filename, "w", encoding="utf-8") as f: 
            f.write(f"Original: {orig_count} words | Target: {meta.get('target_words', 'N/A')} words\n\n" + final_article + attr_footer + f"\n\nFinal Word Count: {new_count}")

        # --- 9-COLUMN AUDIT ---
        rates = {
            MODEL_GEMINI: {"in": 0.1/1e6, "out": 0.4/1e6}, 
            MODEL_GPT: {"in": 0.05/1e6, "out": 0.4/1e6}, 
            MODEL_TRINITY: {"in": 0, "out": 0}, 
            MODEL_LLAMA: {"in": 0, "out": 0},
            MODEL_DEEPSEEK: {"in": 0, "out": 0} # PRO-BONO work!
        }
        r = rates.get(model_used, {"in": 0, "out": 0})
        in_cost, out_cost = in_t * r["in"], out_t * r["out"]
        total_c = in_cost + out_cost

        log_file = os.path.join(out_dir, "gemini_cost_log.csv")
        file_exists = os.path.isfile(log_file)
        with open(log_file, "a", newline="") as f:
            writer = csv.writer(f)
            if not file_exists: writer.writerow(["timestamp", "Model", "mode", "input_tokens", "output_tokens", "total_tokens", "input_cost", "output_cost", "total_cost"])
            writer.writerow([datetime.now().strftime("%Y-%m-%d %H:%M"), model_used, tag.upper(), in_t, out_t, in_t+out_t, f"{in_cost:.6f}", f"{out_cost:.6f}", f"{total_c:.6f}"])

        print(f"\n{'═'*45}\n💰 AUDIT ({model_used})\n   In: {in_t} | Out: {out_t} | Cost: ${total_c:.6f}\n✅ Saved: {os.path.relpath(filename)}\n{'═'*45}")

    except Exception as e: print(f"❌ Error: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ELYU Herald Automation")
    parser.add_argument("--web", action="store_true")
    parser.add_argument("--print", action="store_true")
    parser.add_argument("--manual", action="store_true")
    parser.add_argument("driver_or_source", nargs="?", default=None)
    parser.add_argument("actual_source", nargs="?", default=None)

    args = parser.parse_args()
    drivers = ["gpt", "trinity", "llama", "gemini"]
    
    first_word = args.driver_or_source.lower() if args.driver_or_source else None
    if first_word in drivers:
        ai_choice, source_to_use = first_word, args.actual_source
    else:
        ai_choice, source_to_use = "gemini", args.driver_or_source

    mode_tag = "--print" if args.print else "--web"
    if args.manual:
        process(mode_tag, get_manual_input(), ai_choice)
    elif source_to_use:
        process(mode_tag, source_to_use, ai_choice)
    else: print("❌ Error: Provide URL/File or use --manual")