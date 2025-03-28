# In[0]:
import os
import sys
sys.path.append('..')

from SynaptiCore.Core.genFuncs import (
    add_dir_to_path, 
    load_env_file
)

add_dir_to_path(os.getcwd())
load_env_file()

from SynaptiCore.Tools.liteLM import create_gemini_flash_2_exp_mods
from SynaptiCore.Apps.DeCypher import DeCypher 
from SynaptiCore.Core.langFuncs import pretty_state_print

# In[1]:

# Initialize DeCypher instance with language models
language_models = create_gemini_flash_2_exp_mods(reqs="all")
decypherApp = DeCypher(*language_models)

# In[2]:
# Test the DeCypher App with a plain Web Search Query

web_search_message = "When and where did India win its last champions trophy?"
final_state = decypherApp(web_search_message)
pretty_state_print(final_state)

# In[3]:
# Test the DeCypher App with a plain Calculation Query

calc_msg = "212*212"
final_state = decypherApp(calc_msg)
pretty_state_print(final_state)

# In[4]:
# Test the DeCypher App with a Calculation and Web Search Combo

combo_msg_1 = "  add the total points scored in regular season by Steph Curry \
                        and Klay Thompson\
                        and tell me if their total is graeter than LBJ"
final_state = decypherApp(combo_msg_1)
pretty_state_print(final_state)
