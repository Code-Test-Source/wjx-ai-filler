"""
CLI module for WJX AI Survey Filler
Provides interactive commands for setup and running
"""

import os
import sys
import json
import io
from pathlib import Path

# Fix encoding for Chinese Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from .utils.config import config

def setup():
    """Interactive setup wizard"""
    print("\n" + "="*60)
    print("  WJX AI Survey Filler - Setup Wizard")
    print("="*60)

    print("\n--- Step 1: API Configuration ---")
    print("(OpenAI-compatible API - works with DeepSeek, OpenAI, etc.)")
    api_url = input("API URL (e.g., https://api.openai.com/v1): ").strip()
    api_key = input("API Key: ").strip()
    model = input("Model (default: gpt-4): ").strip() or "gpt-4"

    # Save to .env file
    env_file = Path(config.PROJECT_ROOT) / '.env'
    with open(env_file, 'w', encoding='utf-8') as f:
        f.write(f"API_URL={api_url}\n")
        f.write(f"API_KEY={api_key}\n")
        f.write(f"API_MODEL={model}\n")
    print(f"   Saved to {env_file}")

    print("\n--- Step 2: WJX Activity URL (Required) ---")
    while True:
        activity_url = input("WJX Activity URL（https://www.wjx.cn/wjx/promote/joinbacklist.aspx?activity=activity_id）: ").strip()
        if activity_url:
            with open(env_file, 'a', encoding='utf-8') as f:
                f.write(f"WJX_ACTIVITY_URL={activity_url}\n")
            break
        print("   [ERROR] Activity URL is required!")

    print("\n--- Step 3: Delay Settings ---")
    min_delay = input("Min delay between actions (default: 1.5): ").strip() or "1.5"
    max_delay = input("Max delay between actions (default: 3.0): ").strip() or "3.0"

    with open(env_file, 'a', encoding='utf-8') as f:
        f.write(f"MIN_DELAY={min_delay}\n")
        f.write(f"MAX_DELAY={max_delay}\n")

    print("\n--- Step 4: Cookies ---")
    cookies_file = Path(config.PROJECT_ROOT) / 'cookies.json'
    if cookies_file.exists():
        print(f"   Cookies file found: {cookies_file}")
    else:
        print(f"   No cookies file found.")
        print(f"   Run 'python -m src.cli import-cookies' to create one.")

    print("\n" + "="*60)
    print("Setup complete! Run 'python -m src.cli run' to start.")
    print("="*60 + "\n")


def import_cookies():
    """Import cookies from various formats"""
    from datetime import datetime

    print("\n" + "="*60)
    print("  Cookie Import Wizard")
    print("="*60)

    print("\nSelect cookie format:")
    print("  1. Cookie-Editor JSON export")
    print("  2. Raw cookie string (name=value; name2=value2...)")
    print("  3. Manual entry")

    choice = input("Choice (1/2/3): ").strip()

    cookies_file = Path(config.PROJECT_ROOT) / 'cookies.json'

    def update_lastaccdate(cookies):
        """Update lastaccdate to current time"""
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for cookie in cookies:
            if cookie.get('name') == 'lastaccdate':
                cookie['value'] = current_time
                cookie['domain'] = '.wjx.cn'
                cookie['path'] = '/'
                print(f"   Updated lastaccdate to: {current_time}")
                return cookies
        # Add lastaccdate if not exists
        cookies.append({
            "name": "lastaccdate",
            "value": current_time,
            "domain": ".wjx.cn",
            "path": "/"
        })
        print(f"   Added lastaccdate: {current_time}")
        return cookies

    if choice == '1':
        # JSON format
        print("\nPaste JSON content (Ctrl+D to finish):")
        content = sys.stdin.read()
        try:
            cookies = json.loads(content)
            cookies = update_lastaccdate(cookies)
            with open(cookies_file, 'w', encoding='utf-8') as f:
                json.dump(cookies, f, indent=2, ensure_ascii=False)
            print(f"   Saved {len(cookies)} cookies to {cookies_file}")
        except json.JSONDecodeError as e:
            print(f"   [ERROR] Invalid JSON: {e}")

    elif choice == '2':
        # Raw cookie string
        cookie_str = input("\nPaste cookie string: ").strip()
        cookies = []

        # Parse cookie string
        for part in cookie_str.split(';'):
            part = part.strip()
            if '=' in part:
                name, value = part.split('=', 1)
                cookies.append({
                    "name": name.strip(),
                    "value": value.strip(),
                    "domain": ".wjx.cn",
                    "path": "/"
                })

        if cookies:
            cookies = update_lastaccdate(cookies)
            with open(cookies_file, 'w', encoding='utf-8') as f:
                json.dump(cookies, f, indent=2, ensure_ascii=False)
            print(f"   Saved {len(cookies)} cookies to {cookies_file}")
        else:
            print("   [ERROR] No valid cookies found")

    elif choice == '3':
        # Manual entry
        print("\nEnter cookies one by one (name, value)")
        print("Press Enter twice to finish:")

        cookies = []
        while True:
            name = input("Cookie name (or Enter to finish): ").strip()
            if not name:
                break
            value = input("Cookie value: ").strip()
            domain = input("Domain (default: .wjx.cn): ").strip() or ".wjx.cn"
            path = input("Path (default: /): ").strip() or "/"

            cookies.append({
                "name": name,
                "value": value,
                "domain": domain,
                "path": path
            })

        if cookies:
            cookies = update_lastaccdate(cookies)
            with open(cookies_file, 'w', encoding='utf-8') as f:
                json.dump(cookies, f, indent=2, ensure_ascii=False)
            print(f"   Saved {len(cookies)} cookies")

    print("\n" + "="*60 + "\n")


def download_driver():
    """Download ChromeDriver"""
    from .browser.chrome_driver import get_or_download_chromedriver

    print("\n" + "="*60)
    print("  ChromeDriver Download")
    print("="*60)

    driver_path = get_or_download_chromedriver(str(config.PROJECT_ROOT))

    if driver_path:
        print(f"\nSuccess! ChromeDriver saved to: {driver_path}")
    else:
        print("\nFailed to download ChromeDriver")

    print("\n" + "="*60 + "\n")


def check_config():
    """Check configuration status"""
    print("\n" + "="*60)
    print("  Configuration Status")
    print("="*60)
    config.print_status()
    print("="*60 + "\n")


def run_filler():
    """Run the survey filler"""
    # Reload config to get latest values from .env
    from .utils.config import Config, config
    config = Config()  # Create fresh instance to reload .env

    if not config.API_KEY:
        print("\n[ERROR] API not configured. Run 'python -m src.cli setup' first.")
        return

    if not Path(config.COOKIES_FILE).exists():
        print(f"\n[ERROR] Cookies file not found: {config.COOKIES_FILE}")
        print("Run 'python -m src.cli import-cookies' first.")
        return

    if not config.WJX_ACTIVITY_URL:
        print("\n[ERROR] WJX Activity URL not configured. Run 'python -m src.cli setup' first.")
        return

    # Import and run the filler
    from .filler.fill_survey import main as fill_main
    fill_main()


def interactive_mode():
    """Interactive mode with menu"""
    while True:
        print("\n" + "="*60)
        print("  WJX AI Survey Filler - Interactive Menu")
        print("="*60)
        print("  1. Setup/Configure")
        print("  2. Import Cookies")
        print("  3. Check Configuration")
        print("  4. Download ChromeDriver")
        print("  5. Run Survey Filler")
        print("  0. Exit")
        print("="*60)

        choice = input("\nSelect: ").strip()

        if choice == '1':
            setup()
        elif choice == '2':
            import_cookies()
        elif choice == '3':
            check_config()
        elif choice == '4':
            download_driver()
        elif choice == '5':
            run_filler()
        elif choice == '0':
            print("\nGoodbye!")
            break
        else:
            print("\nInvalid choice. Please try again.")


def main():
    """Main CLI entry point"""
    if len(sys.argv) < 2:
        interactive_mode()
        return

    command = sys.argv[1]

    if command == 'setup':
        setup()
    elif command == 'import-cookies':
        import_cookies()
    elif command == 'download-driver':
        download_driver()
    elif command == 'check':
        check_config()
    elif command == 'run':
        run_filler()
    elif command == 'interactive':
        interactive_mode()
    else:
        print(f"Unknown command: {command}")
        print("\nAvailable commands:")
        print("  setup             - Interactive setup wizard")
        print("  import-cookies    - Import cookies from browser")
        print("  download-driver   - Download ChromeDriver")
        print("  check             - Check configuration status")
        print("  run               - Run the survey filler")
        print("  interactive       - Interactive menu mode")


if __name__ == "__main__":
    main()