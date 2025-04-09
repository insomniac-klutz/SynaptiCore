from typing import Literal

from langchain.agents import Tool
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import ToolNode

from langgraph.graph import (
    END,
    START,
    StateGraph,
    MessagesState
)

from smolagents import LiteLLMModel 
from langchain_community.chat_models import ChatLiteLLM

from SynaptiCore.Tools.langBots import langBots

class DeCypher:
    '''
        A class for managing conversational AI interactions with tool integration and state management.
        The DeCypher class provides a framework for creating and managing conversational AI agents
        with integrated tools and workflow management. It combines language models, state tracking,
        and tool execution in a flexible architecture.
            DeCypherBot (langBots): Instance handling language model interactions
            app (StateGraph): Workflow manager controlling conversation flow
            >>> lang_model = ChatLiteLLM(xxx)
            >>> smol_model = LiteLLMModel(xxx)
            >>> decypherApp = DeCypher(lang_model, smol_model)
            >>> # Use default flow
            >>> decypherApp(initial_messages)
            >>> # With custom tools
            >>> custom_tools = [CustomTool()]
            >>> decypherApp = DeCypher(lang_model, smol_model, additional_tools=custom_tools)
        Notes:
            - Supports both default and custom workflow definitions
            - Integrates with various tool implementations
            - Manages conversation state and memory
            - Provides built-in web search and calculation capabilities
    '''

    def __init__(self, langmodel: ChatLiteLLM, smolmodel: LiteLLMModel , app: StateGraph = None ,additional_tools: list[Tool] = []):
        """
        Initialize the DeCypher instance.
        This class initializes a DeCypher object with language models and state management capabilities.
        Parameters:
            langmodel (ChatLiteLLM): The main language model for chat interactions.
            smolmodel (LiteLLMModel): A lightweight language model for auxiliary processing.
            app (StateGraph, optional): Custom state graph for managing application flow. 
                If None, a default flow will be created. Defaults to None.
            additional_tools (list[Tool], optional): List of additional Tool instances to 
                be incorporated into the default flow. Defaults to empty list.
        Raises:
            AssertionError: If additional_tools is not a list of Tool instances, or
                if app is provided but is not an instance of StateGraph.
        Attributes:
            DeCypherBot: Instance of langBots initialized with the provided language models
            app: StateGraph instance managing the application flow
        """
        self.DeCypherBot = langBots(langmodel,smolmodel)

        if not app:
            assert isinstance(additional_tools,list) , "additional_tools must be a list of Tool instances"
            assert all([isinstance(tool,Tool) for tool in additional_tools]) , "additional_tools must be a list of Tool instances"
            self.app = self.draft_default_flow(additional_tools)
        else:
            assert isinstance(app, StateGraph) , "app must be an instance of StateGraph"
            self.app = app
    
    def __call__(self, content: str, system_message: str = None, additional_user_inputs: list[str] = None) -> dict:
            """
            Process content with system message and additional user inputs to generate a response.
            This method handles the processing of content through the application, incorporating
            system messages and additional user inputs into the conversation flow.
            Args:
                content (str): The main content to be processed.
                system_message (str, optional): Optional system message to set context. Defaults to None.
                additional_user_inputs (list[str], optional): Optional list of additional user messages. Defaults to None.
            Returns:
                dict: The final state response from the application.
            Raises:
                AssertionError: If system_message is not a string or additional_user_inputs is not
                                a list of strings.
            Example:
                >>> decypher = DeCypher(lang_model, smol_model)
                >>> result = decypher("Hello", "Be concise", ["Context1", "Context2"])
            """
            if system_message:
                assert isinstance(system_message, str), "system_message must be a string"
                system_draft = [{"role": "system", "content": system_message}]
            else:
                system_draft = []
            
            if additional_user_inputs:
                assert isinstance(additional_user_inputs, list), "additional_user_inputs must be a list"
                assert all([isinstance(input, str) for input in additional_user_inputs]), "additional_user_inputs must be a list of strings"
                additional_user_inputs = [{"role": "user", "content": input } for input in additional_user_inputs ]
            else:
                additional_user_inputs = []

            messages = system_draft + additional_user_inputs + [{"role": "user", "content": content}]
        
            final_state = self.app.invoke(
                {
                    "messages": messages
                },
                config={"configurable": {"thread_id": 42}}
            )
            
            return final_state

    @staticmethod
    def should_continue(state: MessagesState) -> Literal["tools", END]:
        """
        Determines the next state of processing based on the message state.
        Args:
            state (MessagesState): Current state containing messages and their metadata.
                                  MessagesState is expected to be a dict with a 'messages' key.
        Returns:
            Literal["tools", "end"]: Returns "tools" if the last message contains tool calls,
                                    otherwise returns "end" indicating processing should stop.
        Note:
            - The function examines the last message in the message history
            - Tool calls presence triggers continuation of processing
            - Absence of tool calls signals end of processing
        """
        messages = state['messages']
        last_message = messages[-1]
        
        if last_message.tool_calls:
            return "tools"
            
        return END
    
    def call_model(self, state: MessagesState) -> dict[str, list]:
        """
        Processes messages through the DeCypherLangBot model and returns the response.

        Args:
            state (MessagesState): A dictionary containing a 'messages' key with the conversation history

        Returns:
            dict[str, list]: A dictionary with 'messages' key containing a list with the model's response

        Example:
            state = {'messages': [{'role': 'user', 'content': 'Hello'}]}
            result = call_model(state)
            # Returns {'messages': [<model_response>]}
        """
        messages = state['messages']
        response = self.DeCypherBot.langmodel.invoke(messages)
        return {"messages": [response]}
    
    def default_tool_node(self,additional_tools = []):
        """
        Creates a default tool node with base tools and optional additional tools.
        This method initializes a tool node with basic functionalities including a web searcher
        and calculator, with the option to add more tools.
        Parameters:
            additional_tools (list[Tool]): Optional list of additional Tool instances to be added
                to the base toolset. Defaults to empty list.
        Returns:
            ToolNode: A new tool node instance containing the combined toolset.
        Raises:
            AssertionError: If additional_tools is not a list or contains non-Tool instances.
        Example:
            >>> bot = DeCypher()
            >>> custom_tool = CustomTool()
            >>> tool_node = bot.default_tool_node([custom_tool])
        """
        
        base_tools = [
            self.DeCypherBot.lang_tav_web_searcher_tool,
            self.DeCypherBot.calculator_tool
        ]
        
        assert isinstance(additional_tools,list) , "additional_tools must be a list of Tool instances"
        assert all([isinstance(tool,Tool) for tool in additional_tools]) , "additional_tools must be a list of Tool instances"
        
        if additional_tools:
            toolset = base_tools.extend(additional_tools)
        else:
            toolset = base_tools

        self.DeCypherBot.langmodel = self.DeCypherBot.langmodel.bind_tools(toolset,tool_choice="auto")

        return ToolNode(toolset)
    
    # def get_user_input(self):
    #     """
    #     Gets input from the user based on the current state.
    #     Args:
    #         state: The current state of the application.
    #     Returns:
    #         dict: A dictionary containing the user input with key 'user_input'.
    #     Example:
    #         >>> state = {}
    #         >>> result = get_user_input(state)
    #         Enter something: hello
    #         >>> print(result)
    #         {'user_input': 'hello'}
    #     """
    
    #     return {"user_input": input("Enter something: ")}

    def draft_default_flow(self,additional_tools = []):
        """
        Creates and compiles a default workflow with a state graph for agent-tool interaction.
        This method sets up a basic workflow that alternates between an agent and tools, 
        where the agent can decide whether to continue using tools or conclude the interaction.
        Parameters:
            additional_tools (list, optional): List of additional tools to be added to the default tool set.
                                             Defaults to empty list.
        Returns:
            function: A compiled workflow function with integrated memory checkpointing.
        Example:
            flow = agent.draft_default_flow()
            # Use flow as a compiled workflow function
            flow(input_messages)
        """

        tool_node = self.default_tool_node(additional_tools)

        workflow = StateGraph(MessagesState)
        workflow.add_node("agent", self.call_model)
        # workflow.add_node("get_input", self.get_user_input)
        workflow.add_node("tools", tool_node)
        workflow.add_edge(START, "agent")

        workflow.add_conditional_edges(
            "agent",
            self.should_continue,
        )

        workflow.add_edge("tools", 'agent')

        # workflow.set_entry_point("get_input")

        checkpointer = MemorySaver()

        return workflow.compile(checkpointer=checkpointer)


        
        
       