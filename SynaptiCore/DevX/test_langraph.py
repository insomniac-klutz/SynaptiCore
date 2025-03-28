import pandas as pd
from typing import Literal
from langchain.agents import Tool
from langchain_core.tools import tool as langTools
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph, MessagesState
from langgraph.prebuilt import ToolNode
from langchain_community.tools import DuckDuckGoSearchRun
from smolagents import (
    CodeAgent,
    LiteLLMModel,
    tool as smolTools
)

from langchain_community.chat_models import ChatLiteLLM
from langchain.agents import Tool
from langgraph.prebuilt import ToolNode

MODEL_GEMINI_FLASH_2_EXP = "gemini/gemini-2.0-flash-exp"
lang_gemini_flash_2_exp = ChatLiteLLM(model=MODEL_GEMINI_FLASH_2_EXP)
smol_gemini_flash_2_exp = LiteLLMModel(model_id=MODEL_GEMINI_FLASH_2_EXP)

RETRY_COUNTER = 0 # Global retry counter

# python_repl_tool = PythonREPLTool()

data = {
    'Name': ['Alice', 'Bob', 'Charlie', 'David', 'Eva'],
    'Age': [25, 30, 35, None, 28],
    'Salary': [50000, 60000, None, 70000, 55000],
    'Department': ['HR', 'Finance', 'IT', 'IT', 'HR']
}

@langTools
def search(query: str) -> str:
    """Search the web for real-time information."""
    
    search_tool = DuckDuckGoSearchRun()
    
    result = search_tool.run(query)
    return result  

@langTools
def calculator(query: str) -> str:
    """
       Perform Mathematical Calculations.

        Args:
            query: input for calculator

    """
    model = smol_gemini_flash_2_exp
    
    calculator_agent = CodeAgent(
        tools=[],  # Calculator doesn't need tools, it can calculate directly
        model=model,
        name="calculator",
        description="A code agent specialized in performing mathematical calculations. Use this agent to solve any numerical problems. It is capable of complex arithmetic.",
        additional_authorized_imports=["math","numpy"],
        #use_e2b_executor=True
    )

    return calculator_agent.run(str(query))

@langTools
def narration(df_dict: dict) -> str:
    """Narrate after doing analytics over the data in the dataframe."""

    def analytical_summary(df: pd.DataFrame) -> dict:
        '''
            Generate an analytical summary of a DataFrame with basic information and statistics.
            This function provides a comprehensive overview of the DataFrame including:
                1. Basic information (rows, columns, column names)
                2. Column data types
                3. Numerical statistics
                4. Categorical statistics
                5. Unique value counts
                6. Sample data
            Args:
                df (pd.DataFrame): Input DataFrame to analyze
            Returns:
                dict: Dictionary containing the following keys:
                    - basic_info (dict): Basic DataFrame information
                    - column_dtypes (pd.Series): Data types of each column
                    - numerical_stats (pd.DataFrame): Statistical summary of numerical columns
                    - categorical_stats (pd.DataFrame): Statistical summary of categorical columns
                    - unique_values (dict): Count of unique values per column
                    - sample_data (pd.DataFrame): Random sample of rows from the DataFrame
        '''
        basic_info = {
            'num_rows': df.shape[0],
            'num_columns': df.shape[1],
            'column_names': df.columns.tolist()
        }
        column_dtypes = df.dtypes
        numerical_stats = df.describe()
        categorical_stats = df.describe(include='object')
        unique_values = {col: df[col].nunique() for col in df.columns}
        sample_data = df.sample(min(5, len(df)))
        
        return {
            'basic_info': basic_info,
            'column_dtypes': column_dtypes,
            'numerical_stats': numerical_stats,
            'categorical_stats': categorical_stats,
            'unique_values': unique_values,
            'sample_data': sample_data
        }
    
    model = LiteLLMModel(model_id="bedrock/us.anthropic.claude-3-5-sonnet-20241022-v2:0")
    
    df = pd.DataFrame(df_dict)

    narration_agent = CodeAgent(
        tools=[], 
        model=model,
        name="narration",
        description=''' A storytelling agent that narrates the insights from the 
                        data in the given target_dataframe basis a base analysis. '
                        Use this agent to generate a narrative summary of the data, 
                        including key statistics and interesting patterns.''',
        additional_authorized_imports=["math","numpy","pandas"],
        #use_e2b_executor=True
    )

    df_analysis = analytical_summary(df)
    
    return narration_agent.run(f'''Base Analysis:{str(df_analysis)}''',additional_args={"target_dataframe":df})
    
tools = [
            search,
            calculator
            # narration
        ]

tool_node = ToolNode(tools)

model = lang_gemini_flash_2_exp.bind_tools(tools)

def should_continue(state: MessagesState) -> Literal["tools", END]:
    messages = state['messages']
    last_message = messages[-1]
    
    if last_message.tool_calls:
        return "tools"
    
    # if "Need to Retry" in last_message.content and RETRY_COUNTER < 3:
    #     RETRY_COUNTER += 1
    #     return "try_again"
        
    return END

def call_model(state: MessagesState):
    messages = state['messages']
    response = model.invoke(messages)
    return {"messages": [response]}

def try_again(state: MessagesState):
    messages = state['messages']
    messages = messages[:-1]  
    response = model.invoke(messages)
    return {"messages": [response]}

workflow = StateGraph(MessagesState)
workflow.add_node("agent", call_model)
workflow.add_node("tools", tool_node)
workflow.add_edge(START, "agent")

# workflow.add_node("try_again", try_again)
# workflow.add_edge("try_again", "agent")

workflow.add_conditional_edges(
    "agent",
    should_continue,
)

workflow.add_edge("tools", 'agent')

checkpointer = MemorySaver()

app = workflow.compile(checkpointer=checkpointer)

content = "what is the weather in sf"
# content = "2+3"
# content = "who played the world cup winning shot for first country to win cricket world cup at home "
# content = "calculate the population density of delhi ncr in 2024"
# content = "who the greatest basketball player of all time"
# content = "who the greatest basketball shooter of all time"
# content = "who the greatest basketball defender of all time"

# content = f"Analyze this data : {data}"

final_state = app.invoke(
    {
        "messages": [
                        {"role": "system", "content": "In case you feel like you need to retry add phrase : Need to Retry in the top of output"},
                        {"role": "user", "content": content }
                ]
    },
    config={"configurable": {"thread_id": 42}}
)

print(final_state["messages"][-1].content)

for i,message in enumerate(final_state["messages"]):
    print(f"Message {i}:\n")
    print("Type : " ,dict(message).get("type", "base").upper())
    print("\n")
    print(message.content)
    print("\n")

#app.get_graph().draw_png("workflow_graph.png")