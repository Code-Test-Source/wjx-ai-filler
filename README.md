# WJX AI Survey Filler

注意：此工具仅适用于问卷星互助问卷社区，建议先积攒积分再打开问卷，并且适当停止问卷避免问卷被做爆－几千分。
<img width="870" height="97" alt="image" src="https://github.com/user-attachments/assets/fe413cf2-e3b2-4cfc-a72a-4fc91d16978b" />


A demo AI-powered survey automation tool for 问卷星 (WJX/WenJuanXing).

<img width="223" height="82" alt="8615e08c25a2e75f8ece64cc05c570b" src="https://github.com/user-attachments/assets/2a00d75b-389d-42e0-a7c9-8d74fc0f9903" />

Man!

<img width="249" height="22" alt="d4f33a86ce0ecba998402330ed16f0e" src="https://github.com/user-attachments/assets/ed127458-f568-42dc-8516-3282286bf9b3" />

传统检验毫无作用：

<img width="443" height="123" alt="5f4536fc68ee101c3547144b8a64cf6" src="https://github.com/user-attachments/assets/bfad55c0-4304-47d7-8c07-317f72cf73b2" />

Easy:

<img width="626" height="440" alt="9047c51cadf4a73d5548b198171692e" src="https://github.com/user-attachments/assets/05e01071-45d4-47d3-aa8e-67a96899b87c" />

<img width="751" height="417" alt="f0a3f461b73a1ec1fe9ce296d673438" src="https://github.com/user-attachments/assets/0524e8a5-b13d-4330-b3ff-2a9573942d19" />



机器人检验没办法，只能做不触发的，如果未来直接用Agent做的话那其实和人没啥区别了，可能可以解决。

<img width="258" height="198" alt="7b0159cfe7d2274462258260f5d1d17" src="https://github.com/user-attachments/assets/f4804e5e-f5fa-495e-8afc-a87058708124" />

无法解决部分情况下开始填写的问题，实际上点击了开始填写但是由于没办法体现在用户界面上最后没法通过安全校验，只能跳过这种。


## 项目简介

本项目旨在帮助用户自动化填写互助问卷以获取积分，从而获得其他用户的帮助性填写。这是一个练习性质的小项目。

**限制说明：** 问卷星限制每日最多填写30个互助问卷。

**优化建议：** 你可以通过调高填写问卷的最低积分要求（默认为20分）来获得尽可能多的积分，优先填写高积分问卷。

## Features

- **AI-Powered Answers**: Uses OpenAI-compatible API to intelligently answer survey questions
- **Browser Automation**: Selenium-based Chrome automation
- **Configurable**: API keys and settings via configuration or environment variables
- **Interactive Mode**: CLI and interactive modes available
- **Speed Control**: Built-in delays to avoid detection
- **Daily Limit**: WJX limits 30 surveys per day
- **Reward Filter**: Skips surveys with reward < 20 points

## ⚠️ Important Notes

### 安全校验无法绕过
- 问卷星的安全校验（验证码、滑块验证、人机验证等）**无法自动绕过**
- 遇到安全校验时，程序会卡住或失败，需要手动处理或跳过该问卷
- 这是平台的安全机制，不建议尝试绕过

### 问卷不能包含隐私信息
- Do not fill in surveys that ask for personal information (ID number, phone, address, etc.)
- The tool automatically skips "其他/Others" options to avoid fill-in-the-blank questions
- Be cautious when filling open-ended text questions

### 隐私保护
- **Never commit** the following files to git:
  - `.env` - contains your API keys and URLs
  - `cookies.json` - contains your login session
  - `conversation*.txt` - contains conversation history
- These files are already in `.gitignore`

## Setup

### 1. Create Virtual Environment & Install Dependencies

```bash
uv venv wjx-ai
uv sync
```

Or with pip:
```bash
python -m venv wjx-ai
wjx-ai\Scripts\activate  # Windows
pip install -r requirements.txt
```

### 2. Download ChromeDriver

> ⚠️ **Important:** `chromedriver.exe` must be placed in the **project root folder** (same level as `src/`).

**Auto Download (Recommended)**

Run the CLI command to automatically download the matching ChromeDriver:
```bash
uv run python -m src.cli download-driver
```

This will automatically detect your Chrome version and download the correct ChromeDriver to the project root.

**Manual Download (If Auto Fails)**

If auto-download fails, download manually:

1. Check your Chrome version: Open Chrome → Settings → About Chrome
2. Download matching ChromeDriver from:
   - Chrome 115+: https://googlechromelabs.github.io/chrome-for-testing/
   - Older versions: https://chromedriver.chromium.org/downloads
3. Place `chromedriver.exe` in the project root directory

### 3. Get WJX Cookies

**Method A: Browser Extension (Recommended)**
1. Login to wjx.cn in Chrome
2. Install "Cookie-Editor" extension from Chrome Web Store
3. Click the extension icon → Export → Export as JSON
4. Save the JSON content as `cookies.json` in the project root

**Method B: Use CLI Import**
```bash
uv run python -m src.cli import-cookies
```

> ⚠️ **Login Expired?** If you see login errors or the filler stops working, your cookies may have expired. Simply re-login to wjx.cn in your browser and export new cookies to `cookies.json`.

### 4. Configure API

Create `.env` file in project root:
```bash
# Copy from .env.example
cp .env.example .env
```

Edit `.env`:
```bash
API_URL=https://api.openai.com/v1
API_KEY=your-api-key-here
API_MODEL=gpt-4
WJX_ACTIVITY_URL=https://www.wjx.cn/wjx/promote/joinbacklist.aspx?activity=YOUR_ACTIVITY_ID
```

## Quick Start

```bash
# First time setup - run interactive setup
uv run python -m src.cli setup

# Run the filler
uv run python -m src.cli run

# Or use interactive mode
uv run python -m src.cli interactive
```

## CLI Commands

```bash
# Setup configuration interactively
uv run python -m src.cli setup

# Convert browser cookies to JSON format
uv run python -m src.cli import-cookies

# Run the survey filler
uv run python -m src.cli run

# Interactive mode
uv run python -m src.cli interactive

# Check configuration status
uv run python -m src.cli check
```

## Configuration

| Variable | Description | Required |
|----------|-------------|----------|
| `API_URL` | OpenAI-compatible API URL | Yes |
| `API_KEY` | API key | Yes |
| `API_MODEL` | Model name (default: gpt-4) | No |
| `WJX_ACTIVITY_URL` | Your WJX activity page URL | Yes |
| `CHROMEDRIVER_PATH` | Path to chromedriver.exe | No |
| `MIN_DELAY` | Min delay between actions (default: 1.5) | No |
| `MAX_DELAY` | Max delay between actions (default: 3.0) | No |

## Project Structure

```
wjx_ai_filler/
├── src/
│   ├── __init__.py
│   ├── cli.py              # CLI commands
│   ├── ai/                 # AI modules
│   │   ├── __init__.py
│   │   └── ai_answer.py    # AI answer generation
│   ├── browser/            # Browser automation
│   │   ├── __init__.py
│   │   └── chrome_driver.py
│   ├── filler/             # Survey filling logic
│   │   ├── __init__.py
│   │   ├── fill_survey.py  # Main filling logic
│   │   ├── auto_fetch.py   # Auto-fetch surveys
│   │   └── wjx_filler.py   # Utility functions
│   └── utils/              # Utilities
│       ├── __init__.py
│       └── config.py       # Configuration
├── main.py                 # Entry point
├── requirements.txt        # Python dependencies
├── .env.example            # Example configuration
├── .gitignore              # Git ignore rules
└── README.md
```

## Supported Question Types

- ✅ Single choice (radio buttons)
- ✅ Multiple choice (checkboxes)
- ✅ Text input / Textarea
- ✅ Dropdown / Select
- ✅ Matrix scale ratings (1-5)

## Troubleshooting

### Login / Cookie Issues
- **Problem**: Filler shows "请先登录" or stops working
- **Solution**: Your cookies have expired. Re-login to wjx.cn and export new cookies to `cookies.json`

### ChromeDriver Issues
- **Problem**: "chromedriver not found" or version mismatch
- **Solution**: Run `uv run python -m src.cli download-driver` to auto-download the correct version

### Daily Limit
- **Problem**: "每日限制已达" message
- **Solution**: WJX limits 30 surveys per day. Wait until tomorrow.

## License

MIT
