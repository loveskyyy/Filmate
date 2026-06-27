import asyncio

import httpx


async def test():
    api_key = "ak_bqgm1NvaRGNAMfAD0lFSlYMdASmsVYe3"
    base_url = "https://sk.aistore777.top/api/v1"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {"model": "GPT image2", "prompt": "test", "size": "16:9"}

    print(f"URL: {base_url}/images/generations")
    print(f"Headers: {headers}")
    print(f"Payload: {payload}")

    async with httpx.AsyncClient() as client:
        response = await client.post(f"{base_url}/images/generations", json=payload, headers=headers, timeout=30.0)
        print(f"Status: {response.status_code}")
        print(f"Response: {response.text}")


asyncio.run(test())
