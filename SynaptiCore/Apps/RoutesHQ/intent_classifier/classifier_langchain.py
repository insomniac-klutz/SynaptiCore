"""
Intent classifier agent using Amazon Bedrock and LangChain.

This module contains the implementation of an LLM-based intent classifier
for SQL query and visualization chatbot interactions.
"""
import os
from typing import Dict, Any, List, Optional, Union, cast

from langchain_core.prompts import ChatPromptTemplate
from langchain_aws import ChatBedrock
from langchain_core.output_parsers import StrOutputParser
from langchain.output_parsers import PydanticOutputParser
from langchain_core.runnables import RunnablePassthrough

from pydantic import BaseModel, Field

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


class IntentClassifier:
    """LLM-based intent classifier for SQL and visualization queries."""
    
    def __init__(self, model_id: str = "anthropic.claude-3-sonnet-20240229-v1:0", temperature: float = 0.0):
        """Initialize the intent classifier.
        
        Args:
            model_id: The Amazon Bedrock model ID to use
            temperature: Temperature for LLM sampling
        """
        self.llm = ChatBedrock(model_id=model_id, temperature=temperature)
        
        # Define first query classification chain
        first_query_prompt = ChatPromptTemplate.from_messages([
            ("system", FIRST_QUERY_SYSTEM_PROMPT),
            ("human", FIRST_QUERY_HUMAN_PROMPT)
        ])
        self.first_query_chain = (
            {"query": RunnablePassthrough()}
            | first_query_prompt
            | self.llm
            | StrOutputParser()
        )
        
        # Define followup query classification chain
        followup_query_prompt = ChatPromptTemplate.from_messages([
            ("system", FOLLOWUP_QUERY_SYSTEM_PROMPT),
            ("human", FOLLOWUP_QUERY_HUMAN_PROMPT)
        ])
        self.followup_query_chain = (
            {"query": lambda x: x["query"], "context": lambda x: x.get("context", "No previous context available.")}
            | followup_query_prompt
            | self.llm
            | StrOutputParser()
        )
        
        # Define salutation classification chain
        salutation_prompt = ChatPromptTemplate.from_messages([
            ("system", SALUTATION_SYSTEM_PROMPT),
            ("human", SALUTATION_HUMAN_PROMPT)
        ])
        self.salutation_chain = (
            {"message": RunnablePassthrough()}
            | salutation_prompt
            | self.llm
            | StrOutputParser()
        )
    
    def classify_first_query(self, query: str) -> FirstQueryIntent:
        """Classify a first query from a user.
        
        Args:
            query: The raw user query text
        
        Returns:
            FirstQueryIntent object with classified intent
        """
        intent_str = self.first_query_chain.invoke(query)
        
        try:
            intent_type = FirstQueryIntentType(intent_str.strip().lower())
        except ValueError:
            # Default to SQL_ONLY if classification fails
            intent_type = FirstQueryIntentType.SQL_ONLY
            
        return FirstQueryIntent(
            raw_query=query,
            intent_type=intent_type
        )
    
    def classify_followup_query(self, query: str, context: Optional[Dict[str, Any]] = None) -> FollowupQueryIntent:
        """Classify a followup query from a user.
        
        Args:
            query: The raw user query text
            context: Optional context from previous interactions
            
        Returns:
            FollowupQueryIntent object with classified intent
        """
        input_data = {"query": query, "context": context}
        intent_str = self.followup_query_chain.invoke(input_data)
        
        try:
            intent_type = FollowupQueryIntentType(intent_str.strip().lower())
        except ValueError:
            # Default to MODIFY_SQL_AND_CHART if classification fails
            intent_type = FollowupQueryIntentType.MODIFY_SQL_AND_CHART
            
        return FollowupQueryIntent(
            raw_query=query,
            intent_type=intent_type,
            context=context
        )
    
    def classify_salutation(self, message: str) -> Optional[SalutationIntent]:
        """Classify if a message is a salutation.
        
        Args:
            message: The raw user message text
            
        Returns:
            SalutationIntent object if the message is a salutation, None otherwise
        """
        salutation_str = self.salutation_chain.invoke(message)
        
        # If it's not a salutation, return None
        if salutation_str.strip().lower() == "not_salutation":
            return None
            
        try:
            salutation_type = SalutationType(salutation_str.strip().lower())
        except ValueError:
            # If classification fails but we know it's a salutation, use OTHER
            salutation_type = SalutationType.OTHER
            
        return SalutationIntent(
            raw_query=message,
            intent_type=salutation_type
        )
    
    def classify_query(self, query: str, is_first_query: bool = True, context: Optional[Dict[str, Any]] = None) -> Union[FirstQueryIntent, FollowupQueryIntent, SalutationIntent, None]:
        """Classify any query from a user.
        
        This method first checks if the query is a salutation. If not, it classifies it
        based on whether it's the first query or a followup.
        
        Args:
            query: The raw user query text
            is_first_query: Whether this is the first query in a conversation
            context: Optional context from previous interactions
            
        Returns:
            Intent object with classified intent or None if not classifiable
        """
        # First check if it's a salutation
        salutation_intent = self.classify_salutation(query)
        if salutation_intent:
            return salutation_intent
        
        # If not a salutation, classify as a query
        if is_first_query:
            return self.classify_first_query(query)
        else:
            return self.classify_followup_query(query, context)