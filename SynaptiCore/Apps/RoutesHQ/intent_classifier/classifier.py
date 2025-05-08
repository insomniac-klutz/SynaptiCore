"""
Intent classifier agent using Amazon Bedrock and LangGraph.

This module contains the implementation of an LLM-based intent classifier
for SQL query and visualization chatbot interactions using LangGraph.
"""
from typing import Dict, Any, Optional, Union, TypedDict, Annotated
from typing_extensions import Annotated

from langchain_core.prompts import ChatPromptTemplate
from langchain_aws import ChatBedrock
from langchain_core.output_parsers import StrOutputParser
from langgraph.graph import END, StateGraph
from langgraph.checkpoint.memory import MemorySaver

from .schema import (
    FirstQueryIntentType, 
    FollowupQueryIntentType,
    SalutationType,
    FirstQueryIntent,
    FollowupQueryIntent,
    SalutationIntent
)


# Prompt templates for intent classification
FIRST_QUERY_SYSTEM_PROMPT = """You are an intelligent assistant that helps classify user queries related to SQL and data visualization.
For the first query in a conversation, you need to determine if the user wants:

1. SQL_ONLY: To write a SQL query only without any visualization . This is default in case of ambiguity.
2. SQL_AND_CHART: To write a SQL query and also create a visualization/chart . Only tag this if user explicitly asks for a chart.

Analyze the user's query carefully and output the corresponding intent type.

Most Important Guardrails:
- Only output one of the specified intent types (SQL_ONLY or SQL_AND_CHART)
- Do not include explanations in your response
- Do not attempt to execute any SQL
- Do not suggest or recommend specific charts
- Do not include any text other than the intent type
"""

FOLLOWUP_QUERY_SYSTEM_PROMPT = """You are an intelligent assistant that helps classify user queries related to SQL and data visualization.
For follow-up queries in a conversation (not the first query), you need to determine if the user wants:

1. MODIFY_SQL_AND_CHART: To modify the SQL query and create a new chart/visualization based on the modified SQL. This is default in case of ambiguity.
2. MODIFY_CHART_ONLY: To modify only the chart/visualization without changing the SQL query . Only tag this if user explicitly asks for modification of the chart.

Analyze the user's query carefully, consider any context from previous interactions, and output the corresponding intent type.
Context may include previous SQL queries, chart configurations, and user feedback.

Most Important Guardrails:
- Only output one of the specified intent types (MODIFY_SQL_AND_CHART or MODIFY_CHART_ONLY)
- Do not include explanations in your response
- Do not attempt to modify or create any SQL code
- Do not suggest or recommend specific chart modifications
- Do not include any text other than the intent type
"""

SALUTATION_SYSTEM_PROMPT = """You are an intelligent assistant that helps identify different types of salutations in a conversation.
You need to determine if a user's message is one of the following salutation types:

1. GREETING: Messages like "Hi", "Hello", "Hey", etc.
2. GOODBYE: Messages like "Bye", "Goodbye", "See you", etc.
3. THANKS: Messages like "Thanks", "Thank you", "Appreciate it", etc.
4. OTHER: Any other type of salutation not covered above

Analyze the user's message carefully and output the corresponding salutation type.
If the message is not a salutation but an actual query, respond with "NOT_SALUTATION".

Most Important Guardrails:
- Only output one of the specified salutation types (GREETING, GOODBYE, THANKS, OTHER) or NOT_SALUTATION
- Do not include explanations in your response
- Do not engage in conversation or respond to the user's query content
- Do not include any text other than the salutation type or NOT_SALUTATION
"""

FIRST_QUERY_HUMAN_PROMPT = """Please classify the following user query into one of the specified intent types:

User query: {query}

Respond with only one of these values:
- SQL_ONLY
- SQL_AND_CHART

Most Important Guardrails:
- Return only the intent type as a single word
- No explanations, reasoning, or additional text
- No follow-up questions or suggestions
"""

FOLLOWUP_QUERY_HUMAN_PROMPT = """Please classify the following user query into one of the specified intent types:

User query: {query}

Previous context:
{context}

Respond with only one of these values:
- MODIFY_SQL_AND_CHART
- MODIFY_CHART_ONLY

Most Important Guardrails:
- Return only the intent type as a single phrase
- No explanations, reasoning, or additional text
- No follow-up questions or suggestions
"""

SALUTATION_HUMAN_PROMPT = """Please classify if the following message is a salutation, and if so, what type:

User message: {message}

Respond with only one of these values:
- GREETING
- GOODBYE
- THANKS
- OTHER
- NOT_SALUTATION

Most Important Guardrails:
- Return only the classification type as a single word
- No explanations, reasoning, or additional text
- No follow-up questions or suggestions
- Do not respond to the content of the message
"""


# Define state for our graph
class IntentClassifierState(TypedDict):
    """State for the intent classifier graph."""
    query: str  # This should be a simple field, not an annotated one
    is_first_query: bool
    context: Optional[Dict[str, Any]]
    salutation_type: Annotated[Optional[str], "override"]
    first_query_type: Annotated[Optional[str], "override"]
    followup_query_type: Annotated[Optional[str], "override"]
    final_intent: Annotated[Optional[Union[FirstQueryIntent, FollowupQueryIntent, SalutationIntent, None]], "override"]


# Node functions for our graph
def check_salutation(state: IntentClassifierState, llm):
    """Check if the input is a salutation."""
    salutation_prompt = ChatPromptTemplate.from_messages([
        ("system", SALUTATION_SYSTEM_PROMPT),
        ("human", SALUTATION_HUMAN_PROMPT)
    ])
    
    message = state["query"]
    salutation_chain = salutation_prompt | llm | StrOutputParser()
    salutation_str = salutation_chain.invoke({"message": message},
                                             config={"configurable": {"thread_id": 42}})
    
    # Update state with salutation result
    state["salutation_type"] = salutation_str.strip().lower()
    
    # Return the state with a next key to indicate which node to route to
    if state["salutation_type"] == "not_salutation":
        return {"state": state, "next": "route_query_type"}
    else:
        return {"state": state, "next": "create_final_intent"}


def route_query_type(state: IntentClassifierState):
    """Route to first query or followup query classifier based on is_first_query flag."""
    # Return a dictionary with the next node to route to
    if state["is_first_query"]:
        return {"state": state, "next": "classify_first_query"}
    else:
        return {"state": state, "next": "classify_followup_query"}


def classify_first_query(state: IntentClassifierState, llm):
    """Classify a first query."""
    first_query_prompt = ChatPromptTemplate.from_messages([
        ("system", FIRST_QUERY_SYSTEM_PROMPT),
        ("human", FIRST_QUERY_HUMAN_PROMPT)
    ])
    
    query = state["query"]
    first_query_chain = first_query_prompt | llm | StrOutputParser()
    intent_str = first_query_chain.invoke({"query": query},
                                          config={"configurable": {"thread_id": 42}})
    
    # Update state with classification result
    state["first_query_type"] = intent_str.strip().lower()
    
    # Return the state dictionary
    return {"state": state}


def classify_followup_query(state: IntentClassifierState, llm):
    """Classify a followup query."""
    followup_query_prompt = ChatPromptTemplate.from_messages([
        ("system", FOLLOWUP_QUERY_SYSTEM_PROMPT),
        ("human", FOLLOWUP_QUERY_HUMAN_PROMPT)
    ])
    
    query = state["query"]
    context = state["context"] or "No previous context available."
    followup_query_chain = followup_query_prompt | llm | StrOutputParser()
    intent_str = followup_query_chain.invoke({"query": query, "context": context},
                                             config={"configurable": {"thread_id": 42}})
    
    # Update state with classification result
    state["followup_query_type"] = intent_str.strip().lower()
    
    # Return the updated state as a dictionary
    return {"state": state}


def create_final_intent(state: IntentClassifierState):
    """Create the final intent object based on classification results."""
    
    # Check if it's a salutation
    if state["salutation_type"] and state["salutation_type"] != "not_salutation":
        try:
            salutation_type = SalutationType(state["salutation_type"])
        except ValueError:
            # If classification fails but we know it's a salutation, use OTHER
            salutation_type = SalutationType.OTHER
            
        state["final_intent"] = SalutationIntent(
            raw_query=state["query"],
            intent_type=salutation_type
        )
    
    # If it's a first query
    elif state["is_first_query"] and state["first_query_type"]:
        try:
            intent_type = FirstQueryIntentType(state["first_query_type"])
        except ValueError:
            # Default to SQL_ONLY if classification fails
            intent_type = FirstQueryIntentType.SQL_ONLY
            
        state["final_intent"] = FirstQueryIntent(
            raw_query=state["query"],
            intent_type=intent_type
        )
    
    # If it's a followup query
    elif not state["is_first_query"] and state["followup_query_type"]:
        try:
            intent_type = FollowupQueryIntentType(state["followup_query_type"])
        except ValueError:
            # Default to MODIFY_SQL_AND_CHART if classification fails
            intent_type = FollowupQueryIntentType.MODIFY_SQL_AND_CHART
            
        state["final_intent"] = FollowupQueryIntent(
            raw_query=state["query"],
            intent_type=intent_type,
            context=state["context"]
        )
    
    # If we couldn't classify it at all (should not happen with our implementation)
    else:
        state["final_intent"] = None
    
    # Return the state as a dictionary and indicate it's the end of the graph
    return {"state": state, "__end__": True}


class IntentClassifierGraph:
    """LangGraph-based intent classifier for SQL and visualization queries."""
    
    def __init__(self, model_id: str = "anthropic.claude-3-sonnet-20240229-v1:0", temperature: float = 0.0):
        """Initialize the intent classifier.
        
        Args:
            model_id: The Amazon Bedrock model ID to use
            temperature: Temperature for LLM sampling
        """
        self.llm = ChatBedrock(model_id=model_id, temperature=temperature)
        
        # Create the graph
        builder = StateGraph(IntentClassifierState)
        
        # Add nodes
        builder.add_node("check_salutation", lambda state: check_salutation(state, self.llm))
        builder.add_node("route_query_type", route_query_type)
        builder.add_node("classify_first_query", lambda state: classify_first_query(state, self.llm))
        builder.add_node("classify_followup_query", lambda state: classify_followup_query(state, self.llm))
        builder.add_node("create_final_intent", create_final_intent)
        
        # Set up the flow
        builder.set_entry_point("check_salutation")
        builder.add_edge("check_salutation", "route_query_type")
        builder.add_edge("check_salutation", "create_final_intent")
        builder.add_edge("route_query_type", "classify_first_query")
        builder.add_edge("route_query_type", "classify_followup_query")
        builder.add_edge("classify_first_query", "create_final_intent")
        builder.add_edge("classify_followup_query", "create_final_intent")
        
        # Add conditional edges based on node output
        builder.add_conditional_edges(
            "check_salutation",
            lambda output: output["next"],
            {
                "route_query_type": "route_query_type", 
                "create_final_intent": "create_final_intent"
            }
        )
        
        builder.add_conditional_edges(
            "route_query_type",
            lambda output: output["next"],
            {
                "classify_first_query": "classify_first_query", 
                "classify_followup_query": "classify_followup_query"
            }
        )
        
        # Save builder for visualization
        self.builder = builder
        
        # Initialize checkpoint and compile the graph
        self.graph = builder.compile(checkpointer=MemorySaver())
    
    def visualize_graph(self, height: int = 800, width: int = 1000):
        """Visualize the intent classifier graph with conditional edges using Graphviz.
        
        Args:
            height: Height of the visualization in pixels
            width: Width of the visualization in pixels
        
        Returns:
            Graphviz visualization of the graph that can be displayed in a notebook
        """
        try:
            from graphviz import Digraph
        except ImportError:
            print("Graphviz not installed. Install with: pip install graphviz")
            print("You may also need to install Graphviz system package: https://graphviz.org/download/")
            return None
            
        # Create a new directed graph
        dot = Digraph('Intent Classifier Graph')
        dot.attr(rankdir='TB', size=f"{width/72},{height/72}")
        dot.attr('node', shape='box', style='filled', fontname='Arial')
        
        # Define node colors and shapes
        node_styles = {
            "check_salutation": {"fillcolor": "#f8d56f", "shape": "diamond", "label": "check_salutation\n(Checks if query is a salutation)"},
            "route_query_type": {"fillcolor": "#f8d56f", "shape": "diamond", "label": "route_query_type\n(Routes based on query type)"},
            "classify_first_query": {"fillcolor": "#5fa8d3", "shape": "box", "label": "classify_first_query\n(Classifies first query intent)"},
            "classify_followup_query": {"fillcolor": "#5fa8d3", "shape": "box", "label": "classify_followup_query\n(Classifies followup query intent)"},
            "create_final_intent": {"fillcolor": "#7dcf85", "shape": "box", "label": "create_final_intent\n(Creates final intent object)"}
        }
        
        # Add nodes to the graph
        for node_id, style in node_styles.items():
            dot.node(node_id, style["label"], shape=style["shape"], fillcolor=style["fillcolor"])
        
        # Add conditional edges with labels
        dot.edge("check_salutation", "route_query_type", label="NOT_SALUTATION")
        dot.edge("check_salutation", "create_final_intent", label="SALUTATION") 
        dot.edge("route_query_type", "classify_first_query", label="is_first_query=True")
        dot.edge("route_query_type", "classify_followup_query", label="is_first_query=False")
        
        # Add standard edges
        dot.edge("classify_first_query", "create_final_intent")
        dot.edge("classify_followup_query", "create_final_intent")
        
        return dot

    def classify_query(self, query: str, is_first_query: bool = True, context: Optional[Dict[str, Any]] = None) -> Union[FirstQueryIntent, FollowupQueryIntent, SalutationIntent, None]:
        """Classify a user query into an intent.
        
        Args:
            query: The user's query to classify
            is_first_query: Whether this is the first query in a conversation
            context: Optional context from previous interactions
            
        Returns:
            An intent object (FirstQueryIntent, FollowupQueryIntent, or SalutationIntent)
        """
        # Create initial state for the graph
        initial_state = {
            "query": query,
            "is_first_query": is_first_query,
            "context": context,
            "salutation_type": None,
            "first_query_type": None,
            "followup_query_type": None,
            "final_intent": None
        }
        
        # Run the graph with the initial state
        result = self.graph.invoke(initial_state, config={"configurable": {"thread_id": 42}})
        
        # Extract and return the final intent
        return result.get("final_intent")