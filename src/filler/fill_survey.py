"""
WJX AI Survey Filler - AI-powered mode
Reads all questions at once, gets AI answers for all, then fills them
"""

import json
import time
import os
import sys
import random
import re
from datetime import datetime, date
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# Local imports
from .wjx_filler import load_survey_links
from .auto_fetch import auto_fetch_surveys
from ..ai.ai_answer import get_ai_answers_batch, get_fallback_answers
from ..utils.config import config

# Get settings from config
CHROMEDRIVER_PATH = config.CHROMEDRIVER_PATH
MIN_DELAY = config.MIN_DELAY
MAX_DELAY = config.MAX_DELAY
WJX_ACTIVITY_URL = config.WJX_ACTIVITY_URL  # Required - no default
COOKIES_FILE = config.COOKIES_FILE

# Daily limit settings
DAILY_LIMIT = 30
MIN_REWARD_POINTS = 15
DAILY_COUNT_FILE = "daily_count.json"


def get_daily_count():
    """Get today's survey fill count from file"""
    today = str(date.today())
    if os.path.exists(DAILY_COUNT_FILE):
        try:
            with open(DAILY_COUNT_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if data.get('date') == today:
                    return data.get('count', 0)
        except:
            pass
    return 0


def set_daily_count(count):
    """Set today's survey fill count"""
    today = str(date.today())
    with open(DAILY_COUNT_FILE, 'w', encoding='utf-8') as f:
        json.dump({'date': today, 'count': count}, f)


def increment_daily_count():
    """Increment today's survey fill count"""
    count = get_daily_count() + 1
    set_daily_count(count)
    return count


def check_website_daily_limit(driver):
    """Check if website shows daily limit reached message
    Returns: (limit_reached, message) tuple
    """
    try:
        page_source = driver.page_source

        # Check for daily limit message
        if '每个用户每天只能互填问卷30次' in page_source or '每天只能' in page_source:
            print("   [WARN] Website shows daily limit reached!")
            return True, "daily_limit_reached"

        # Check for other limit messages
        limit_patterns = [
            r'已填写(\d+)次',
            r'今日已填写(\d+)',
            r'还可以填写(\d+)次',
        ]
        for pattern in limit_patterns:
            match = re.search(pattern, page_source)
            if match:
                return False, match.group(0)

        return False, None
    except:
        return False, None


def verify_daily_count_from_website(driver):
    """Verify and update daily count from website if possible"""
    try:
        # Use the configured activity URL
        activity_url = WJX_ACTIVITY_URL
        if not activity_url:
            print("   [DEBUG] No activity URL configured, skipping website verification")
            return get_daily_count()

        current_url = driver.current_url
        driver.get(activity_url)
        time.sleep(2)

        page_source = driver.page_source

        # Check for count on the page
        # Look for patterns like "已填写X次" or "今日填写X份"
        patterns = [
            r'已填写\s*(\d+)\s*次',
            r'今日填写\s*(\d+)\s*份',
            r'已完成\s*(\d+)\s*份',
        ]

        count = None
        for pattern in patterns:
            match = re.search(pattern, page_source)
            if match:
                count = int(match.group(1))
                break

        # Check for remaining count
        if count is None:
            match = re.search(r'还可以填写\s*(\d+)\s*次', page_source)
            if match:
                remaining = int(match.group(1))
                count = DAILY_LIMIT - remaining

        # Go back to original URL
        driver.get(current_url)
        time.sleep(1)

        if count is not None:
            print(f"   [INFO] Website shows count: {count}")
            set_daily_count(count)
            return count

        return get_daily_count()

    except Exception as e:
        print(f"   [DEBUG] Could not verify count from website: {e}")
        return get_daily_count()


def check_survey_reward(driver):
    """Check if survey offers reward points >= MIN_REWARD_POINTS
    Returns: (has_reward, points) tuple
    """
    try:
        page_source = driver.page_source

        # Find "提供XX点数" pattern
        match = re.search(r'提供\s*(\d+)\s*点数', page_source)
        if match:
            points = int(match.group(1))
            return True, points

        # Also check for just "点数" with nearby number
        match = re.search(r'(\d+)\s*点数', page_source)
        if match:
            points = int(match.group(1))
            return True, points

        return False, 0
    except:
        return True, 0  # Default to allow if check fails

def random_delay():
    """Add random delay between actions to avoid detection"""
    delay = random.uniform(MIN_DELAY, MAX_DELAY)
    time.sleep(delay)

def setup_driver():
    """Setup Chrome driver"""
    options = Options()
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--start-maximized')
    options.add_experimental_option('excludeSwitches', ['enable-automation'])
    options.add_experimental_option('useAutomationExtension', False)
    options.add_argument('--disable-extensions')
    options.add_argument('--disable-popup-blocking')

    # Use local chromedriver
    print(f"   Using local chromedriver: {CHROMEDRIVER_PATH}")
    service = Service(executable_path=CHROMEDRIVER_PATH)
    driver = webdriver.Chrome(options=options, service=service)

    # Stealth
    driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
        'source': 'Object.defineProperty(navigator, "webdriver", {get: () => undefined})'
    })

    return driver

def load_cookies(driver, cookies_file=None):
    if cookies_file is None:
        cookies_file = COOKIES_FILE
    """Load cookies from file"""
    if not os.path.exists(cookies_file):
        return False

    driver.get("https://www.wjx.cn/")
    time.sleep(2)

    with open(cookies_file, 'r', encoding='utf-8') as f:
        cookies = json.load(f)

    for cookie in cookies:
        try:
            driver.add_cookie(cookie)
        except Exception as e:
            pass

    print("   [OK] Cookies loaded")
    return True

def extract_all_questions(driver):
    """Extract ALL questions from the survey page at once"""
    questions = []
    seen_elements = set()  # Track already processed elements

    # Primary method: Find all .field elements (WJX standard structure)
    try:
        fields = driver.find_elements(By.CSS_SELECTOR, '.field.ui-field-contain, .field[topic]')
        print(f"   [DEBUG] Found {len(fields)} .field elements")

        for elem in fields:
            try:
                # Skip if already processed
                elem_id = elem.get_attribute('id')
                if elem_id and elem_id in seen_elements:
                    continue
                if elem_id:
                    seen_elements.add(elem_id)

                # Get question type from attribute first
                elem_type = elem.get_attribute('type')

                # Get question title
                title = "Unknown"
                for sel in ['.topichtml', '.topic', '.topicnumber + div', '.field-label .topichtml']:
                    try:
                        title_elem = elem.find_element(By.CSS_SELECTOR, sel)
                        title = title_elem.text.strip()
                        if title:
                            break
                    except:
                        continue

                # Skip non-question elements
                skip_words = ['提交', '下一步', '按钮', '版权', '问卷星', '已完成', '感谢', '提交成功']
                if any(word in title for word in skip_words):
                    continue

                # Determine question type
                qtype = 'unknown'
                options = []

                # 1. Check by type attribute first (most reliable)
                if elem_type == '6':
                    qtype = 'scale_matrix'
                    for i in range(1, 6):
                        options.append(f'{i}星')
                elif elem_type == '5':
                    qtype = 'scale_single'
                    for i in range(1, 6):
                        options.append(f'{i}星')
                elif elem_type == '2':
                    qtype = 'text'

                # 2. If still unknown, check for UI elements
                if qtype == 'unknown':
                    # Check for matrix scale
                    if elem.find_elements(By.CSS_SELECTOR, '.scaletablewrap, .matrix-rating, tr[tp="d"]'):
                        qtype = 'scale_matrix'
                        for i in range(1, 6):
                            options.append(f'{i}星')

                if qtype == 'unknown':
                    # Check for single scale
                    if elem.find_elements(By.CSS_SELECTOR, '.scale-div, .scale-rating'):
                        qtype = 'scale_single'
                        for i in range(1, 6):
                            options.append(f'{i}星')

                if qtype == 'unknown':
                    # Check for multiple choice (checkbox)
                    checks = elem.find_elements(By.CSS_SELECTOR, '.ui-checkbox, input[type="checkbox"]')
                    if checks:
                        qtype = 'multiple_choice'
                        for cb in checks:
                            # Get option text
                            try:
                                label = cb.find_element(By.CSS_SELECTOR, '.label, label')
                                opt_text = label.text.strip()
                                if opt_text and len(opt_text) < 100:
                                    options.append(opt_text)
                            except:
                                pass

                if qtype == 'unknown':
                    # Check for single choice (radio)
                    radios = elem.find_elements(By.CSS_SELECTOR, '.ui-radio, input[type="radio"]')
                    if radios:
                        qtype = 'single_choice'
                        for label in elem.find_elements(By.CSS_SELECTOR, 'label, .label'):
                            opt_text = label.text.strip()
                            if opt_text and len(opt_text) < 100 and opt_text not in options:
                                options.append(opt_text)

                if qtype == 'unknown':
                    # Check for dropdown
                    if elem.find_elements(By.CSS_SELECTOR, 'select'):
                        qtype = 'dropdown'
                        try:
                            select = elem.find_element(By.CSS_SELECTOR, 'select')
                            for opt in select.find_elements(By.CSS_SELECTOR, 'option'):
                                opt_text = opt.text.strip()
                                if opt_text and opt_text not in ['请选择', '选择']:
                                    options.append(opt_text)
                        except:
                            pass

                if qtype == 'unknown':
                    # Check for text input
                    textareas = elem.find_elements(By.CSS_SELECTOR, 'textarea, .beginner_problem textarea')
                    text_inputs = elem.find_elements(By.CSS_SELECTOR, '.ui-input-text input, input[type="text"]')
                    if textareas or text_inputs:
                        qtype = 'text'

                # Only add if we found a valid question type
                if qtype != 'unknown':
                    questions.append({
                        'index': len(questions) + 1,
                        'title': title[:200],
                        'type': qtype,
                        'options': options[:15],
                        'element': elem,
                        'full_text': elem.text[:500] if elem.text else ''
                    })

            except Exception as e:
                continue

    except Exception as e:
        print(f"   [WARN] Primary extraction failed: {e}")

    # Fallback: try other selectors if primary found nothing
    if not questions:
        print("   [DEBUG] Primary found nothing, trying fallback selectors...")
        selectors = ['.question', '.questiondiv', '.topic']

        for selector in selectors:
            try:
                elems = driver.find_elements(By.CSS_SELECTOR, selector)
                for elem in elems:
                    try:
                        text = elem.text.strip()
                        if len(text) < 5:
                            continue
                        skip_words = ['提交', '下一步', '按钮', '版权', '问卷星', '已完成', '感谢', '提交成功']
                        if any(word in text for word in skip_words):
                            continue

                        # Try to find parent .field element
                        try:
                            parent = elem.find_element(By.XPATH, "./ancestor::div[contains(@class, 'field')]")
                            if parent.get_attribute('id') in seen_elements:
                                continue
                            elem = parent
                        except:
                            pass

                        # Simple type detection
                        qtype = 'unknown'
                        options = []

                        if elem.find_elements(By.CSS_SELECTOR, '.ui-checkbox, input[type="checkbox"]'):
                            qtype = 'multiple_choice'
                        elif elem.find_elements(By.CSS_SELECTOR, '.ui-radio, input[type="radio"]'):
                            qtype = 'single_choice'
                        elif elem.find_elements(By.CSS_SELECTOR, '.scaletablewrap, .matrix-rating, tr[tp="d"]'):
                            qtype = 'scale_matrix'
                            for i in range(1, 6):
                                options.append(f'{i}星')
                        elif elem.find_elements(By.CSS_SELECTOR, 'textarea, input[type="text"]'):
                            qtype = 'text'

                        if qtype != 'unknown':
                            title = text.split('\n')[0][:200]
                            questions.append({
                                'index': len(questions) + 1,
                                'title': title,
                                'type': qtype,
                                'options': options,
                                'element': elem,
                                'full_text': text[:500]
                            })
                    except:
                        continue
            except:
                continue

    return questions

def fill_answer(driver, element, question_type, answer):
    """Fill a single answer with delay to avoid detection"""
    try:
        random_delay()  # Add delay before each action

        # Scroll element into view first
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
        random_delay()

        if question_type == 'single_choice':
            # Answer could be a number (option index) or text
            # Filter out "其他" options to avoid needing to fill extra text
            radios = element.find_elements(By.CSS_SELECTOR, '.ui-radio')
            if not radios:
                radios = element.find_elements(By.CSS_SELECTOR, '.column1 .ui-radio')
            if not radios:
                radios = element.find_elements(By.CSS_SELECTOR, 'input[type="radio"]')

            # Find valid options (exclude "其他" / "Others")
            valid_indices = []
            for i, radio in enumerate(radios):
                radio_text = radio.text.strip().lower() if radio.text else ''
                # Check label text too
                try:
                    label = radio.find_element(By.CSS_SELECTOR, 'label, .label')
                    radio_text = label.text.strip().lower()
                except:
                    pass
                # Skip "其他" or "others" options
                if '其他' not in radio_text and 'others' not in radio_text and '其他' not in radio_text:
                    valid_indices.append(i)

            # Determine index to click
            if isinstance(answer, int):
                idx = answer - 1
            elif str(answer).isdigit():
                idx = int(answer) - 1
            else:
                idx = 0

            # Adjust index if it points to an "其他" option
            if valid_indices:
                if idx not in valid_indices:
                    idx = valid_indices[0]  # Use first valid option instead
                # Make sure idx is within valid range
                if idx >= len(radios):
                    idx = valid_indices[0]
            else:
                # No valid options found, use first anyway
                pass

            # Click the radio
            if radios and idx < len(radios):
                try:
                    radios[idx].click()
                except:
                    pass
                try:
                    inp = radios[idx].find_element(By.CSS_SELECTOR, 'input[type="radio"]')
                    driver.execute_script("arguments[0].checked = true; arguments[0].dispatchEvent(new Event('change'));", inp)
                except:
                    pass
                return True

            return False

        elif question_type == 'multiple_choice':
            # Answer could be "1,2,3" or list
            # LIMIT: Select at most 3 options to avoid unrealistic answers
            # Skip "其他" / "Others" options
            indices = []
            if isinstance(answer, list):
                indices = [int(x) - 1 for x in answer]
            elif isinstance(answer, str):
                if ',' in answer:
                    indices = [int(x.strip()) - 1 for x in answer.split(',')]
                else:
                    indices = [int(answer) - 1]

            # Limit to max 3 options
            if len(indices) > 3:
                indices = indices[:3]
                print(f"   [INFO] Limited multiple choice to 3 options")

            # WJX multiple choice - reference code clicks .ui-checkbox directly
            checkboxes = element.find_elements(By.CSS_SELECTOR, '.ui-checkbox')
            if not checkboxes:
                checkboxes = element.find_elements(By.CSS_SELECTOR, '.column1 .ui-checkbox')
            if not checkboxes:
                checkboxes = element.find_elements(By.CSS_SELECTOR, 'input[type="checkbox"]')

            if checkboxes:
                # Find valid options (exclude "其他" / "Others")
                valid_indices = []
                for i, cb in enumerate(checkboxes):
                    cb_text = cb.text.strip().lower() if cb.text else ''
                    try:
                        label = cb.find_element(By.CSS_SELECTOR, 'label, .label')
                        cb_text = label.text.strip().lower()
                    except:
                        pass
                    # Skip "其他" or "others" options
                    if '其他' not in cb_text and 'others' not in cb_text and '其他' not in cb_text:
                        valid_indices.append(i)

                # Filter indices to only valid ones
                if valid_indices:
                    indices = [idx for idx in indices if idx in valid_indices]
                    # If no valid indices remain, pick from valid ones
                    if not indices:
                        num_to_select = min(2, len(valid_indices))
                        indices = random.sample(valid_indices, num_to_select)

                for idx in indices:
                    if idx < len(checkboxes):
                        try:
                            checkboxes[idx].click()
                        except:
                            pass
                        try:
                            inp = checkboxes[idx].find_element(By.CSS_SELECTOR, 'input[type="checkbox"]')
                            driver.execute_script("arguments[0].checked = true; arguments[0].dispatchEvent(new Event('change'));", inp)
                        except:
                            pass
                return True

            return False

        elif question_type in ['text', 'textarea']:
            # Try textarea first (including .beginner_problem textarea)
            textareas = element.find_elements(By.CSS_SELECTOR, 'textarea, .beginner_problem textarea')
            if textareas:
                ta = textareas[0]
                try:
                    ta.click()
                    ta.clear()
                    ta.send_keys(str(answer))
                except:
                    # Fallback: use JavaScript
                    driver.execute_script("arguments[0].value = arguments[1]; arguments[0].dispatchEvent(new Event('input')); arguments[0].dispatchEvent(new Event('change'));", ta, str(answer))
                return True

            # Try WJX style: input inside .ui-input-text
            inputs = element.find_elements(By.CSS_SELECTOR, '.ui-input-text input')
            if not inputs:
                inputs = element.find_elements(By.CSS_SELECTOR, 'input[type="text"]')

            if inputs:
                try:
                    inputs[0].click()
                except:
                    pass
                try:
                    inputs[0].clear()
                    inputs[0].send_keys(str(answer))
                except:
                    # Fallback: use JavaScript to set value directly
                    driver.execute_script("arguments[0].value = arguments[1]; arguments[0].dispatchEvent(new Event('input')); arguments[0].dispatchEvent(new Event('change'));", inputs[0], str(answer))
                return True

            # Try generic input
            generic_inputs = element.find_elements(By.CSS_SELECTOR, 'input')
            for inp in generic_inputs:
                inp_type = inp.get_attribute('type')
                if inp_type in ['text', 'number', 'email', 'tel']:
                    try:
                        inp.click()
                    except:
                        pass
                    try:
                        inp.send_keys(str(answer))
                    except:
                        driver.execute_script(f"arguments[0].value = '{str(answer)}';", inp)
                    return True

            return False

        elif question_type == 'dropdown':
            from selenium.webdriver.support.ui import Select
            selects = element.find_elements(By.CSS_SELECTOR, 'select')
            if selects:
                try:
                    select = Select(selects[0])
                    # Try to select by index or value
                    if str(answer).isdigit():
                        select.select_by_index(int(answer))
                    else:
                        select.select_by_index(1)  # Default to first option
                    return True
                except:
                    pass
            return False

        elif question_type in ['scale_single', 'scale_matrix']:
            # Scale/rating questions - click on the scale value (1-5)
            try:
                # For single scale row
                if question_type == 'scale_single':
                    # Get the answer value (1-5)
                    val = int(answer) if str(answer).isdigit() else random.randint(3, 5)
                    if val < 1: val = 1
                    if val > 5: val = 5

                    # Find all scale buttons and click the one with matching value
                    scale_buttons = element.find_elements(By.CSS_SELECTOR, '.scale-rating a.rate-off, .scale-rating li a')
                    for btn in scale_buttons:
                        btn_val = btn.get_attribute('val') or btn.text.strip()
                        if btn_val == str(val):
                            driver.execute_script("arguments[0].click();", btn)
                            return True

                # For matrix scale (multiple rows) - each row gets a random rating
                elif question_type == 'scale_matrix':
                    rows = element.find_elements(By.CSS_SELECTOR, 'tr[tp="d"]')
                    print(f"   [INFO] Matrix scale: found {len(rows)} rows")

                    if not rows:
                        # Try alternative selector
                        rows = element.find_elements(By.CSS_SELECTOR, '.matrix-rating tbody tr')
                        rows = [r for r in rows if r.find_elements(By.CSS_SELECTOR, 'a[dval]')]
                        print(f"   [INFO] Alternative: found {len(rows)} rows")

                    clicked_count = 0
                    skipped_count = 0
                    for row_idx, row in enumerate(rows):
                        # Check if this row already has a selection
                        already_selected = row.find_elements(By.CSS_SELECTOR, 'a.rate-on, a.rate-onlarge')
                        if already_selected:
                            skipped_count += 1
                            continue  # Skip this row, already filled

                        # Random rating for each row (lean towards positive: 3-5)
                        val = random.randint(3, 5)

                        # Find ALL scale options in this row (both off and on states)
                        scale_options = row.find_elements(By.CSS_SELECTOR, 'a[dval]')
                        if not scale_options:
                            scale_options = row.find_elements(By.CSS_SELECTOR, 'a.rate-off, a.rate-offlarge, a.rate-on, a.rate-onlarge')

                        clicked = False
                        for opt in scale_options:
                            opt_val = opt.get_attribute('dval')
                            if opt_val == str(val):
                                # Scroll into view
                                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", opt)
                                # Click using multiple methods for reliability
                                try:
                                    opt.click()
                                except:
                                    pass
                                # JavaScript click
                                driver.execute_script("arguments[0].click();", opt)
                                # Trigger additional events
                                driver.execute_script("""
                                    var evt = new MouseEvent('click', {
                                        bubbles: true,
                                        cancelable: true,
                                        view: window
                                    });
                                    arguments[0].dispatchEvent(evt);
                                """, opt)
                                clicked = True
                                clicked_count += 1
                                print(f"      Row {row_idx + 1}: rated {val}")
                                time.sleep(0.3)  # Small delay between clicks
                                break

                        if not clicked and scale_options:
                            # Fallback: click the first available option
                            print(f"      Row {row_idx + 1}: fallback click")
                            driver.execute_script("arguments[0].click();", scale_options[-1])  # Click last option (usually highest)
                            clicked_count += 1

                    print(f"   [INFO] Matrix scale: clicked {clicked_count}, skipped {skipped_count}")
                    return clicked_count > 0 or skipped_count > 0

            except Exception as e:
                print(f"   [WARN] Scale question error: {e}")
                import traceback
                traceback.print_exc()

            return False

    except Exception as e:
        print(f"   [WARN] Error filling answer: {e}")

    return False

def rescan_unanswered_questions(driver):
    """Rescan page for unanswered required questions"""
    unanswered = []

    try:
        # Method 1: Look for error messages indicating unanswered questions
        error_elements = driver.find_elements(By.CSS_SELECTOR, '.errorMessage')
        for err in error_elements:
            err_text = err.text or ''
            # Check if error is visible or has error styling
            if err_text or 'display' not in (err.get_attribute('style') or ''):
                if '请' in err_text or '必填' in err_text or '选择' in err_text or err_text == '':
                    # Find the parent question div
                    try:
                        parent = err.find_element(By.XPATH, "./ancestor::div[contains(@class, 'field') or contains(@class, 'question')]")
                    except:
                        continue

                    if parent:
                        # Get question title
                        title = "Unknown"
                        for sel in ['.topichtml', '.topic', '.topicnumber + div', '.label']:
                            try:
                                title_elem = parent.find_element(By.CSS_SELECTOR, sel)
                                title = title_elem.text
                                break
                            except:
                                continue

                        # Detect ALL possible question types
                        possible_types = []

                        # Check for single choice (.ui-radio, input[radio])
                        if parent.find_elements(By.CSS_SELECTOR, '.ui-radio'):
                            possible_types.append('single_choice')
                        if parent.find_elements(By.CSS_SELECTOR, '.column1 .ui-radio, .column1 input[type="radio"]'):
                            possible_types.append('single_choice')
                        if parent.find_elements(By.CSS_SELECTOR, 'input[type="radio"]'):
                            possible_types.append('single_choice')

                        # Check for multiple choice (.ui-checkbox)
                        if parent.find_elements(By.CSS_SELECTOR, '.ui-checkbox'):
                            possible_types.append('multiple_choice')
                        if parent.find_elements(By.CSS_SELECTOR, 'input[type="checkbox"]'):
                            possible_types.append('multiple_choice')

                        # Check for text input
                        if parent.find_elements(By.CSS_SELECTOR, 'input[type="text"]:not([style*="display:none"])'):
                            possible_types.append('text')
                        if parent.find_elements(By.CSS_SELECTOR, 'textarea'):
                            possible_types.append('text')
                        if parent.find_elements(By.CSS_SELECTOR, '.beginner_problem textarea'):
                            possible_types.append('text')

                        # Check for dropdown
                        if parent.find_elements(By.CSS_SELECTOR, 'select'):
                            possible_types.append('dropdown')

                        # Check for scale/matrix questions
                        if parent.find_elements(By.CSS_SELECTOR, '.scaletablewrap, .matrix-rating'):
                            possible_types.append('scale_matrix')
                        if parent.find_elements(By.CSS_SELECTOR, '.scale-div, .scale-rating'):
                            possible_types.append('scale_single')

                        # Also check by type attribute
                        parent_type = parent.get_attribute('type')
                        if parent_type == '6':
                            possible_types.append('scale_matrix')
                        elif parent_type == '5':
                            possible_types.append('scale_single')
                        elif parent_type == '2':
                            possible_types.append('text')

                        # Add with all detected types (will try each)
                        if possible_types:
                            print(f"   [RESCAN] Found unanswered Q: {title[:40]}... types={possible_types}")
                            unanswered.append({
                                'index': len(unanswered) + 1,
                                'title': title[:100],
                                'types': possible_types,  # List of types to try
                                'element': parent
                            })

        # Method 2: Scan all required fields and check if matrix questions are answered
        all_fields = driver.find_elements(By.CSS_SELECTOR, '.field[req="1"], .field.ui-field-contain[req="1"]')
        for field in all_fields:
            field_type = field.get_attribute('type')

            # Check matrix scale questions (type='6')
            if field_type == '6':
                rows = field.find_elements(By.CSS_SELECTOR, 'tr[tp="d"]')
                unfilled_rows = []

                for row in rows:
                    # Check if any rating is selected in this row
                    selected = row.find_elements(By.CSS_SELECTOR, 'a.rate-on, a.rate-onlarge')
                    if not selected:
                        unfilled_rows.append(row)

                if unfilled_rows:
                    title = "Matrix question"
                    try:
                        title_elem = field.find_element(By.CSS_SELECTOR, '.topichtml')
                        title = title_elem.text[:100]
                    except:
                        pass

                    print(f"   [RESCAN] Matrix has {len(unfilled_rows)} unfilled rows: {title[:40]}...")
                    if not any(u['element'] == field for u in unanswered):
                        unanswered.append({
                            'index': len(unanswered) + 1,
                            'title': title,
                            'types': ['scale_matrix'],
                            'element': field
                        })
                    elif parent_type == '2':
                        possible_types.append('text')

                    # Add with all detected types (will try each)
                    if possible_types:
                        unanswered.append({
                            'index': len(unanswered) + 1,
                            'title': title[:100],
                            'types': possible_types,  # List of types to try
                            'element': parent
                        })

    except Exception as e:
        print(f"   [ERROR] Rescan failed: {e}")

    return unanswered


def submit_survey(driver):
    """Submit the survey or go to next page"""
    # First, check if there's a "下一页" (Next Page) button - PRIORITY!
    # Search across all clickable elements by text
    try:
        # Check buttons
        buttons = driver.find_elements(By.TAG_NAME, 'button')
        for btn in buttons:
            btn_text = btn.text.strip()
            if '下一页' in btn_text or '下一页' in btn_text or 'next' in btn_text.lower():
                print(f"   [INFO] Found '下一页' button: '{btn_text}', going to next page...")
                random_delay()
                try:
                    btn.click()
                except:
                    driver.execute_script("arguments[0].click();", btn)
                time.sleep(2)
                return "next_page"
    except:
        pass

    # Check input elements (type=button, type=submit)
    try:
        inputs = driver.find_elements(By.CSS_SELECTOR, 'input[type="button"], input[type="submit"]')
        for inp in inputs:
            inp_value = inp.get_attribute('value') or ''
            inp_text = inp.text.strip() if inp.text else ''
            if '下一页' in inp_value or '下一页' in inp_text or '下一页' in inp_value or 'next' in (inp_value + inp_text).lower():
                print(f"   [INFO] Found '下一页' input: '{inp_value}', going to next page...")
                random_delay()
                try:
                    inp.click()
                except:
                    driver.execute_script("arguments[0].click();", inp)
                time.sleep(2)
                return "next_page"
    except:
        pass

    # Check links (a tags)
    try:
        links = driver.find_elements(By.TAG_NAME, 'a')
        for link in links:
            link_text = link.text.strip()
            if '下一页' in link_text or '下一页' in link_text or 'next' in link_text.lower():
                print(f"   [INFO] Found '下一页' link: '{link_text}', going to next page...")
                random_delay()
                try:
                    link.click()
                except:
                    driver.execute_script("arguments[0].click();", link)
                time.sleep(2)
                return "next_page"
    except:
        pass

    # Check divs/spans with click handlers or submit-related classes
    try:
        divs = driver.find_elements(By.CSS_SELECTOR, 'div[onclick], div[class*="next"], div[class*="submit"], span[onclick], span[class*="next"]')
        for div in divs:
            div_text = div.text.strip()
            onclick = div.get_attribute('onclick') or ''
            if '下一页' in div_text or '下一页' in div_text or 'next' in div_text.lower() or '下一页' in onclick:
                print(f"   [INFO] Found '下一页' div/span: '{div_text}', going to next page...")
                random_delay()
                try:
                    div.click()
                except:
                    driver.execute_script("arguments[0].click();", div)
                time.sleep(2)
                return "next_page"
    except:
        pass

    # Check page source for "下一页" text and try to find the element
    try:
        page_source = driver.page_source
        if '下一页' in page_source:
            print("   [DEBUG] Page contains '下一页', searching for clickable element...")
            # Try common WJX next page selectors
            next_selectors = [
                '#nextbutton', '.nextbutton', '#btnNextPage', '.btnNextPage',
                '[id*="next"]', '[class*="next"]', '[onclick*="NextPage"]',
                '[onclick*="next"]', 'a[onclick*="下一页"]', 'div[onclick*="下一页"]'
            ]
            for selector in next_selectors:
                try:
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    for elem in elements:
                        if elem.is_displayed():
                            print(f"   [INFO] Found next page element via selector '{selector}'")
                            random_delay()
                            try:
                                elem.click()
                            except:
                                driver.execute_script("arguments[0].click();", elem)
                            time.sleep(2)
                            return "next_page"
                except:
                    continue
    except:
        pass

    # No "下一页" found, now look for "提交" (submit)
    selectors = [
        '.voteDiv',
        '#submit',
        'button[type="submit"]',
        'input[type="submit"]',
        'a.submit',
        '[class*="submit"]',
        '.nextbtn',
        '#ctlNext',
        '[id*="submit"]',
        '[onclick*="submit"]'
    ]

    for selector in selectors:
        try:
            btn = driver.find_element(By.CSS_SELECTOR, selector)
            random_delay()
            btn.click()
            time.sleep(2)
            return True
        except:
            continue

    # Try by text "提交"
    try:
        buttons = driver.find_elements(By.TAG_NAME, 'button')
        for btn in buttons:
            if '提交' in btn.text or '完成' in btn.text or '提交问卷' in btn.text:
                random_delay()
                btn.click()
                time.sleep(2)
                return True
    except:
        pass

    return False


def check_submission_success(driver):
    """Check if we're on the submission success page"""
    try:
        page_source = driver.page_source
        page_url = driver.current_url

        # Check for success indicators in page content
        success_indicators = [
            '提交成功', '感谢参与', '感谢您的参与', '问卷已提交',
            '已完成', '感谢您', '提交完毕', 'answer over'
        ]
        for indicator in success_indicators:
            if indicator in page_source:
                print(f"   [INFO] Found success indicator: '{indicator}'")
                return True

        # Check URL for success page indicators
        if 'joinok' in page_url or 'success' in page_url.lower() or 'complete' in page_url.lower():
            return True

        # Check for result message div
        try:
            result_divs = driver.find_elements(By.CSS_SELECTOR, '.result-message, .success-msg, .thank-msg, .end-msg')
            if result_divs:
                for div in result_divs:
                    if div.text and any(ind in div.text for ind in ['感谢', '成功', '完成']):
                        return True
        except:
            pass

    except Exception as e:
        print(f"   [DEBUG] Error checking success: {e}")

    return False


def fill_survey_with_ai(driver, survey_url):
    """
    Fill a single survey (handles multi-page surveys):
    1. Check daily limit and reward points
    2. Extract all questions
    3. Send all to AI at once
    4. Fill all answers
    5. Submit and verify success
    6. If not successful, rescan unanswered, get new AI answers, retry
    7. Repeat for each page
    """
    # Check daily limit
    daily_count = get_daily_count()
    if daily_count >= DAILY_LIMIT:
        print(f"\n[STOP] Daily limit reached ({daily_count}/{DAILY_LIMIT}). Try again tomorrow!")
        return "daily_limit"

    print(f"\n{'='*60}")
    print(f"Filling: {survey_url[:80]}...")
    print(f"{'='*60}")

    try:
        # Load the survey
        driver.get(survey_url)
        random_delay()
        random_delay()  # Extra delay for page load

        # Check if website shows daily limit reached
        limit_reached, msg = check_website_daily_limit(driver)
        if limit_reached:
            print(f"   [STOP] Website shows daily limit reached!")
            set_daily_count(DAILY_LIMIT)  # Update local count to max
            return "daily_limit"

        # Check reward points
        has_reward, points = check_survey_reward(driver)
        if not has_reward:
            print(f"   [SKIP] Survey has no reward points")
            return "no_reward"
        if points < MIN_REWARD_POINTS:
            print(f"   [SKIP] Survey reward ({points}点) < minimum ({MIN_REWARD_POINTS}点)")
            return "low_reward"
        print(f"   [INFO] Survey reward: {points}点数")

        page_num = 1
        max_pages = 20  # Safety limit
        max_submit_attempts = 3  # Max attempts to fix unanswered questions

        while page_num <= max_pages:
            print(f"\n{'='*20} Page {page_num} {'='*20}")

            # Extract all questions
            print(f"\n📋 Extracting questions from page {page_num}...")
            questions = extract_all_questions(driver)
            print(f"   [OK] Found {len(questions)} questions")

            if not questions:
                print("   [WARN] No questions found on this page")
                # Check if we're already on success page
                if check_submission_success(driver):
                    print("   [OK] Survey already submitted!")
                    new_count = increment_daily_count()
                    print(f"   [INFO] Today's count: {new_count}/{DAILY_LIMIT}")
                    return True
                if page_num == 1:
                    return False
            else:
                # Get AI answers for ALL questions at once
                print(f"\n🤖 Getting AI answers for all {len(questions)} questions...")
                ai_answers = get_ai_answers_batch(questions)

                if not ai_answers:
                    print("   [WARN] No AI answers received")
                    ai_answers = get_fallback_answers(questions)

                # Fill all answers
                print(f"\n✍️  Filling answers...")
                filled_count = 0
                for q in questions:
                    answer = ai_answers.get(str(q['index']), '1')
                    qtype = q.get('type', 'unknown')
                    success = fill_answer(driver, q['element'], qtype, answer)
                    if success:
                        filled_count += 1
                        print(f"   Q{q['index']}: ✓ ({qtype})")
                    else:
                        print(f"   Q{q['index']}: ✗ ({qtype}) - {answer}")
                print(f"\n   Filled {filled_count}/{len(questions)} questions")

            # Submit or go to next page - with retry logic
            submit_attempt = 0
            while submit_attempt < max_submit_attempts:
                submit_attempt += 1
                print(f"\n📤 Submit attempt {submit_attempt}/{max_submit_attempts}...")
                random_delay()

                result = submit_survey(driver)

                if result == "next_page":
                    print("   [INFO] Going to next page...")
                    random_delay()
                    random_delay()
                    page_num += 1
                    break  # Break inner loop, continue outer loop for next page

                # Check if submission was successful
                time.sleep(2)  # Wait for page to load
                if check_submission_success(driver):
                    print("   [OK] Survey submitted successfully!")
                    new_count = increment_daily_count()
                    print(f"   [INFO] Today's count: {new_count}/{DAILY_LIMIT}")
                    return True

                # Not on success page - rescan for unanswered questions
                print("   [WARN] Not on success page, rescanning for unanswered questions...")
                unanswered = rescan_unanswered_questions(driver)

                if not unanswered:
                    # No unanswered questions found - maybe already submitted?
                    if check_submission_success(driver):
                        print("   [OK] Survey submitted successfully!")
                        new_count = increment_daily_count()
                        print(f"   [INFO] Today's count: {new_count}/{DAILY_LIMIT}")
                        return True
                    print("   [WARN] No unanswered questions but not on success page")
                    # Try clicking submit again
                    continue

                print(f"   Found {len(unanswered)} unanswered questions")

                # Get NEW AI answers for unanswered questions
                print(f"   🤖 Getting AI answers for unanswered questions...")
                new_ai_answers = get_ai_answers_batch(unanswered)
                if not new_ai_answers:
                    new_ai_answers = get_fallback_answers(unanswered)

                # Fill unanswered questions
                print(f"   ✍️  Filling unanswered questions...")
                for q in unanswered:
                    answer = new_ai_answers.get(str(q['index']), '1')
                    print(f"      Fixing Q{q['index']}: {q['title'][:40]}...")

                    # Try each possible question type
                    if 'types' in q:
                        for qtype in q['types']:
                            success = fill_answer(driver, q['element'], qtype, answer)
                            if success:
                                print(f"         ✓ Fixed with {qtype}")
                                break
                    else:
                        fill_answer(driver, q['element'], q.get('type', 'text'), answer)
            else:
                # Exhausted submit attempts
                print("   [WARN] Max submit attempts reached")
                # Final check for success
                if check_submission_success(driver):
                    print("   [OK] Survey submitted successfully!")
                    new_count = increment_daily_count()
                    print(f"   [INFO] Today's count: {new_count}/{DAILY_LIMIT}")
                    return True

                # Save URL for manual completion
                with open("incomplete_surveys.txt", "a", encoding="utf-8") as f:
                    f.write(survey_url + "\n")
                print(f"   [WARN] Survey incomplete! URL saved to incomplete_surveys.txt")
                print(f"   URL: {survey_url}")
                return False

        # Reached max pages
        print(f"   [WARN] Reached max pages ({max_pages}), stopping")
        with open("incomplete_surveys.txt", "a", encoding="utf-8") as f:
            f.write(survey_url + "\n")
        return False

    except Exception as e:
        print(f"   [ERROR] {e}")
        import traceback
        traceback.print_exc()
        # Save URL on error too
        try:
            with open("incomplete_surveys.txt", "a", encoding="utf-8") as f:
                f.write(survey_url + "\n")
        except:
            pass
        return False

import io
def main():
    """Main function to run the AI survey filler"""
    print("\n" + "="*60)
    print("  WJX AI Survey Filler - AI Powered")
    print("="*60)

    # Check for cookies
    cookies_file = COOKIES_FILE
    if not os.path.exists(cookies_file):
        print("\n❌ cookies.json not found!")
        return

    # Load incomplete surveys to exclude
    incomplete_surveys = set()
    if os.path.exists("incomplete_surveys.txt"):
        with open("incomplete_surveys.txt", "r", encoding="utf-8") as f:
            for line in f:
                url = line.strip()
                if url:
                    incomplete_surveys.add(url)
        print(f"\n📋 Loaded {len(incomplete_surveys)} previously incomplete surveys to skip")

    # Setup browser
    print("\n🔧 Setting up browser...")
    driver = setup_driver()

    try:
        # Load cookies
        print("\n🔐 Loading cookies...")
        load_cookies(driver, cookies_file)

        # Get survey links
        print("\n📥 Getting survey links...")
        links = load_survey_links()

        if not links and WJX_ACTIVITY_URL:
            # Try to get from activity page
            print(f"   Accessing activity page...")
            driver.get(WJX_ACTIVITY_URL)
            random_delay()

            # Save page source
            with open("page_source.html", "w", encoding="utf-8") as f:
                f.write(driver.page_source)

            # Extract links
            link_elems = driver.find_elements(By.CSS_SELECTOR, 'a[href*="/vm/"]')
            links = []
            for elem in link_elems:
                href = elem.get_attribute('href')
                if href and '/vm/' in href and href not in links:
                    links.append(href)

            if links:
                with open("survey_links.txt", 'w', encoding='utf-8') as f:
                    for link in links:
                        f.write(link + '\n')

        # Filter out incomplete surveys
        original_count = len(links)
        links = [link for link in links if link not in incomplete_surveys]
        if len(links) < original_count:
            print(f"   [INFO] Excluded {original_count - len(links)} previously incomplete surveys")

        print(f"   [OK] Found {len(links)} surveys to fill")

        if not links:
            print("\n❌ No surveys found")
            return

        # Verify daily count from website
        print(f"\n📊 Verifying daily count from website...")
        website_count = verify_daily_count_from_website(driver)
        print(f"   Current count: {website_count}/{DAILY_LIMIT}")

        if website_count >= DAILY_LIMIT:
            print(f"\n[STOP] Daily limit already reached on website!")
            return

        # Ask user to start
        print(f"\nFound {len(links)} surveys to fill")
        print(f"Daily limit: {DAILY_LIMIT} | Min reward: {MIN_REWARD_POINTS}点")
        print(f"Today's count: {get_daily_count()}/{DAILY_LIMIT}")
        print("Starting AI-powered survey filling...")
        print("(Press Ctrl+C to stop)\n")

        # Fill surveys
        success_count = 0
        skipped_no_reward = 0
        skipped_low_reward = 0

        for i, link in enumerate(links):
            # Check daily limit before each survey
            if get_daily_count() >= DAILY_LIMIT:
                print(f"\n[STOP] Daily limit reached ({DAILY_LIMIT}). Stopping.")
                break

            print(f"\n{'#'*60}")
            print(f"Survey {i+1}/{len(links)}")

            result = fill_survey_with_ai(driver, link)
            if result == True:
                success_count += 1
            elif result == "no_reward":
                skipped_no_reward += 1
            elif result == "low_reward":
                skipped_low_reward += 1
            elif result == "daily_limit":
                break

            # Delay between surveys
            random_delay()
            random_delay()

        print(f"\n{'='*60}")
        print(f"Completed! Filled {success_count} surveys")
        print(f"Skipped (no reward): {skipped_no_reward}")
        print(f"Skipped (low reward <{MIN_REWARD_POINTS}点): {skipped_low_reward}")
        print(f"Today's total: {get_daily_count()}/{DAILY_LIMIT}")

        # Auto fetch new surveys after completing current batch
        if WJX_ACTIVITY_URL and get_daily_count() < DAILY_LIMIT:
            print("\n[FETCH] Getting new surveys from activity page...")
            new_links = auto_fetch_surveys(driver, WJX_ACTIVITY_URL)
            # Filter out incomplete surveys
            if new_links:
                new_links = [link for link in new_links if link not in incomplete_surveys]
            if new_links:
                print(f"[FETCH] Found {len(new_links)} new surveys to continue...")
                # Continue filling new surveys in a loop
                while new_links and get_daily_count() < DAILY_LIMIT:
                    for link in new_links:
                        if get_daily_count() >= DAILY_LIMIT:
                            print(f"\n[STOP] Daily limit reached ({DAILY_LIMIT}).")
                            break
                        print(f"\n--- New Survey: {new_links.index(link)+1}/{len(new_links)} ---")
                        result = fill_survey_with_ai(driver, link)
                        if result == True:
                            success_count += 1
                        elif result == "no_reward":
                            skipped_no_reward += 1
                        elif result == "low_reward":
                            skipped_low_reward += 1
                        elif result == "daily_limit":
                            break
                        random_delay()
                        random_delay()
                    # Fetch again and filter
                    new_links = auto_fetch_surveys(driver, WJX_ACTIVITY_URL)
                    if new_links:
                        new_links = [link for link in new_links if link not in incomplete_surveys]

        print(f"\n{'='*60}")
        print(f"TOTAL COMPLETED: {success_count} surveys!")
        print(f"Skipped (no reward): {skipped_no_reward}")
        print(f"Skipped (low reward <{MIN_REWARD_POINTS}点): {skipped_low_reward}")
        print(f"Today's total: {get_daily_count()}/{DAILY_LIMIT}")
        print(f"{'='*60}")

    finally:
        input("\nPress Enter to close browser...")
        driver.quit()

if __name__ == "__main__":
    main()