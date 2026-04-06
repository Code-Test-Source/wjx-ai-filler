"""
Chrome Driver utilities - automatic version detection and download
"""

import os
import sys
import subprocess
import json
import urllib.request
import zipfile
import shutil
import platform

# ChromeDriver download base URL
CHROMEDRIVER_BASE_URL = "https://storage.googleapis.com/chrome-for-testing-public"

def get_os_info():
    """Get operating system info"""
    system = platform.system().lower()  # 'windows', 'linux', 'darwin'
    arch = platform.machine().lower()

    # Map to ChromeDriver platform names
    if system == 'windows':
        return 'win64', 'windows'
    elif system == 'linux':
        if 'x86_64' in arch or 'amd64' in arch:
            return 'linux64', 'linux'
        elif 'aarch64' in arch or 'arm64' in arch:
            return 'linux64', 'linux'  # ChromeDriver uses linux64 for ARM64 too
    elif system == 'darwin':
        if 'arm64' in arch or 'aarch64' in arch:
            return 'mac-arm64', 'mac'
        else:
            return 'mac-x64', 'mac'

    return None, system

def get_chrome_version():
    """Get the installed Chrome version"""
    system, _ = get_os_info()

    if system == 'win64':
        chrome_paths = [
            "C:/Program Files/Google/Chrome/Application/chrome.exe",
            "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
        ]

        for path in chrome_paths:
            if os.path.exists(path):
                try:
                    # Use PowerShell to get version info
                    result = subprocess.run(
                        ['powershell', '-Command',
                         f"(Get-Item '{path}').VersionInfo.FileVersion"],
                        capture_output=True,
                        text=True,
                        timeout=10
                    )
                    if result.returncode == 0 and result.stdout.strip():
                        version = result.stdout.strip()
                        # Extract major version (e.g., "146" from "146.0.7680.178")
                        major_version = version.split('.')[0]
                        return major_version, version
                except Exception as e:
                    print(f"Error getting Chrome version from {path}: {e}")

    elif system in ['linux64', 'darwin']:
        # Try to get Chrome version from command line
        for cmd in ['google-chrome', 'chrome', 'chromium', '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome']:
            try:
                result = subprocess.run(
                    [cmd, '--version'],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                if result.returncode == 0:
                    version = result.stdout.strip().split()[-1]
                    major_version = version.split('.')[0]
                    return major_version, version
            except:
                continue

    return None, None

def get_latest_chromedriver_version(chrome_major_version, platform_key):
    """Get the latest ChromeDriver version for a given Chrome major version"""
    url = f"{CHROMEDRIVER_BASE_URL}/known-good-versions-with-downloads.json"

    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            data = json.loads(response.read().decode('utf-8'))

        # Find the matching version
        for version_info in data['versions']:
            version = version_info['version']
            if version.startswith(f"{chrome_major_version}."):
                # Check if it has downloads for the platform
                if 'downloads' in version_info and 'chromedriver' in version_info['downloads']:
                    for download in version_info['downloads']['chromedriver']:
                        if download['platform'] == platform_key:
                            return version, download['url']

        # If no exact match, try to get the latest for that major version
        print(f"No exact match for Chrome {chrome_major_version}, trying latest...")
        latest = data['versions'][-1]
        version = latest['version']
        if 'downloads' in latest and 'chromedriver' in latest['downloads']:
            for download in latest['downloads']['chromedriver']:
                if download['platform'] == platform_key:
                    return version, download['url']

    except Exception as e:
        print(f"Error getting ChromeDriver version: {e}")

    return None, None

def download_chromedriver(version, download_url, destination, platform_key):
    """Download and extract ChromeDriver"""
    print(f"Downloading ChromeDriver {version} for {platform_key}...")

    zip_path = os.path.join(destination, f"chromedriver_{platform_key}.zip")

    try:
        # Download
        urllib.request.urlretrieve(download_url, zip_path)
        print(f"Downloaded to {zip_path}")

        # Extract
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(destination)

        # Find and move chromedriver (different names per platform)
        driver_names = ['chromedriver.exe', 'chromedriver']
        for root, dirs, files in os.walk(destination):
            for driver_name in driver_names:
                if driver_name in files:
                    src = os.path.join(root, driver_name)
                    dst = os.path.join(destination, 'chromedriver.exe' if platform_key.startswith('win') else 'chromedriver')
                    if os.path.exists(dst):
                        os.remove(dst)
                    shutil.move(src, dst)
                    print(f"Extracted to {dst}")
                    break
            else:
                continue
            break

        # Cleanup zip
        os.remove(zip_path)
        return True

    except Exception as e:
        print(f"Error downloading ChromeDriver: {e}")
        return False

def get_or_download_chromedriver(download_dir=None):
    """
    Get ChromeDriver - download if not exists

    Args:
        download_dir: Directory to download ChromeDriver to

    Returns:
        Path to chromedriver.exe or None if failed
    """
    if download_dir is None:
        # Default to project root (src/browser -> src -> project_root)
        download_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    # Get OS info
    platform_key, os_name = get_os_info()
    print(f"Detected OS: {os_name} ({platform_key})")

    # Determine driver filename based on OS
    if platform_key.startswith('win'):
        driver_filename = 'chromedriver.exe'
    else:
        driver_filename = 'chromedriver'

    chromedriver_path = os.path.join(download_dir, driver_filename)

    # Check if already exists
    if os.path.exists(chromedriver_path):
        print(f"ChromeDriver already exists at: {chromedriver_path}")
        return chromedriver_path

    # Get Chrome version
    print("Detecting Chrome version...")
    major_version, full_version = get_chrome_version()

    if not major_version:
        print("Could not detect Chrome version!")
        return None

    print(f"Found Chrome version: {full_version} (major: {major_version})")

    # Get ChromeDriver version
    print("Finding matching ChromeDriver...")
    driver_version, download_url = get_latest_chromedriver_version(major_version, platform_key)

    if not driver_version:
        print("Could not find matching ChromeDriver!")
        return None

    print(f"Found ChromeDriver version: {driver_version}")

    # Download
    if download_chromedriver(driver_version, download_url, download_dir, platform_key):
        return chromedriver_path

    return None


if __name__ == "__main__":
    print("=" * 50)
    print("Chrome Driver Auto-Installer")
    print("=" * 50)

    chromedriver_path = get_or_download_chromedriver()

    if chromedriver_path:
        print(f"\nSuccess! ChromeDriver at: {chromedriver_path}")
    else:
        print("\nFailed to get ChromeDriver")