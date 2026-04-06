"""WJX AI Survey Filler package"""

from .utils.config import config
from .ai.ai_answer import generate_answer, get_ai_answers_batch
from .filler.fill_survey import fill_survey_with_ai, main as run_filler

__version__ = "1.0.0"