"""
AI Answer Generator module
Uses configured AI API (OpenAI, DeepSeek, etc.)
"""

import json
import re
import random

import requests

from ..utils.config import config


def call_ai_api(prompt):
    """Call AI API to get response"""
    if not config.API_URL or not config.API_KEY:
        raise ValueError("API not configured. Run 'uv run python -m src.cli setup'")

    headers = {
        "Authorization": f"Bearer {config.API_KEY}",
        "Content-Type": "application/json"
    }

    messages = [
        {"role": "system", "content": "你是一个问卷填写助手，根据问题语义给出合理自然的回答。"},
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
            return response.json()['choices'][0]['message']['content']
        else:
            print(f"   [ERROR] API error: {response.status_code}")
            return None
    except Exception as e:
        print(f"   [ERROR] API call failed: {e}")
        return None


def get_ai_answers_batch(questions):
    """
    Send all questions to AI at once and get answers.
    Returns dict: {"1": "answer1", "2": "answer2", ...}
    """
    prompt = "请回答以下问卷的所有问题。\n\n"
    prompt += "请以JSON格式返回答案：{\"1\": \"答案1\", \"2\": \"答案2\", ...}\n\n"
    prompt += "规则：\n"
    prompt += "1. 单选题：返回选项编号（1/2/3...），不要选含\"其他\"的选项\n"
    prompt += "2. 多选题：返回编号用逗号分隔（如\"1,2\"），最多3个选项，不要选含\"其他\"的选项\n"
    prompt += "3. 填空题：返回简短具体的答案（20-50字）\n\n"
    prompt += "问题列表：\n\n"

    for q in questions:
        qtype = q.get('type') or (q.get('types', ['unknown'])[0] if q.get('types') else 'unknown')
        prompt += f"问题{q['index']}：{q['title']}\n类型：{qtype}\n"
        if q.get('options'):
            prompt += "选项：\n"
            for i, opt in enumerate(q['options']):
                prompt += f"  {i+1}. {opt}\n"
        prompt += "\n"

    prompt += "只返回JSON格式答案。"

    print(f"\n📡 Sending {len(questions)} questions to AI...")
    response = call_ai_api(prompt)

    if response:
        json_match = re.search(r'\{[^{}]*\}', response, re.DOTALL)
        if json_match:
            try:
                answers = json.loads(json_match.group())
                print(f"   [OK] Received {len(answers)} answers from AI")
                return answers
            except:
                print(f"   [WARN] Could not parse JSON from AI response")

    print(f"   [WARN] Using fallback answers")
    return get_fallback_answers(questions)


def get_fallback_answers(questions):
    """Generate contextual fallback answers when AI fails"""
    answers = {}
    for q in questions:
        qtype = q.get('type') or (q.get('types', ['unknown'])[0] if q.get('types') else 'unknown')
        idx = str(q['index'])

        if qtype in ['text', 'textarea']:
            # Contextual answers based on question keywords
            title = q.get('title', '')
            if '印象' in title or '深刻' in title:
                answers[idx] = "整体体验很好，服务态度热情周到，印象深刻。"
            elif '建议' in title:
                answers[idx] = "建议增加更多互动体验项目，提升参与感。"
            elif '意见' in title or '看法' in title:
                answers[idx] = "整体体验不错，希望能继续保持并改进。"
            elif '满意' in title or '评价' in title:
                answers[idx] = "总体满意，体验良好。"
            elif '问题' in title or '不足' in title:
                answers[idx] = "暂无明显问题，体验过程顺利。"
            elif '期望' in title or '希望' in title:
                answers[idx] = "希望能提供更多优质服务。"
            elif '原因' in title or '为什么' in title:
                answers[idx] = "因为整体体验良好，符合预期。"
            else:
                answers[idx] = "体验很好，总体满意。"

        elif qtype == 'multiple_choice' and q.get('options'):
            # Select 1-2 random options, skip "其他"
            valid = [i+1 for i, opt in enumerate(q['options'])
                     if '其他' not in opt.lower() and 'others' not in opt.lower()]
            if valid:
                num = min(random.randint(1, 2), len(valid), 3)
                answers[idx] = ",".join(map(str, random.sample(valid, num)))
            else:
                answers[idx] = "1"

        elif qtype in ['scale_matrix', 'scale_single']:
            answers[idx] = str(random.randint(3, 5))

        elif q.get('options'):
            # Single choice - skip "其他"
            for i, opt in enumerate(q['options']):
                if '其他' not in opt.lower() and 'others' not in opt.lower():
                    answers[idx] = str(i + 1)
                    break
            else:
                answers[idx] = "1"
        else:
            answers[idx] = "1"

    return answers
