import asyncio
import os

import dotenv
from langchain.chat_models import init_chat_model
from langchain_core.output_parsers import JsonOutputParser
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain.agents import create_agent  # 或者使用你习惯的 Agent 构建方式

dotenv.load_dotenv()
async def main():
    # 1. 初始化客户端并配置服务器
    # 这里的配置直接对应你截图中的 JSON 结构
    client = MultiServerMCPClient(
        {
            "amap-maps": {  # 服务器名称，可自定义
                "transport": "stdio",  # 通信方式：通过标准输入输出与 npx 进程通信
                "command": "npx",  # 启动命令
                "args": [
                    "-y",  # 自动确认安装
                    "@amap/amap-maps-mcp-server"  # 包名
                ],
                "env": {
                    "AMAP_MAPS_API_KEY": "45262461ddafde77eae1e67b45ccd824"
                }
            }
        }
    )

    # 2. 获取转换后的工具列表
    # get_tools() 会启动 npx 进程，建立连接，并拉取所有可用的工具定义
    tools = await client.get_tools()

    print(f"成功加载了 {len(tools)} 个工具: {[t.name for t in tools]}")

    llm = init_chat_model(
        model="qwen3.6-plus",
        model_provider="openai",
        api_key=os.getenv("DASHSCOPE_API_KEY"),
        base_url=os.getenv("DASHSCOPE_BASE_URL"),
    )

    # 3. 将工具集成到 LangChain Agent 中
    # 假设你已经初始化了一个 LLM (例如 chat_model)
    agent = create_agent(model=llm, tools=tools)

    # 4. 使用 Agent 进行对话
    result = await agent.ainvoke({"messages": [("user", "帮我查一下北京今天的天气")]})
    print('result',result)

if __name__ == "__main__":
    asyncio.run(main())