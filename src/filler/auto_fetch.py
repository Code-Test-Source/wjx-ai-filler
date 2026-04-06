"""Auto fetch new surveys from activity page"""
from selenium.webdriver.common.by import By
import random
import time

def auto_fetch_surveys(driver, activity_url):
    """Fetch surveys from activity page - call this after each round"""
    print(f"\n[FETCH] Getting surveys from activity page...")
    try:
        driver.get(activity_url)
        time.sleep(random.uniform(2, 3))

        link_elems = driver.find_elements(By.CSS_SELECTOR, 'a[href*="/vm/"]')
        links = []
        for elem in link_elems:
            href = elem.get_attribute('href')
            if href and '/vm/' in href and href not in links:
                links.append(href)

        # Save
        with open("survey_links.txt", 'w', encoding='utf-8') as f:
            for link in links:
                f.write(link + '\n')

        print(f"[FETCH] Found {len(links)} surveys")
        return links
    except Exception as e:
        print(f"[FETCH] Error: {e}")
        return []