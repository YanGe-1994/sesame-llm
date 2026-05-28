import os
from dotenv import load_dotenv

# 初始化 Chat Model（LangChain 新版统一入口）
from langchain.chat_models import init_chat_model

# 用于“运行时可配置分支”的核心工具
from langchain_core.runnables import ConfigurableField
from langchain_core.runnables.configurable import RunnableConfigurableAlternatives
# 输出解析器：把模型输出统一转成字符串
from langchain_core.output_parsers import StrOutputParser

# Prompt 模板
from langchain_core.prompts import PromptTemplate

# 读取 .env 环境变量
load_dotenv()

# =========================
# 1. 初始化大模型
# =========================
llm = init_chat_model(
    model="qwen3.6-plus",  # 模型名称（Qwen 系列）
    model_provider="openai",  # 使用 OpenAI 兼容接口

    # API Key（从环境变量读取）
    openai_api_key=os.getenv("DASHSCOPE_API_KEY"),

    # API Base（例如 DashScope / OpenAI 兼容地址）
    openai_api_base=os.getenv("DASHSCOPE_BASE_URL"),
)

# =========================
# 2. 基础 Prompt（默认模板）
# =========================
prompt_default = PromptTemplate.from_template(
    "讲一个关于{topic}的笑话"
)

# =========================
# 3. 将 Prompt 改造成“可配置多分支版本”
# =========================
# configurable_alternatives：
# 👉 允许在运行时根据 prompt_style 选择不同 prompt
prompt_configurable = prompt_default.configurable_alternatives(
    ConfigurableField(id="prompt_style"),  # 配置字段名（运行时通过它切换）

    default_key="joke",  # 默认走 joke 模式

    # ===== 各种可选 prompt 分支 =====
    joke=PromptTemplate.from_template("讲一个关于{topic}的笑话"),
    poem=PromptTemplate.from_template("写一首关于{topic}的短诗"),
    story=PromptTemplate.from_template("写一个关于{topic}的小故事"),
    fact=PromptTemplate.from_template("列举关于{topic}的三个有趣事实")
)

# =========================
# 4. 组装 LCEL Chain
# =========================
# Prompt（可切换） → LLM → 输出解析
chain_configurable = prompt_configurable | llm | StrOutputParser()

# =========================
# 5. 运行时配置（控制走哪个 prompt）
# =========================
config_joke = {"configurable": {"prompt_style": "joke"}}
config_poem = {"configurable": {"prompt_style": "poem"}}
config_story = {"configurable": {"prompt_style": "story"}}

# =========================
# 6. 测试不同分支效果
# =========================
print("Joke 模式:")
print(chain_configurable.invoke({"topic": "python"}, config=config_joke))

print("\nPoem 模式:")
print(chain_configurable.invoke({"topic": "python"}, config=config_poem))

print("\nStory 模式:")
print(chain_configurable.invoke({"topic": "python"}, config=config_story))

# ==========================================================
# 7. 第二种方式：直接使用 RunnableConfigurableAlternatives
# ==========================================================

# 这种方式更“显式”，不用依赖 prompt 的 configurable_alternatives
configurable_prompt = RunnableConfigurableAlternatives(
    which=ConfigurableField(id="prompt_type"),  # 配置字段名

    # 默认 prompt（simple）
    default=PromptTemplate.from_template("简单回答：{question}"),
    default_key="simple",

    # 可选分支 prompt
    alternatives={
        "detailed": PromptTemplate.from_template("详细解释：{question}"),
        "casual": PromptTemplate.from_template("用口语回答：{question}")
    }
)

# 组装 chain
configurable_chain = configurable_prompt | llm | StrOutputParser()

# 运行：选择 detailed 分支
detailed_result = configurable_chain.invoke(
    {"question": "什么是云计算？"},
    config={"configurable": {"prompt_type": "detailed"}}
)

# 输出截断展示
print(f"\n详细模式回答: {detailed_result[:150]}...")