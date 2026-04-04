from setuptools import setup, find_packages

setup(
    name="agentshrink",
    version="0.1.0",
    description="Automatically convert LLM agents to use cheaper local SLMs",
    packages=find_packages(),
    python_requires=">=3.10",
    install_requires=[
        "langchain>=0.3.7",
        "langchain-core>=0.3.19",
        "langchain-openai>=0.2.8",
        "langchain-google-genai>=2.0.9",
        "langgraph>=0.2.45",
        "click>=8.1.7",
        "python-dotenv>=1.0.1",
        "rich>=13.8.1",
        "fastapi>=0.115.5",
        "uvicorn>=0.32.0",
        "openai>=1.54.4",
        "huggingface_hub>=0.26.2",
    ],
    entry_points={
        "console_scripts": [
            "agentshrink=agentshrink.cli:cli",
        ],
    },
)
