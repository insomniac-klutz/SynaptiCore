## Run your server 

-- Running 1:1 client <> servers

    uv run mcpClient.py <path_to_server.py>

-- Running 1:∞ client <> servers

    uv run mcpClient.py <path_to_server_1.py> <path_to_server_2.py> <path_to_server_3.py> . . . . .

    or 

    #ToDo
    uv run mcpClient.py mcpServer.py # After adding custom running instructions in mcpServer.py