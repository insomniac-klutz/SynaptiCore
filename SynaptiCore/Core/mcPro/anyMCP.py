from dotenv import load_dotenv

from ast import literal_eval
from collections import defaultdict

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
        
        #self.session: Optional[ClientSession] = None
        self.sessions = {}
        self.exit_stack = AsyncExitStack()
        self.RUN = False
        self.model_slug = model_slug
        self.tool_dir = defaultdict(lambda: None)
    
    async def register_tools(self,server_name,tools):
        for tool in tools:
            if not self.tool_dir.get(tool.name):
                self.tool_dir[tool.name] = server_name
            else:
                print(f'''Unable to register Tool '{tool.name}' with {server_name} . 
                        It is already registered to server {self.tool_dir[tool.name]}''')
                
                counter = 0
                while True:
                    ask_user = input(''' Which server would you like to use? \n\n1: {self.tool_dir[tool.name]} \n2: {server_name}\n\nInput 1 or 2 to continue : ''')
                    
                    try:
                        assert ask_user in ['1','2'], "Invalid input. Please enter 1 or 2."

                        if ask_user == '1':
                            print(f"Tool '{tool.name}' is already registered to server {self.tool_dir[tool.name]}.")
                            break
                        elif ask_user == '2':
                            print(f"Tool '{tool.name}' is now registered to server {server_name}.")
                            self.tool_dir[tool.name] = server_name
                            break
                    except AssertionError as e:
                        if counter < 3:
                            counter += 1
                            continue
                        else:
                            print(f"Maximum attempts reached. No changes made for {tool.name}.")

    async def connect_to_server(self, server_name: str,server_script_path: str):
        """Connect to an MCP server

        Args:
            server_script_path: Path to the server script (.py or .js)
        """
        if server_name in self.sessions:
            raise ValueError(f"Server with name '{server_name}' is already connected.")
        
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
        stdio, write = stdio_transport
        session = await self.exit_stack.enter_async_context(ClientSession(stdio, write))
        await session.initialize()

        # List available tools
        response = await session.list_tools()
        tools = response.tools

        # Register tools from this server with this session
        await self.register_tools(server_name,tools)
        print(f"\nConnected to server '{server_name}' with tools:", [tool for tool in tools])            
                    
        # Store the session and its resources
        self.sessions[server_name] = session

    async def process_query(self, query: str) -> str:
        """Process a query using Claude and available tools"""
        messages = [
            {
                "role": "user",
                "content": query
            }
        ]

        responses = []
        
        for server_name, session in self.sessions.items():
            resp = await session.list_tools()
            responses.append(resp)

        available_tools = [{
            "type": "function",
            "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.inputSchema
            }
        } for response in responses for tool in response.tools]

        # Initial LM API call
        response = completion(
                model=self.model_slug,
                messages=messages,
                tools=available_tools,
                tool_choice="auto"
            )

        print(response)
        # Process response and handle tool calls
        final_text = []

        content = response.choices[0]
        if content.finish_reason == 'stop' and content.message.tool_calls is None:
            final_text.append(content.message.content)
        elif content.finish_reason == 'tool_calls' or content.message.tool_calls is not None:
            for tool_inf in content.message.tool_calls:
                tool_name = tool_inf.function.name
                tool_args = literal_eval(tool_inf.function.arguments)
                tool_id = tool_inf.id
                print(f"Calling tool {tool_name} with args {tool_args} with id {tool_id}")

                # Execute tool call
                result = await self.sessions[self.tool_dir[tool_name]].call_tool(tool_name, tool_args)
                final_text.append(f"[Calling tool {tool_name} with args {tool_args} on server {self.tool_dir[tool_name]}]")

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