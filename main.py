import os
from langchain.agents import create_agent
import dotenv
from langchain.chat_models import init_chat_model
from langchain_core.output_parsers import JsonOutputParser

dotenv.load_dotenv()

def get_weather(city: str) -> str:
    """Get weather for a given city."""
    return f"It's always sunny in {city}!"

llm = init_chat_model(
    model="qwen3.6-plus",
    model_provider="openai",
    api_key=os.getenv("DASHSCOPE_API_KEY"),
    base_url=os.getenv("DASHSCOPE_BASE_URL"),
)

agent = create_agent(
    model=llm,
    tools=[get_weather],
    system_prompt="你是一个天气查询助手"
)

chain = agent | JsonOutputParser()

# Run the agent
message = agent.invoke(
    {"messages": [{"role": "user", "content": "今天成都的天气如何?"}]}
)
print(message)