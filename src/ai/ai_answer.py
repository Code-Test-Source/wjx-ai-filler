"""
AI Answer Generator module
Uses configured AI API (DeepSeek or similar)
"""

import json
import sys
from pathlib import Path

# Add src to path for imports
src_path = Path(__file__).parent
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

import requests

from config import config

# System prompt for the AI
SYSTEM_PROMPT = """你是一个友好的问卷填写助手。你会根据问题的语义给出合理、自然的回答。
注意：
- 对于选择题，选择最符合常理的选项
- 对于人口统计学问题（如性别、年级），选择最常见的选项
- 对于满意度问题，选择中等偏上的选项
- 回答要自然、符合实际情况
- 只返回答案，不需要解释"""


def call_ai_api(prompt):
    """Call AI API to get response - uses config for settings"""
    if not config.API_URL or not config.API_KEY:
        raise ValueError("API URL and Key not configured. Run 'python -m src.cli setup'")

    headers = {
        "Authorization": f"Bearer {config.API_KEY}",
        "Content-Type": "application/json"
    }

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt}
    ]

    payload = {
        "model": config.API_MODEL,
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 1000
    }

    try:
        response = requests.post(
            f"{config.API_URL}/chat/completions",
            headers=headers,
            json=payload,
            timeout=60
        )

        if response.status_code == 200:
            result = response.json()
            return result['choices'][0]['message']['content']
        else:
            print(f"   [ERROR] API error: {response.status_code}")
            return None

    except Exception as e:
        print(f"   [ERROR] API call failed: {e}")
        return None


def generate_answer(question_title, options, question_type):
    """
    Generate an AI answer for a survey question
    """
    prompt = f"""请回答以下问卷问题。根据问题的语义给出合理、自然的回答。

问题：{question_title}
问题类型：{question_type}
"""

    if options:
        prompt += f"选项：\n"
        for i, opt in enumerate(options):
            prompt += f"{i+1}. {opt}\n"

    # Add specific instructions
    if question_type == 'multiple_choice':
        prompt += "\n注意：这是一个多选题，请选择2-3个最合适的选项（如果题目要求选n个，则选n个）。"
        prompt += "\n回答格式：用逗号分隔选项编号，如 \"1,2,3\" 或 \"2,3\""
    else:
        prompt += "\n重要：不要总是选第一个选项！请根据题目语义选择最合理的选项，可以是任意选项编号。"

    prompt += "\n请给出一个合理、自然的答案。"

    answer = call_ai_api(prompt)

    if answer is None:
        return get_fallback_answer(question_type, options)

    return parse_ai_answer(answer, question_type, options)


def parse_ai_answer(ai_response, question_type, options):
    """Parse AI response to get usable answer"""
    ai_response = ai_response.strip()

    if question_type in ['text', 'textarea']:
        return ai_response[:200]

    if question_type == 'multiple_choice':
        # For multiple choice, try to find multiple numbers like "1,2,3" or "1 2 3"
        import re
        # Find all numbers in the response
        numbers = re.findall(r'\d+', ai_response)
        if numbers:
            indices = [int(n) for n in numbers if 1 <= int(n) <= len(options)]
            if indices:
                return indices  # Return list of indices

        # Try to match option texts
        matched = []
        ai_lower = ai_response.lower()
        for i, opt in enumerate(options):
            if opt.lower() in ai_lower:
                matched.append(i + 1)
        if matched:
            return matched

        return [1]  # Default to first option as list

    # Single choice
    if options:
        import re
        numbers = re.findall(r'\d+', ai_response)
        if numbers:
            idx = int(numbers[0])
            if 1 <= idx <= len(options):
                return idx

        ai_lower = ai_response.lower()
        for i, opt in enumerate(options):
            if opt.lower() in ai_lower:
                return i + 1

        return 1

    return 1


def get_fallback_answer(question_type, options):
    """Get fallback answer when API fails"""
    if question_type in ['text', 'textarea']:
        return "同意"

    if options:
        return 1

    return 1


def get_ai_answers_batch(questions):
    """Send all questions to AI at once and get answers"""
    prompt = "请回答以下问卷的所有问题。\n\n"
    prompt += "请以JSON格式返回答案：\n"
    prompt += '{"1": "答案1", "2": "答案2", ...}\n\n'
    prompt += "重要规则：\n"
    prompt += "1. 单选题：不要总是选第一个选项！请根据题目语义选择最合理的选项，可以是1、2、3、4等任意选项\n"
    prompt += "2. 多选题：请选择2-3个选项（如果题目要求选n个，则选n个）。不要总是选前几个！\n"
    prompt += "3. 如果题目有明确要求（如\"请选择2项\"），请严格遵守\n"
    prompt += "4. 填空题：返回简短的答案文字\n\n"
    prompt += "问题列表：\n\n"

    for q in questions:
        prompt += f"问题{q['index']}：{q['title']}\n"
        prompt += f"类型：{q['type']}\n"

        if q['options']:
            prompt += "选项：\n"
            for i, opt in enumerate(q['options']):
                prompt += f"  {i+1}. {opt}\n"
        prompt += "\n"

    prompt += "\n只返回JSON格式答案。不要只选第一个选项！"

    response = call_ai_api(prompt)

    if response:
        import re
        json_match = re.search(r'\{[^{}]*\}', response, re.DOTALL)
        if json_match:
            try:
                answers = json.loads(json_match.group())
                return answers
            except:
                pass

    return get_fallback_answers(questions)


def get_fallback_answers(questions):
    """Generate fallback answers"""
    answers = {}
    for q in questions:
        if q['type'] in ['text', 'textarea']:
            answers[str(q['index'])] = "同意"
        elif q['options']:
            answers[str(q['index'])] = "1"
        else:
            answers[str(q['index'])] = "1"
    return answers