import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent))

import asyncio
from SynaptiCore.Core.mcPro.anyMCP import anyMCP

#from SynaptiCore.Tools.liteLM import MODEL_GEMINI_FLASH_2_EXP
from SynaptiCore.Tools.liteLM import MODEL_BEDROCK_CLAUDE_SONNET_3_5
    
async def main():
    if len(sys.argv) < 2:
        print("Usage: python client.py <path_to_server_script>")
        sys.exit(1)

    client = anyMCP(MODEL_BEDROCK_CLAUDE_SONNET_3_5)
    print("Initialized client")
    try:
        for server_script in sys.argv[1:]:
            server_name= server_script.split("/")[-1].split(".")[0]
            await client.connect_to_server(server_name,server_script)
        await client.chat_loop()
    finally:
        await client.cleanup()

if __name__ == "__main__":
    asyncio.run(main())