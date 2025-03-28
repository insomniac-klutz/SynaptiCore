import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent.parent))

import asyncio
from SynaptiCore.Core.mcPro.anyMCP import anyMCP

from SynaptiCore.Tools.liteLM import MODEL_GEMINI_FLASH_2_EXP
    
async def main():
    if len(sys.argv) < 2:
        print("Usage: python client.py <path_to_server_script>")
        sys.exit(1)

    client = anyMCP(MODEL_GEMINI_FLASH_2_EXP)
    print("Initialized client")
    try:
        await client.connect_to_server(sys.argv[1])
        await client.chat_loop()
    finally:
        await client.cleanup()

if __name__ == "__main__":
    asyncio.run(main())