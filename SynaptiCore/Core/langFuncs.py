
def pretty_state_print(final_state):
    for i,message in enumerate(final_state["messages"]):
        print(f"Message {i}:\n")
        print("Type : " ,dict(message).get("type", "base").upper())
        print("\n")
        print(message.content)
        print("\n")