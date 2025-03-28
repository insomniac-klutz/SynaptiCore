from dotenv import load_dotenv

from ast import literal_eval

from typing import Optional
from contextlib import AsyncExitStack

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from litellm import completion

class anyMCP:
    def __init__(self,model_slug: str):
        # Initialize session and client objects
        # Model Slug should be litellm model slug for any of the supported models/providers : https://docs.litellm.ai/docs/providers

        load_dotenv()  # Load environment variables
        
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()
        self.RUN = False
        self.model_slug = model_slug

    async def connect_to_server(self, server_script_path: str):
        """Connect to an MCP server

        Args:
            server_script_path: Path to the server script (.py or .js)
        """
        is_python = server_script_path.endswith('.py')
        is_js = server_script_path.endswith('.js')
        if not (is_python or is_js):
            raise ValueError("Server script must be a .py or .js file")

        command = "python" if is_python else "node"
        server_params = StdioServerParameters(
            command=command,
            args=[server_script_path],
            env=None
        )

        stdio_transport = await self.exit_stack.enter_async_context(stdio_client(server_params))
        self.stdio, self.write = stdio_transport
        self.session = await self.exit_stack.enter_async_context(ClientSession(self.stdio, self.write))

        await self.session.initialize()

        # List available tools
        response = await self.session.list_tools()
        tools = response.tools
        print("\nConnected to server with tools:", [tool for tool in tools])

    async def process_query(self, query: str) -> str:
        """Process a query using Claude and available tools"""
        messages = [
            {
                "role": "user",
                "content": query
            }
        ]

        response = await self.session.list_tools()
        available_tools = [{
            "type": "function",
            "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.inputSchema
            }
        } for tool in response.tools]

        # Initial Claude API call
        response = completion(
                model=self.model_slug,
                messages=messages,
                tools=available_tools,
                tool_choice="auto"
            )
        
        print("respone",response)

        # Process response and handle tool calls
        final_text = []

        assistant_message_content = []

        content = response.choices[0]
        if content.finish_reason == 'stop':
            final_text.append(content.message.content)
            # assistant_message_content.append(content)
        elif content.finish_reason == 'tool_calls':
            for tool_inf in content.message.tool_calls:
                tool_name = tool_inf.function.name
                tool_args = literal_eval(tool_inf.function.arguments)
                tool_id = tool_inf.id
                print(f"Calling tool {tool_name} with args {tool_args} with id {tool_id}")

                # Execute tool call
                result = await self.session.call_tool(tool_name, tool_args)
                final_text.append(f"[Calling tool {tool_name} with args {tool_args}]")

                # assistant_message 
                messages.append({
                    "role": content.message.role,
                    "content": content.message.content,
                    "tool_calls": content.message.tool_calls
                })

                print("result", result)

                # tool_res_message 
                messages.append({
                    "tool_call_id": tool_id,
                    "role": "tool",
                    "name": tool_name,
                    "content": result.content[0].text,
                })

            print("\n")
            for message in messages:
                print("#",message)
                print("\n")

            # Get next response from Claude
            response = completion(
                    model=self.model_slug,
                    messages=messages,
                    tools=available_tools,
                    tool_choice="auto"
                )

            print("\n")
            print("response", response)
            print("\n")
            for message in messages:
                print("#",message)
                print("\n")

            print("##",response.choices[0].message.content)
            final_text.append(response.choices[0].message.content)

        return "\n".join(final_text)
    async def chat_loop(self):
        """Run an interactive chat loop"""
        print("\nMCP Client Started!")
        print("Type your queries or 'quit' to exit.")

        while True:
            try:
                query = input("\nQuery: ").strip()

                if query.lower() == 'quit':
                    break

                #print("\nQuery<>", query)
                response = await self.process_query(query)
                print("\n" + response)
                
                # if not self.RUN:
                #     query = "time now"
                #     self.RUN = True
                #     print("\nQuery:", query)
                #     response = await self.process_query(query)
                #     print("\n" + response)
                # else:
                #     break

            except Exception as e:
                print(f"\nError: {str(e)}")

    async def cleanup(self):
        """Clean up resources"""
        await self.exit_stack.aclose()