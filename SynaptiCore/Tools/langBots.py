from langchain_core.tools import tool as langTools

from langchain_community.chat_models import ChatLiteLLM
from langchain_community.tools import (
    DuckDuckGoSearchRun,
    TavilySearchResults
)
from smolagents import LiteLLMModel 

from .smolBots import smolBots

class langBots:

    def __init__(self, langmodel: ChatLiteLLM, smolmodel: LiteLLMModel):
        self.langmodel = langmodel
        self.smolBots = smolBots(smolmodel)

        self.lang_duck_web_searcher_tool = langTools(self.lang_duck_web_searcher)
        self.smol_duck_web_searcher_tool = langTools(self.smol_duck_web_searcher)
        self.lang_tav_web_searcher_tool = langTools(self.lang_tav_web_searcher)
        self.calculator_tool = self._calculator

    def lang_tav_web_searcher(self,query: str) -> str:
        """
        Performs a web search using Tavily Search API and returns the results.
        This method utilizes the TavilySearchResults tool to perform an advanced web search
        with specified parameters.
        Args:
            query (str): The search query string to be processed.
        Returns:
            str: The search results from Tavily, including answers and raw content for up to 5 results.
        Example:
            >>> searcher = YourClass()
            >>> results = searcher.lang_tav_web_searcher("Python programming")
        """

        search_tool = TavilySearchResults(
            max_results=5,
            search_depth="advanced",
            include_answer=True,
            include_raw_content=True
        )
        return search_tool.run(query)
            
    def lang_duck_web_searcher(self,query: str) -> str:
        """Search the web for real-time information using DuckDuckGo.
        This function performs a web search using DuckDuckGo's search engine to retrieve
        current information based on the provided query.
        Args:
            query (str): The search query string to look up on the web.
        Returns:
            str: The search results as a formatted string containing relevant web content.
        Example:
            >>> result = lang_duck_web_searcher("latest Python release")
            >>> print(result)
            'Python 3.11.4 was released on...'
        Note:
            - Requires DuckDuckGoSearchRun to be properly imported and configured
            - Results may vary based on DuckDuckGo's search index and availability
            - Internet connection required for functionality
        """
        """Search the web for real-time information."""
        
        return DuckDuckGoSearchRun().run(query)  
    
    def smol_duck_web_searcher(self, query: str) -> str:
        """Search the web for real-time information.

        Args:
            query (str): Input for web search

        Returns:
            str: Result of the web search
        """
        return self.smolBots.smol_duck_web_searcher().run(str(query))
    
    def _calculator(self,query: str) -> str:
        """Processes the given mathematical expression and returns the calculated result.

        Args:
            query (str): Mathematical expression to evaluate

        Returns:
            str: Result of the calculation

        Examples:
            >>> calculator("2 + 2")
            '4'
            >>> calculator("5 * 3")
            '15'

        Note:
            The calculation is performed by the smolBots calculator component
        """
        return self.smolBots.calculater().run(str(query))
    
    @langTools
    def calculator(self, query: str) -> str:
        """Wrapper function to expose as a tool."""
        return self.calculator_tool(query)
