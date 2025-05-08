"""
Schema definitions for the intent classifier.
"""
from enum import Enum
from typing import Optional, Dict, Any, Literal
from pydantic import BaseModel, Field

class FirstQueryIntentType(str, Enum):
    """Intent types for the first query in a conversation."""
    SQL_ONLY = "sql_only"
    SQL_AND_CHART = "sql_and_chart"

class FollowupQueryIntentType(str, Enum):
    """Intent types for follow-up queries in a conversation."""
    MODIFY_SQL_AND_CHART = "modify_sql_and_chart"
    MODIFY_CHART_ONLY = "modify_chart_only"

class SalutationType(str, Enum):
    """Intent types for salutations in a conversation."""
    GREETING = "greeting"  # Hi, Hello, Hey
    GOODBYE = "goodbye"    # Bye, Goodbye, See you
    THANKS = "thanks"      # Thanks, Thank you, Appreciate it
    OTHER = "other"        # Other salutations

class Intent(BaseModel):
    """Base class for all intents."""
    raw_query: str = Field(..., description="The raw user query text")
    
class FirstQueryIntent(Intent):
    """Intent for the first query in a conversation."""
    intent_type: FirstQueryIntentType = Field(..., description="The type of first query intent")
    is_first_query: Literal[True] = True
    
class FollowupQueryIntent(Intent):
    """Intent for follow-up queries in a conversation."""
    intent_type: FollowupQueryIntentType = Field(..., description="The type of follow-up query intent")
    is_first_query: Literal[False] = False
    context: Optional[Dict[str, Any]] = Field(None, description="Any contextual information from previous interactions")

class SalutationIntent(Intent):
    """Intent for salutations in a conversation."""
    intent_type: SalutationType = Field(..., description="The type of salutation intent")
    is_salutation: Literal[True] = True