from langchain_core.tools import tool as langTools

from langchain_community.chat_models import ChatLiteLLM
from smolagents import LiteLLMModel 

from .smolBots import smolBots

class langBots:

    def __init__(self, langmodel: ChatLiteLLM, smolmodel: LiteLLMModel):
        self.langmodel = langmodel
        self.smolBots = smolBots(smolmodel)

        self.web_searcher_tool = langTools(self.web_searcher)
        self.calculator_tool = self._calculator
    
    def web_searcher(self, query: str) -> str:
        """Search the web for real-time information.

        Args:
            query (str): Input for web search

        Returns:
            str: Result of the web search
        """
        return self.smolBots.web_searcher().run(str(query))
    
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
