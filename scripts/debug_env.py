"""환경 변수 디버깅 스크립트"""
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

# .env 로드
load_dotenv()

print("=" * 60)
print("🔍 환경 변수 디버깅")
print("=" * 60)

env_vars = [
    "CLAUDE_CODE_USE_BEDROCK",
    "ANTHROPIC_BEDROCK_BASE_URL",
    "AWS_SESSION_TOKEN",
    "AWS_REGION",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "API_TIMEOUT_MS",
]

for var in env_vars:
    value = os.getenv(var)
    if var == "AWS_SESSION_TOKEN" and value:
        print(f"{var}: {value[:30]}... (length: {len(value)})")
    elif value:
        print(f"{var}: {value}")
    else:
        print(f"{var}: ❌ NOT SET")

print("\n" + "=" * 60)
print("🧪 Bedrock 클라이언트 생성 테스트")
print("=" * 60)

try:
    import boto3
    from botocore.config import Config

    region = os.getenv("AWS_REGION", "us-east-1")
    endpoint_url = os.getenv("ANTHROPIC_BEDROCK_BASE_URL")
    session_token = os.getenv("AWS_SESSION_TOKEN")
    access_key = os.getenv("AWS_ACCESS_KEY_ID", "anything_is_fine")
    secret_key = os.getenv("AWS_SECRET_ACCESS_KEY", "anything_is_fine")

    print(f"\n📋 boto3 클라이언트 설정:")
    print(f"   region: {region}")
    print(f"   endpoint_url: {endpoint_url}")
    print(f"   session_token: {session_token[:30] if session_token else 'NOT SET'}...")

    bedrock_client = boto3.client(
        service_name="bedrock-runtime",
        region_name=region,
        endpoint_url=endpoint_url,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        aws_session_token=session_token,
        config=Config(
            retries={"max_attempts": 3, "mode": "standard"},
            connect_timeout=60,
            read_timeout=600,
        ),
    )

    print(f"\n✅ boto3 클라이언트 생성 성공!")
    print(f"   Endpoint: {bedrock_client.meta.endpoint_url}")

    # 간단한 API 호출 테스트
    print(f"\n🔧 API 호출 테스트...")
    from langchain_aws import ChatBedrockConverse
    from langchain_core.messages import HumanMessage

    llm = ChatBedrockConverse(
        model="us.anthropic.claude-haiku-4-5-20251001-v1:0",
        client=bedrock_client,
        temperature=0.0,
    )

    messages = [HumanMessage(content="Say 'Hello!'")]
    response = llm.invoke(messages)

    print(f"✅ API 호출 성공!")
    print(f"   Response: {response.content}")

except Exception as e:
    print(f"\n❌ 에러 발생: {e}")
    import traceback
    traceback.print_exc()
