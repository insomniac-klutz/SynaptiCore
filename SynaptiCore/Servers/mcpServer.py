import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent))

from SynaptiCore.Servers.serverDeCypher import mcpDeCypher
from SynaptiCore.Servers.serverSnowflake import mcpSnowflake

if __name__ == "__main__":
    print("Starting MCP mcpSnowflake Server")
    mcpSnowflake.run()
    print("Starting MCP mcpDeCypher Server")
    mcpDeCypher.run()

    