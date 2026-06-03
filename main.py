import dotenv
import numpy as np
from langchain_classic.embeddings import CacheBackedEmbeddings
from langchain_classic.storage import LocalFileStore
from langchain_huggingface import HuggingFaceEmbeddings

# 加载 .env 文件中的环境变量。
# 如果你在 .env 中配置了 HF_TOKEN，这里加载后，Hugging Face 相关库就可以直接使用。
dotenv.load_dotenv()

# 指定要使用的中文向量模型。
# 这里单独保存模型名，方便同时给 embeddings 和缓存命名空间复用。
model_name = "BAAI/bge-large-zh-v1.5"

# 创建 Hugging Face 向量模型实例。
# 这个对象负责把输入文本转换成高维向量。
embeddings = HuggingFaceEmbeddings(model_name=model_name)

# 创建本地缓存目录。
# 已经生成过的向量会被保存到 ./cache，下次处理相同文本时可以直接复用。
store = LocalFileStore("./cache")

# 创建带缓存能力的嵌入器。
# 执行流程是：先查缓存；如果缓存不存在，再调用底层模型生成向量，并写入缓存。
# namespace 用模型名区分缓存空间，避免不同模型的结果混在一起。
cached_embedder = CacheBackedEmbeddings.from_bytes_store(
    embeddings,
    store,
    namespace=model_name,
)

# 准备要向量化的文本。
# 前两句语义接近，第三句语义明显不同，适合演示相似度和距离的差异。
texts = [
    "我叫焚影，我喜欢打篮球",
    "这个叫焚影的家伙，喜欢打篮球",
    "LangChain是什么",
]

# 批量生成文本向量。
# 返回值是一个二维列表：每条文本对应一个高维向量。
vectors = cached_embedder.embed_documents(texts)
print(vectors)

# 分别取出三条文本对应的向量，便于后续计算。
A, B, C = vectors

# 计算 A 和 B 的余弦相似度。
# 余弦相似度越接近 1，通常表示两段文本语义越相似。
similarity_ab = np.dot(A, B) / (np.linalg.norm(A) * np.linalg.norm(B))
print(similarity_ab)

# 计算 A 和 C 的余弦相似度。
# 由于两段文本主题不同，这个值通常会更低。
similarity_ac = np.dot(A, C) / (np.linalg.norm(A) * np.linalg.norm(C))
print(similarity_ac)

# 计算 A 和 B 的欧氏距离。
# 欧氏距离越小，通常表示两个向量越接近。
distance_ab = np.linalg.norm(np.array(A) - np.array(B))
print(distance_ab)

# 计算 A 和 C 的欧氏距离。
# 如果语义差异较大，这个距离通常会更大。
distance_ac = np.linalg.norm(np.array(A) - np.array(C))
print(distance_ac)
