import sys
import os
current_dir = os.getcwd() 
parent_dir = os.path.normpath(os.path.join(current_dir.split("SynaptiCore")[0], "SynaptiCore"))
sys.path.append(parent_dir)

from SynaptiCore.Tools.liteLM import lang_gemini_flash_2_exp, smol_gemini_flash_2_exp
from SynaptiCore.Apps.DeCypher import DeCypher 

# In[1]:

# Initialize DeCypher instance with language models
decypherApp = DeCypher(lang_gemini_flash_2_exp, smol_gemini_flash_2_exp)

# In[2]:
# Test the DeCypher App with a plain Web Search Query

web_search_message = "What is the time at this moment in India?"
final_state = decypherApp(web_search_message)

for i,message in enumerate(final_state["messages"]):
    print(f"Message {i}:\n")
    print("Type : " ,dict(message).get("type", "base").upper())
    print("\n")
    print(message.content)
    print("\n")
