"""
WJX Survey Filler - Utility functions
"""

import os

SURVEY_LIST_FILE = "survey_links.txt"

def load_survey_links(filename=SURVEY_LIST_FILE):
    """Load survey URLs from file"""
    links = []
    if os.path.exists(filename):
        with open(filename, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    # Handle relative or absolute URLs
                    if line.startswith('/vm/'):
                        links.append('https://www.wjx.cn' + line)
                    elif line.startswith('http'):
                        links.append(line)
    return links

def save_survey_links(links, filename=SURVEY_LIST_FILE):
    """Save survey URLs to file"""
    with open(filename, 'w', encoding='utf-8') as f:
        f.write("# Survey URLs to fill\n")
        for link in links:
            f.write(link + '\n')
    print(f"✅ Saved {len(links)} survey links to {filename}")
