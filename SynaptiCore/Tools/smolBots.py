from smolagents import (
                        CodeAgent , 
                        LiteLLMModel 
                    )

from smolagents import DuckDuckGoSearchTool


class smolBots:

    def __init__(self,smolmodel : LiteLLMModel):
        self.smolmodel = smolmodel

    def web_searcher(self,additional_authorized_imports = []):
        # Define Code Agent 1: Web Searcher
        return CodeAgent(
            tools=[DuckDuckGoSearchTool()],
            model=self.smolmodel,
            name="web_searcher",
            description="A code agent specialized in searching the web for information.  Use this agent to find specific data or answers to questions when it is not readily available in your current context. Always format the query for best search results.",
            additional_authorized_imports = additional_authorized_imports
            #use_e2b_executor=True
        )
    
    def calculater(self,additional_authorized_imports = ["math","numpy"] ):
        # Define Code Agent 2: Calculator
        return CodeAgent(
            tools=[],  # Calculator doesn't need tools, it can calculate directly
            model=self.smolmodel,
            name="calculator",
            description="A code agent specialized in performing mathematical calculations. Use this agent to solve any numerical problems. It is capable of complex arithmetic.",
            additional_authorized_imports=additional_authorized_imports,
            #use_e2b_executor=True
        )
