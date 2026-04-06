"""
WJX AI Survey Filler - Main survey filling logic
"""

import time
import os
import random
import re

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options

from .wjx_filler import load_survey_links
from .auto_fetch import auto_fetch_surveys
from ..ai.ai_answer import get_ai_answers_batch, get_fallback_answers
from ..utils.config import config

# Settings
CHROMEDRIVER_PATH = config.CHROMEDRIVER_PATH
MIN_DELAY = config.MIN_DELAY
MAX_DELAY = config.MAX_DELAY
WJX_ACTIVITY_URL = config.WJX_ACTIVITY_URL
COOKIES_FILE = config.COOKIES_FILE

MIN_REWARD_POINTS = 20


# ============================================================================
# Browser Setup
# ============================================================================

def random_delay():
    """Random delay to avoid detection."""
    time.sleep(random.uniform(MIN_DELAY, MAX_DELAY))


def setup_driver():
    """Setup Chrome driver with stealth options."""
    options = Options()
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--start-maximized')
    options.add_experimental_option('excludeSwitches', ['enable-automation'])
    options.add_experimental_option('useAutomationExtension', False)

    print(f"   Using chromedriver: {CHROMEDRIVER_PATH}")
    service = Service(executable_path=CHROMEDRIVER_PATH)
    driver = webdriver.Chrome(options=options, service=service)

    # Hide webdriver property
    driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
        'source': 'Object.defineProperty(navigator, "webdriver", {get: () => undefined})'
    })

    return driver


def load_cookies(driver, cookies_file=None):
    """Load cookies from file into driver."""
    import json
    cookies_file = cookies_file or COOKIES_FILE
    if not os.path.exists(cookies_file):
        return False

    driver.get("https://www.wjx.cn/")
    time.sleep(2)

    with open(cookies_file, 'r', encoding='utf-8') as f:
        cookies = json.load(f)

    for cookie in cookies:
        try:
            driver.add_cookie(cookie)
        except:
            pass

    print("   [OK] Cookies loaded")
    return True


# ============================================================================
# Survey Validation
# ============================================================================

def check_survey_reward(driver):
    """Check survey reward points. Returns (has_reward, points)."""
    try:
        page = driver.page_source

        # Pattern on survey page: "填写此问卷可以获得XX个点数"
        patterns = [
            r'填写此问卷可以获得.*?(\d+)\s*个?\s*点数',  # Main pattern
            r'可以获得.*?(\d+)\s*个?\s*点数',
            r'提供\s*(\d+)\s*点数',
            r'奖励\s*(\d+)\s*点',
        ]

        for pattern in patterns:
            match = re.search(pattern, page)
            if match:
                points = int(match.group(1))
                print(f"   [INFO] Found reward: {points}点")
                return True, points

        # No reward info found
        return True, 0
    except:
        return True, 0


# ============================================================================
# Question Extraction
# ============================================================================

def get_question_title(element):
    """Extract question title from element."""
    for selector in ['.topichtml', '.topic', '.topicnumber + div', '.field-label .topichtml']:
        try:
            return element.find_element(By.CSS_SELECTOR, selector).text.strip()
        except:
            continue
    return "Unknown"


def detect_question_type(element, elem_type):
    """Detect question type from element attributes and UI."""
    options = []

    # Check type attribute first (most reliable)
    if elem_type == '6':
        return 'scale_matrix', [f'{i}星' for i in range(1, 6)]
    if elem_type == '5':
        return 'scale_single', [f'{i}星' for i in range(1, 6)]
    if elem_type == '4':
        # Ranking/sorting question - uses checkboxes like multiple choice
        # But we need to get options
        pass  # Fall through to checkbox detection
    if elem_type == '3':
        # Multiple choice
        pass  # Fall through to checkbox detection
    if elem_type == '2':
        return 'text', []

    # Check for matrix scale
    if element.find_elements(By.CSS_SELECTOR, '.scaletablewrap, .matrix-rating, tr[tp="d"]'):
        return 'scale_matrix', [f'{i}星' for i in range(1, 6)]

    # Check for single scale
    if element.find_elements(By.CSS_SELECTOR, '.scale-div, .scale-rating'):
        return 'scale_single', [f'{i}星' for i in range(1, 6)]

    # Check for multiple choice or ranking (both use checkboxes)
    checkboxes = element.find_elements(By.CSS_SELECTOR, '.ui-checkbox, input[type="checkbox"]')
    if checkboxes:
        for cb in checkboxes:
            try:
                label = cb.find_element(By.CSS_SELECTOR, '.label, label')
                text = label.text.strip()
                if text and len(text) < 100:
                    options.append(text)
            except:
                pass
        # type='4' is ranking, type='3' is multiple choice
        if elem_type == '4':
            return 'ranking', options
        return 'multiple_choice', options

    # Check for single choice
    radios = element.find_elements(By.CSS_SELECTOR, '.ui-radio, input[type="radio"]')
    if radios:
        for label in element.find_elements(By.CSS_SELECTOR, 'label, .label'):
            text = label.text.strip()
            if text and len(text) < 100 and text not in options:
                options.append(text)
        return 'single_choice', options

    # Check for dropdown
    if element.find_elements(By.CSS_SELECTOR, 'select'):
        try:
            select = element.find_element(By.CSS_SELECTOR, 'select')
            for opt in select.find_elements(By.CSS_SELECTOR, 'option'):
                text = opt.text.strip()
                if text and text not in ['请选择', '选择']:
                    options.append(text)
        except:
            pass
        return 'dropdown', options

    # Check for text input
    if element.find_elements(By.CSS_SELECTOR, 'textarea, .beginner_problem textarea, input[type="text"]'):
        return 'text', []

    return 'unknown', []


def extract_all_questions(driver):
    """Extract all questions from survey page."""
    questions = []
    seen_ids = set()
    skip_words = ['提交', '下一步', '按钮', '版权', '问卷星', '已完成', '感谢', '提交成功']

    # Find all .field elements
    fields = driver.find_elements(By.CSS_SELECTOR, '.field.ui-field-contain, .field[topic]')
    print(f"   [DEBUG] Found {len(fields)} .field elements")

    for elem in fields:
        try:
            elem_id = elem.get_attribute('id')
            if elem_id and elem_id in seen_ids:
                continue
            if elem_id:
                seen_ids.add(elem_id)

            title = get_question_title(elem)
            if any(word in title for word in skip_words):
                continue

            elem_type = elem.get_attribute('type')
            qtype, options = detect_question_type(elem, elem_type)

            if qtype != 'unknown':
                questions.append({
                    'index': len(questions) + 1,
                    'title': title[:200],
                    'type': qtype,
                    'options': options[:15],
                    'element': elem
                })
        except:
            continue

    return questions


# ============================================================================
# Answer Filling
# ============================================================================

def find_valid_indices(elements):
    """Find indices of options that don't contain '其他' or 'others'."""
    valid = []
    for i, elem in enumerate(elements):
        text = elem.text.lower() if elem.text else ''
        try:
            label = elem.find_element(By.CSS_SELECTOR, 'label, .label')
            text = label.text.lower()
        except:
            pass
        if '其他' not in text and 'others' not in text:
            valid.append(i)
    return valid


def click_element(driver, element):
    """Click element with fallback methods."""
    try:
        element.click()
    except:
        pass
    try:
        driver.execute_script("arguments[0].click();", element)
    except:
        pass


def fill_single_choice(driver, element, answer):
    """Fill single choice question."""
    radios = (element.find_elements(By.CSS_SELECTOR, '.ui-radio') or
              element.find_elements(By.CSS_SELECTOR, 'input[type="radio"]'))

    if not radios:
        return False

    valid = find_valid_indices(radios)
    idx = int(answer) - 1 if str(answer).isdigit() else 0

    if valid and idx not in valid:
        idx = valid[0]
    if idx >= len(radios):
        idx = 0

    click_element(driver, radios[idx])

    # Also set input directly
    try:
        inp = radios[idx].find_element(By.CSS_SELECTOR, 'input[type="radio"]')
        driver.execute_script("arguments[0].checked = true;", inp)
    except:
        pass

    return True


def fill_multiple_choice(driver, element, answer):
    """Fill multiple choice question."""
    checkboxes = (element.find_elements(By.CSS_SELECTOR, '.ui-checkbox') or
                  element.find_elements(By.CSS_SELECTOR, 'input[type="checkbox"]'))

    if not checkboxes:
        return False

    # Parse answer to indices
    if isinstance(answer, list):
        indices = [int(x) - 1 for x in answer]
    elif isinstance(answer, str) and ',' in answer:
        indices = [int(x.strip()) - 1 for x in answer.split(',')]
    else:
        indices = [int(answer) - 1] if str(answer).isdigit() else [0]

    # Limit to 3 options
    indices = indices[:3]

    # Filter to valid indices
    valid = find_valid_indices(checkboxes)
    if valid:
        indices = [i for i in indices if i in valid] or random.sample(valid, min(2, len(valid)))

    for idx in indices:
        if idx < len(checkboxes):
            # Try visual click first (for UI feedback)
            try:
                checkboxes[idx].click()
                time.sleep(0.1)
            except:
                pass
            # Also use JavaScript as backup
            try:
                driver.execute_script("arguments[0].click();", checkboxes[idx])
            except:
                pass
            # Set input directly
            try:
                inp = checkboxes[idx].find_element(By.CSS_SELECTOR, 'input[type="checkbox"]')
                driver.execute_script("arguments[0].checked = true; arguments[0].dispatchEvent(new Event('change'));", inp)
            except:
                pass

    return True


def fill_ranking(driver, element, answer):
    """Fill ranking/sorting question. Similar to multiple choice but order matters."""
    checkboxes = element.find_elements(By.CSS_SELECTOR, '.ui-checkbox')

    if not checkboxes:
        return False

    # Parse answer to indices (same as multiple choice)
    if isinstance(answer, list):
        indices = [int(x) - 1 for x in answer]
    elif isinstance(answer, str) and ',' in answer:
        indices = [int(x.strip()) - 1 for x in answer.split(',')]
    else:
        indices = [int(answer) - 1] if str(answer).isdigit() else [0]

    # For ranking, select 2-4 options in order
    if len(indices) < 2:
        indices = list(range(min(4, len(checkboxes))))

    # Filter to valid indices (skip "其他")
    valid = find_valid_indices(checkboxes)
    if valid:
        indices = [i for i in indices if i in valid]
        if len(indices) < 2:
            indices = valid[:min(4, len(valid))]

    # Click each checkbox in order
    for idx in indices[:4]:  # Max 4 items for ranking
        if idx < len(checkboxes):
            try:
                checkboxes[idx].click()
                time.sleep(0.15)  # Small delay between clicks
            except:
                pass
            try:
                driver.execute_script("arguments[0].click();", checkboxes[idx])
            except:
                pass
            try:
                inp = checkboxes[idx].find_element(By.CSS_SELECTOR, 'input[type="checkbox"]')
                driver.execute_script("arguments[0].checked = true; arguments[0].dispatchEvent(new Event('change'));", inp)
            except:
                pass

    return True


def fill_text(driver, element, answer):
    """Fill text question."""
    # Try textarea first
    textareas = element.find_elements(By.CSS_SELECTOR, 'textarea, .beginner_problem textarea')
    if textareas:
        try:
            textareas[0].send_keys(str(answer))
        except:
            driver.execute_script("arguments[0].value = arguments[1];", textareas[0], str(answer))
        return True

    # Try text input
    inputs = element.find_elements(By.CSS_SELECTOR, '.ui-input-text input, input[type="text"]')
    if inputs:
        try:
            inputs[0].send_keys(str(answer))
        except:
            driver.execute_script("arguments[0].value = arguments[1];", inputs[0], str(answer))
        return True

    return False


def fill_dropdown(element, answer):
    """Fill dropdown question."""
    from selenium.webdriver.support.ui import Select

    selects = element.find_elements(By.CSS_SELECTOR, 'select')
    if not selects:
        return False

    try:
        select = Select(selects[0])
        select.select_by_index(int(answer) if str(answer).isdigit() else 1)
        return True
    except:
        return False


def fill_scale_matrix(driver, element):
    """Fill matrix scale question - each row gets rating 3-5."""
    rows = element.find_elements(By.CSS_SELECTOR, 'tr[tp="d"]')
    if not rows:
        rows = element.find_elements(By.CSS_SELECTOR, '.matrix-rating tbody tr')
        rows = [r for r in rows if r.find_elements(By.CSS_SELECTOR, 'a[dval]')]

    clicked = 0
    for row in rows:
        # Skip if already selected
        if row.find_elements(By.CSS_SELECTOR, 'a.rate-on, a.rate-onlarge'):
            continue

        val = random.randint(3, 5)
        options = row.find_elements(By.CSS_SELECTOR, 'a[dval]')
        if not options:
            options = row.find_elements(By.CSS_SELECTOR, 'a.rate-off, a.rate-offlarge')

        for opt in options:
            if opt.get_attribute('dval') == str(val):
                driver.execute_script("arguments[0].click();", opt)
                clicked += 1
                time.sleep(0.2)
                break
        else:
            if options:
                driver.execute_script("arguments[0].click();", options[-1])
                clicked += 1

    return clicked > 0


def fill_answer(driver, element, question_type, answer):
    """Fill a single answer based on question type."""
    random_delay()
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
    random_delay()

    if question_type == 'single_choice':
        return fill_single_choice(driver, element, answer)
    elif question_type == 'multiple_choice':
        return fill_multiple_choice(driver, element, answer)
    elif question_type == 'ranking':
        return fill_ranking(driver, element, answer)
    elif question_type in ['text', 'textarea']:
        return fill_text(driver, element, answer)
    elif question_type == 'dropdown':
        return fill_dropdown(element, answer)
    elif question_type == 'scale_single':
        val = int(answer) if str(answer).isdigit() else random.randint(3, 5)
        for btn in element.find_elements(By.CSS_SELECTOR, '.scale-rating a'):
            if (btn.get_attribute('val') or btn.text.strip()) == str(val):
                driver.execute_script("arguments[0].click();", btn)
                return True
        return False
    elif question_type == 'scale_matrix':
        return fill_scale_matrix(driver, element)

    return False


# ============================================================================
# Submission
# ============================================================================

def click_start_button(driver):
    """Click '开始作答' button if exists. Returns True if clicked."""
    from selenium.webdriver.common.action_chains import ActionChains

    # Check if start button exists
    try:
        slide_chunk = driver.find_element(By.CSS_SELECTOR, '#slideChunk')
    except:
        slide_chunk = None

    if slide_chunk:
        print("   [INFO] Found '开始作答' slide button")

        # Method 1: Hide the cover div directly
        driver.execute_script("""
            var cover = document.getElementById('divFengMian');
            if (cover) cover.style.display = 'none';
        """)

        time.sleep(1)

        # Check if questions appeared
        questions = driver.find_elements(By.CSS_SELECTOR, '.field')
        if questions:
            print("   [INFO] Started survey (hided cover)")
            return True

        # Method 2: Simulate slide drag
        try:
            actions = ActionChains(driver)
            actions.click_and_hold(slide_chunk).move_by_offset(300, 0).release().perform()
            time.sleep(1)
        except:
            pass

        # Method 3: Trigger touch events
        driver.execute_script("""
            var elem = document.getElementById('slideChunk');
            if (elem) {
                var startX = elem.getBoundingClientRect().left;
                var evt = new TouchEvent('touchstart', {bubbles: true, touches: [{clientX: startX}]});
                elem.dispatchEvent(evt);
                evt = new TouchEvent('touchmove', {bubbles: true, touches: [{clientX: startX + 300}]});
                elem.dispatchEvent(evt);
                evt = new TouchEvent('touchend', {bubbles: true});
                elem.dispatchEvent(evt);
            }
        """)

        time.sleep(1)
        print("   [INFO] Attempted slide to start")
        return True

    # Check buttons and inputs
    for tag in ['button', 'input', 'a']:
        for elem in driver.find_elements(By.TAG_NAME, tag):
            text = elem.text or elem.get_attribute('value') or ''
            if '开始作答' in text or '开始答题' in text:
                click_element(driver, elem)
                time.sleep(2)
                print("   [INFO] Clicked '开始作答'")
                return True

    return False


def find_next_page_button(driver):
    """Find and click '下一页' button if exists."""
    # Check buttons and inputs
    for tag, attr in [('button', 'text'), ('input', 'value')]:
        for elem in driver.find_elements(By.TAG_NAME, tag):
            text = elem.text or elem.get_attribute(attr or 'value') or ''
            if '下一页' in text or 'next' in text.lower():
                click_element(driver, elem)
                time.sleep(2)
                return True

    # Check links
    for elem in driver.find_elements(By.TAG_NAME, 'a'):
        if '下一页' in (elem.text or ''):
            click_element(driver, elem)
            time.sleep(2)
            return True

    return False


def has_next_page(driver):
    """Check if '下一页' button exists (without clicking)."""
    for tag, attr in [('button', 'text'), ('input', 'value')]:
        for elem in driver.find_elements(By.TAG_NAME, tag):
            text = elem.text or elem.get_attribute(attr or 'value') or ''
            if '下一页' in text or 'next' in text.lower():
                return True
    for elem in driver.find_elements(By.TAG_NAME, 'a'):
        if '下一页' in (elem.text or ''):
            return True
    return False


def find_submit_button(driver):
    """Find and click submit button."""
    selectors = [
        ('.voteDiv', 'voteDiv'),
        ('#submit', 'submit'),
        ('button[type="submit"]', 'submit button'),
        ('input[type="submit"]', 'submit input'),
        ('#ctlNext', 'ctlNext'),
        ('.nextbtn', 'nextbtn'),
    ]

    for selector, name in selectors:
        try:
            btn = driver.find_element(By.CSS_SELECTOR, selector)
            # Try normal click
            try:
                btn.click()
                print(f"   [INFO] Clicked submit ({name})")
            except:
                pass
            # Also try JavaScript click
            try:
                driver.execute_script("arguments[0].click();", btn)
            except:
                pass
            time.sleep(1)
            return True
        except:
            continue

    # Try by text "提交"
    for btn in driver.find_elements(By.TAG_NAME, 'button'):
        if '提交' in btn.text:
            try:
                btn.click()
                print(f"   [INFO] Clicked submit button by text")
            except:
                pass
            try:
                driver.execute_script("arguments[0].click();", btn)
            except:
                pass
            time.sleep(1)
            return True

    # Try input with value "提交"
    for inp in driver.find_elements(By.CSS_SELECTOR, 'input[type="button"], input[type="submit"]'):
        val = inp.get_attribute('value') or ''
        if '提交' in val:
            try:
                inp.click()
                print(f"   [INFO] Clicked submit input by value")
            except:
                pass
            try:
                driver.execute_script("arguments[0].click();", inp)
            except:
                pass
            time.sleep(1)
            return True

    print("   [WARN] No submit button found")
    return False


def check_submission_success(driver):
    """Check if survey was submitted successfully."""
    try:
        page = driver.page_source
        url = driver.current_url

        # Check for success indicators in page content
        indicators = [
            '提交成功', '感谢参与', '感谢您的参与', '问卷已提交',
            '已完成', '感谢您', '提交完毕', 'answer over',
            '答题结束', '问卷结束', '答题完成'
        ]
        for ind in indicators:
            if ind in page:
                print(f"   [DEBUG] Found success indicator: '{ind}'")
                return True

        # Check URL for success page
        if 'joinok' in url or 'success' in url.lower() or 'complete' in url.lower():
            print(f"   [DEBUG] Success URL detected")
            return True

        # Check if we're back to activity page (sometimes happens after submit)
        if 'joinbacklist' in url or 'promote' in url:
            print(f"   [DEBUG] Redirected to activity page - likely submitted")
            return True

        return False
    except Exception as e:
        print(f"   [DEBUG] Error checking success: {e}")
        return False


# ============================================================================
# Rescan Unanswered
# ============================================================================

def rescan_unanswered_questions(driver):
    """Rescan page for unanswered required questions."""
    unanswered = []

    # Check for error messages
    for err in driver.find_elements(By.CSS_SELECTOR, '.errorMessage'):
        try:
            parent = err.find_element(By.XPATH, "./ancestor::div[contains(@class, 'field')]")
        except:
            continue

        # Detect question types
        types = []
        parent_type = parent.get_attribute('type')

        # Check for ranking (type='4') first
        if parent_type == '4':
            types.append('ranking')
        elif parent.find_elements(By.CSS_SELECTOR, '.ui-radio, input[type="radio"]'):
            types.append('single_choice')
        elif parent.find_elements(By.CSS_SELECTOR, '.ui-checkbox, input[type="checkbox"]'):
            types.append('multiple_choice')

        if parent.find_elements(By.CSS_SELECTOR, 'textarea, input[type="text"]'):
            types.append('text')
        if parent.find_elements(By.CSS_SELECTOR, 'select'):
            types.append('dropdown')
        if parent.find_elements(By.CSS_SELECTOR, '.scaletablewrap, .matrix-rating'):
            types.append('scale_matrix')

        if types:
            title = get_question_title(parent)
            unanswered.append({
                'index': len(unanswered) + 1,
                'title': title[:100],
                'types': types,
                'element': parent
            })

    # Check unfilled matrix rows
    for field in driver.find_elements(By.CSS_SELECTOR, '.field[req="1"]'):
        if field.get_attribute('type') == '6':
            rows = field.find_elements(By.CSS_SELECTOR, 'tr[tp="d"]')
            unfilled = [r for r in rows if not r.find_elements(By.CSS_SELECTOR, 'a.rate-on')]
            if unfilled and not any(u['element'] == field for u in unanswered):
                unanswered.append({
                    'index': len(unanswered) + 1,
                    'title': get_question_title(field),
                    'types': ['scale_matrix'],
                    'element': field
                })

    return unanswered


# ============================================================================
# Main Fill Logic
# ============================================================================

def fill_survey_with_ai(driver, survey_url, max_time=180):
    """Fill a single survey (handles multi-page).
    Args:
        driver: Selenium driver
        survey_url: URL of the survey
        max_time: Maximum time in seconds (default 3 minutes)
    Returns True, 'low_reward', or False.
    """
    start_time = time.time()
    print(f"\n{'='*60}\nFilling: {survey_url[:60]}...\n{'='*60}")

    def check_timeout():
        """Check if we've exceeded max time"""
        if time.time() - start_time > max_time:
            print(f"   [WARN] Timeout after {max_time}s, refreshing...")
            return True
        return False

    def refresh_and_retry():
        """Refresh page and retry once"""
        print("   [INFO] Refreshing page...")
        driver.refresh()
        time.sleep(3)
        click_start_button(driver)
        random_delay()

    try:
        driver.get(survey_url)
        random_delay()

        # Click "开始作答" if present
        click_start_button(driver)
        random_delay()

        # Check reward
        has_reward, points = check_survey_reward(driver)
        if has_reward and points > 0 and points < MIN_REWARD_POINTS:
            print(f"   [SKIP] Reward ({points}点) < minimum ({MIN_REWARD_POINTS}点)")
            return "low_reward"
        if points > 0:
            print(f"   [INFO] Reward: {points}点")

        # Process each page
        page_num = 1
        refreshed = False  # Track if we've refreshed once

        while page_num <= 20:
            if check_timeout():
                if not refreshed:
                    refresh_and_retry()
                    refreshed = True
                    continue
                else:
                    return False

            print(f"\n{'='*20} Page {page_num} {'='*20}")

            # Click "开始作答" if present on this page
            click_start_button(driver)

            questions = extract_all_questions(driver)
            print(f"   Found {len(questions)} questions")

            if not questions:
                # Check for "开始作答" button first
                if click_start_button(driver):
                    random_delay()
                    questions = extract_all_questions(driver)
                    if questions:
                        print(f"   Found {len(questions)} questions after clicking start")

                # If still no questions, wait and retry once more
                if not questions:
                    time.sleep(2)
                    click_start_button(driver)
                    random_delay()
                    questions = extract_all_questions(driver)

                if not questions:
                    # Try refresh if haven't yet
                    if not refreshed and page_num == 1:
                        refresh_and_retry()
                        refreshed = True
                        continue

                    if check_submission_success(driver):
                        print("   [OK] Submitted!")
                        return True
                    if page_num == 1:
                        print("   [WARN] No questions found - skipping")
                        return False
                    continue
            else:
                # Get and fill answers
                answers = get_ai_answers_batch(questions) or get_fallback_answers(questions)

                for q in questions:
                    if check_timeout():
                        if not refreshed:
                            refresh_and_retry()
                            refreshed = True
                            break
                        else:
                            return False
                    ans = answers.get(str(q['index']), '1')
                    success = fill_answer(driver, q['element'], q.get('type'), ans)
                    print(f"   Q{q['index']}: {'✓' if success else '✗'} ({q.get('type')})")
                else:
                    # All questions filled normally
                    pass

            # Submit or go to next page
            random_delay()

            if check_timeout():
                if not refreshed:
                    refresh_and_retry()
                    refreshed = True
                    continue
                else:
                    return False

            # First check if there's a "下一页" button
            if has_next_page(driver):
                if find_next_page_button(driver):
                    print("   [INFO] Going to next page...")
                    random_delay()
                    page_num += 1
                    continue

            # No "下一页" - try to submit
            find_submit_button(driver)
            time.sleep(3)

            # Check if submitted successfully
            if check_submission_success(driver):
                print("   [OK] Submitted!")
                return True

            # Not successful - try one quick fix
            unanswered = rescan_unanswered_questions(driver)
            if unanswered:
                print(f"   [WARN] Found {len(unanswered)} unanswered, fixing...")
                new_answers = get_fallback_answers(unanswered)
                for q in unanswered:
                    ans = new_answers.get(str(q['index']), '1')
                    for qtype in q.get('types', [q.get('type', 'text')]):
                        if fill_answer(driver, q['element'], qtype, ans):
                            break
                find_submit_button(driver)
                time.sleep(2)

            if check_submission_success(driver):
                print("   [OK] Submitted!")
                return True

            # Failed - move to next survey
            print("   [WARN] Submission failed, moving to next survey")
            return False

        return False

    except Exception as e:
        print(f"   [ERROR] {e}")
        return False


def fetch_surveys_from_activity(driver):
    """Fetch survey links from activity page."""
    if not WJX_ACTIVITY_URL:
        return []

    print("\n📥 Fetching surveys from activity page...")
    driver.get(WJX_ACTIVITY_URL)
    random_delay()
    links = list({e.get_attribute('href') for e in driver.find_elements(By.CSS_SELECTOR, 'a[href*="/vm/"]') if e.get_attribute('href')})
    print(f"   Found {len(links)} surveys")
    return links


def main():
    """Main entry point."""
    print("\n" + "="*60)
    print("  WJX AI Survey Filler")
    print("="*60)

    if not os.path.exists(COOKIES_FILE):
        print("\n❌ cookies.json not found!")
        return

    driver = setup_driver()

    try:
        load_cookies(driver)

        # Fetch surveys from activity page
        links = fetch_surveys_from_activity(driver)

        # Fallback to saved links if no activity URL
        if not links:
            links = load_survey_links()

        if not links:
            print("\n❌ No surveys found")
            return

        # Fill surveys
        success = 0
        skipped_low_reward = 0
        filled_count = 0
        consecutive_failures = 0  # Track consecutive failures
        max_consecutive_failures = 3  # Re-fetch after 3 consecutive failures

        while True:
            for i, link in enumerate(links):
                print(f"\n{'#'*60}\nSurvey {i+1}/{len(links)}")
                result = fill_survey_with_ai(driver, link)

                if result == True:
                    success += 1
                    filled_count += 1
                    consecutive_failures = 0  # Reset on success
                elif result == "low_reward":
                    skipped_low_reward += 1
                    consecutive_failures = 0
                else:
                    consecutive_failures += 1
                    print(f"   [WARN] Consecutive failures: {consecutive_failures}")

                random_delay()

                # Re-fetch every 20 items
                if filled_count > 0 and filled_count % 20 == 0:
                    print(f"\n📥 Re-fetching surveys (filled {filled_count})...")
                    new_links = fetch_surveys_from_activity(driver)
                    if new_links:
                        links = new_links
                        break  # Restart with new links

                # Re-fetch if too many consecutive failures
                if consecutive_failures >= max_consecutive_failures:
                    print(f"\n🔄 Too many failures, re-fetching from activity page...")
                    new_links = fetch_surveys_from_activity(driver)
                    if new_links:
                        links = new_links
                        consecutive_failures = 0
                        break  # Restart with new links
            else:
                # Loop completed normally - all surveys done
                break

        print(f"\n{'='*60}")
        print(f"Completed: {success} surveys")
        if skipped_low_reward:
            print(f"Skipped (reward < {MIN_REWARD_POINTS}点): {skipped_low_reward}")
        print(f"{'='*60}")

    finally:
        input("\nPress Enter to close...")
        driver.quit()


if __name__ == "__main__":
    main()
