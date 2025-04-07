import os
import sys
import time
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent))

import pandas as pd

from SynaptiCore.Core.genFuncs import (
    load_env_file
)

from SynaptiCore.Core.genFuncs import create_connection 
from mcp.server.fastmcp import FastMCP
from mcp.types import TextContent

load_env_file()

# Create an MCP server
mcp = FastMCP("Snowflake")

@mcp.tool()
def snowflake_exec(sql_query: str) -> str:
    """
    Executes a SQL query on the Snowflake database and retrieves the results.

    This function establishes a connection to the Snowflake database, executes 
    the provided SQL query, and returns the results as a string representation 
    of a DataFrame.

    Args:
        sql_query (str): The SQL query string to be executed.

    Returns:
        str: A string representation of the query results in DataFrame format.
    """

    start = time.time()
    conn = create_connection()
    query_result_dataframe = pd.read_sql(sql_query, conn)
    end = time.time()
    conn.close()

    execution_time = end - start

    return [TextContent(
                        type="text",
                        text=f"Results (execution time: {execution_time:.2f}s):\n{query_result_dataframe.to_string}"
                    )]

# Run the server
if __name__ == "__main__":
    print("Starting MCP Server")
    mcp.run()