import csv
import os
import requests
import xml.etree.ElementTree as ET
from datetime import datetime

# --- CONFIGURATION ---
DEFAULT_PESO_RATE = 60.0  # Fallback if internet fails

def get_live_exchange_rate():
    """Fetches the latest USD to PHP rate from a public feed."""
    try:
        # Using a public RSS feed for currency (no API key required)
        url = "https://www.fx-exchange.com/usd/php.xml"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            root = ET.fromstring(response.content)
            # The description usually contains "1 USD = XX.XXXX PHP"
            description = root.find(".//item/description").text
            # Extract the number from the string
            rate_str = description.split('=')[1].split('PHP')[0].strip()
            return float(rate_str)
    except Exception as e:
        print(f"⚠️ Note: Could not fetch live rate ({e}). Using fallback: {DEFAULT_PESO_RATE}")
    return DEFAULT_PESO_RATE

def generate_weekly_report():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    output_dir = os.path.join(script_dir, "outputs")
    
    log_file = os.path.join(output_dir, "gemini_cost_log.csv")
    report_file = os.path.join(output_dir, "weekly_billing_summary.md")
    trend_file = os.path.join(output_dir, "weekly_trend_log.csv")
    
    if not os.path.exists(log_file):
        print(f"❌ No log file found at: {log_file}")
        return

    total_spend = 0.0
    total_articles = 0
    model_counts = {}
    mode_counts = {"WEB": 0, "PRINT": 0, "VISUAL": 0}
    
    # Fetch the live rate for "Bliss" mode
    current_rate = get_live_exchange_rate()
    
    try:
        with open(log_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                # 1. SKIP MANUAL NOTES/SUBTOTALS: 
                # If there's no timestamp OR it's clearly a summary row, skip it.
                ts = (row.get('timestamp') or "").strip()
                if not ts or ts.startswith(','):
                    continue

                # 2. Identify Model
                model = row.get('Model') or row.get('model') or 'Unknown'
                
                # 3. Identify Mode
                mode = (row.get('mode') or "UNKNOWN").upper()
                if mode in mode_counts:
                    mode_counts[mode] += 1
                else:
                    mode_counts["WEB"] += 1 # Default legacy

                # 4. THE CLEAN MATH: Strip symbols ($ , Php) that cause 'wobblies'
                cost_val = row.get('total_cost') or row.get('total_c') or "0.0"
                clean_cost = str(cost_val).replace('$', '').replace('Php', '').replace(',', '').strip()
                
                try:
                    cost = float(clean_cost)
                    total_spend += cost
                    total_articles += 1
                    model_counts[model] = model_counts.get(model, 0) + 1
                except ValueError:
                    continue 

        # --- Generate Markdown Report ---
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        total_php = total_spend * current_rate

        report = f"""# 📑 ELYU Herald: AI Billing Summary
Generated: {now_str}

## 💰 Financial Overview
- **Total Spend (USD):** ${total_spend:.6f}
- **Total Spend (PHP):** ₱{total_php:.2f} 
- **Current Rate Used:** 1 USD = ₱{current_rate:.2f}
- **Total Articles Processed:** {total_articles}
- **Average Cost Per Article:** ${(total_spend / max(total_articles, 1)):.6f}

## 📊 Content Breakdown
- **Web Editions:** {mode_counts['WEB']}
- **Print Editions:** {mode_counts['PRINT']}
- **Illustrations:** {mode_counts['VISUAL']}

## 🧠 Model Usage
"""
        for m, count in model_counts.items():
            report += f"- **{m}:** {count} requests\n"

        with open(report_file, "w") as f:
            f.write(report)

        # --- Update the Trend Ledger ---
        headers = ["date", "total_articles", "total_spend", "avg_per_article"]
        file_exists = os.path.isfile(trend_file)
        with open(trend_file, "a", newline="") as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(headers)
            writer.writerow([
                datetime.now().strftime("%Y-%m-%d"),
                total_articles,
                f"{total_spend:.6f}",
                f"{(total_spend / max(total_articles, 1)):.6f}"
            ])
        
        print("\n" + "═"*50)
        print(f"✅ AUDIT COMPLETE")
        print(f"💵 Total Spend: ${total_spend:.4f} (₱{total_php:.2f})")
        print(f"📈 Rate: 1 USD = ₱{current_rate:.2f}")
        print("═"*50 + "\n")

    except Exception as e:
        print(f"❌ Error during audit: {e}")

if __name__ == "__main__":
    generate_weekly_report()