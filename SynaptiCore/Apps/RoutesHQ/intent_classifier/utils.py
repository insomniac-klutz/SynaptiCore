"""
Utility functions for the intent classifier module.
"""
from typing import Dict, Any, List, Optional
import json


def format_context(
    previous_sql: Optional[str] = None, 
    previous_chart_config: Optional[Dict[str, Any]] = None,
    previous_intents: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """Format context information for intent classification.
    
    Args:
        previous_sql: The previously used SQL query, if any
        previous_chart_config: The previously used chart configuration, if any
        previous_intents: List of previous intent classifications in the conversation
        
    Returns:
        Dictionary with formatted context information
    """
    context = {}
    
    if previous_sql:
        context["previous_sql"] = previous_sql
    
    if previous_chart_config:
        context["previous_chart_config"] = previous_chart_config
    
    if previous_intents:
        context["previous_intents"] = previous_intents
        
    return context


def context_to_string(context: Dict[str, Any]) -> str:
    """Convert context dictionary to a readable string for LLM prompts.
    
    Args:
        context: Context dictionary with information about previous interactions
        
    Returns:
        Formatted string representation of the context
    """
    if not context:
        return "No previous context available."
    
    context_parts = []
    
    if "previous_sql" in context:
        context_parts.append(f"Previous SQL Query:\n{context['previous_sql']}")
    
    if "previous_chart_config" in context:
        chart_str = json.dumps(context["previous_chart_config"], indent=2)
        context_parts.append(f"Previous Chart Configuration:\n{chart_str}")
    
    if "previous_intents" in context:
        intents_str = "\n".join([
            f"- {i+1}. {intent.get('raw_query', 'Unknown query')} "
            f"(Intent: {intent.get('intent_type', 'Unknown')})"
            for i, intent in enumerate(context["previous_intents"])
        ])
        context_parts.append(f"Previous Intents:\n{intents_str}")
    
    return "\n\n".join(context_parts)