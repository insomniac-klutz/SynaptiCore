from langchain_community.chat_models import ChatLiteLLM
from smolagents import LiteLLMModel

### LiteLLM compatible endpoints ###

#gemini_flash_2_exp_endpoints
MODEL_GEMINI_FLASH_2_EXP = "gemini/gemini-2.0-flash-exp"

### LiteLLM compatible endpoints ###

### Create LiteLLM Models ###

def create_gemini_flash_2_exp_mods(reqs: None):
    if reqs == "only_smol":
        return LiteLLMModel(model_id=MODEL_GEMINI_FLASH_2_EXP)
    elif reqs == "only_lang":
        return ChatLiteLLM(model=MODEL_GEMINI_FLASH_2_EXP)
    elif reqs == "all":
        return ChatLiteLLM(model=MODEL_GEMINI_FLASH_2_EXP) , LiteLLMModel(model_id=MODEL_GEMINI_FLASH_2_EXP)
