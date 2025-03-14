from langchain_community.chat_models import ChatLiteLLM
from smolagents import LiteLLMModel


#gemini_flash_2_exp_endpoints
MODEL_GEMINI_FLASH_2_EXP = "gemini/gemini-2.0-flash-exp"
lang_gemini_flash_2_exp = ChatLiteLLM(model=MODEL_GEMINI_FLASH_2_EXP)
smol_gemini_flash_2_exp = LiteLLMModel(model_id=MODEL_GEMINI_FLASH_2_EXP)
