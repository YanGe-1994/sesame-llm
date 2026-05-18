import os
from typing import Iterator, AsyncIterator
from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain_core.runnables import RunnableGenerator, RunnableLambda
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

load_dotenv()

llm = init_chat_model(
    model="qwen3.6-plus",
    model_provider="openai",
    api_key=os.getenv("DASHSCOPE_API_KEY"),
    base_url=os.getenv("DASHSCOPE_BASE_URL"),
)

def add_emoji_generator(input_stream: Iterator[str]) -> Iterator[str]:
    for token in input_stream:
        if "。" in token or "!" in token:
            yield token + "😊"
        else:
            yield token

emoji_runnable = RunnableGenerator(add_emoji_generator)

async def async_capitalize(input_stream: AsyncIterator[str]) -> AsyncIterator[str]:
    async for token in input_stream:
        yield token.upper()

async_runnable = RunnableGenerator(async_capitalize)

prompt = ChatPromptTemplate.from_template("讲一个关于{topic}的短笑话")
chain = prompt | llm | StrOutputParser() | emoji_runnable

print("流式输出（带表情符号）：")
for chunk in chain.stream({"topic": "程序员"}):
    print(chunk, end="", flush=True)