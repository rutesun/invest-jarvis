#!/usr/bin/env python
"""LangSmith 추적 테스트."""
import os
import sys
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv

# .env 로드
load_dotenv()

print("LangSmith 설정:")
print(f"  LANGSMITH_TRACING: {os.getenv('LANGSMITH_TRACING')}")
print(f"  LANGSMITH_API_KEY: {os.getenv('LANGSMITH_API_KEY', 'NOT SET')[:20]}...")
print(f"  LANGSMITH_PROJECT: {os.getenv('LANGSMITH_PROJECT')}")
print(f"  LANGSMITH_ENDPOINT: {os.getenv('LANGSMITH_ENDPOINT', 'default')}")

# 간단한 LLM 호출 테스트
print("\nLLM 호출 테스트...")
from src.llm.provider import LLMProvider
from langchain_core.messages import HumanMessage

llm = LLMProvider.create(provider="openai", model="gpt-4o", temperature=0.3)
response = llm.invoke([HumanMessage(content="Hello, test")])
print(f"응답: {response.content[:50]}...")
print("\n✓ LangSmith 추적이 활성화되면 https://smith.langchain.com 에서 확인 가능")
