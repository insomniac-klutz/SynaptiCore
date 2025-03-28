from smolagents import CodeAgent, DuckDuckGoSearchTool, LiteLLMModel

from dotenv import (
    load_dotenv, 
    find_dotenv
)

load_dotenv(find_dotenv())

# Initialize a common model for all agents
model = LiteLLMModel(model_id="gemini/gemini-2.0-flash-exp") # Or any other model you prefer

# Define Code Agent 1: Web Searcher
web_search_agent = CodeAgent(
    tools=[DuckDuckGoSearchTool()],
    model=model,
    name="web_searcher",
    description="A code agent specialized in searching the web for information.  Use this agent to find specific data or answers to questions when it is not readily available in your current context. Always format the query for best search results.",
    #use_e2b_executor=True
)

# Define Code Agent 2: Calculator
calculator_agent = CodeAgent(
    tools=[],  # Calculator doesn't need tools, it can calculate directly
    model=model,
    name="calculator",
    description="A code agent specialized in performing mathematical calculations. Use this agent to solve any numerical problems. It is capable of complex arithmetic.",
    additional_authorized_imports=["math","numpy"],
    #use_e2b_executor=True
)

# Define Manager Agent
manager_agent = CodeAgent(
    tools=[], # Manager doesn't necessarily *need* tools, but could have them
    model=model,
    managed_agents=[web_search_agent, calculator_agent],
    name="manager",
    description="A managing agent responsible for coordinating web searches and calculations to complete complex tasks. It delegates web search tasks to 'web_searcher' and calculation tasks to 'calculator'. The goal is to use the two assistant agents for your final answer."
)

# Example usage:
task = "Find the population of Tokyo and then calculate what 1% of that population is."
result = manager_agent.run(task)

print(f"Final Result: {result}")