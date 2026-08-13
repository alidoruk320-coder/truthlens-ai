import os
import json

from dotenv import load_dotenv
import cohere
from tavily import TavilyClient


load_dotenv()

COHERE_API_KEY = os.getenv("COHERE_API_KEY")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")


if not COHERE_API_KEY:
    raise RuntimeError("COHERE_API_KEY bulunamadı.")

if not TAVILY_API_KEY:
    raise RuntimeError("TAVILY_API_KEY bulunamadı.")


co = cohere.ClientV2(COHERE_API_KEY)
tavily = TavilyClient(api_key=TAVILY_API_KEY)


# ------------------------------------------------------------
# GERÇEK WEB SEARCH TOOL
# ------------------------------------------------------------

def search_web(query: str):
    print("\n=== GERÇEK WEB ARAMASI ===")
    print("QUERY:", query)

    response = tavily.search(
        query=query,
        search_depth="advanced",
        max_results=5,
        include_answer=False,
    )

    results = []

    for item in response.get("results", []):
        results.append({
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "content": item.get("content", ""),
        })

    print("\n=== WEB SONUÇLARI ===")

    for i, result in enumerate(results, 1):
        print(f"\n[{i}] {result['title']}")
        print(result["url"])
        print(result["content"][:500])

    return results


# ------------------------------------------------------------
# COHERE TOOL TANIMI
# ------------------------------------------------------------

tools = [
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": (
                "İnternette güncel bilgi araştırmak için kullanılır. "
                "Gerçek web araması yapar ve kaynak URL'leri döndürür."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Web'de aranacak sorgu."
                    }
                },
                "required": ["query"]
            }
        }
    }
]


# ------------------------------------------------------------
# İLK MESAJ
# ------------------------------------------------------------

messages = [
    {
        "role": "user",
        "content": (
            "Türkiye'nin başkenti İstanbul'dur. "
            "Bu iddiayı web üzerinde araştır. "
            "Gerçek kaynakları kullan."
        )
    }
]


# ------------------------------------------------------------
# COHERE
# ------------------------------------------------------------

print("=== COHERE BAŞLIYOR ===")

response = co.chat(
    model="command-a-plus-05-2026",
    messages=messages,
    tools=tools,
)


# ------------------------------------------------------------
# TOOL CALL
# ------------------------------------------------------------

tool_calls = response.message.tool_calls or []

if not tool_calls:
    print("\nCohere web araması istemedi.")
    print(response.message)
    raise SystemExit


for tool_call in tool_calls:

    print("\n=== COHERE TOOL CALL ===")
    print(tool_call)

    if tool_call.function.name != "search_web":
        continue

    arguments = json.loads(
        tool_call.function.arguments
    )

    query = arguments["query"]

    results = search_web(query)


    # --------------------------------------------------------
    # TOOL SONUCUNU COHERE'A GERİ VER
    # --------------------------------------------------------

    messages.append(response.message)

    messages.append({
        "role": "tool",
        "tool_call_id": tool_call.id,
        "content": json.dumps(
            results,
            ensure_ascii=False
        )
    })


# ------------------------------------------------------------
# SON CEVAP
# ------------------------------------------------------------

print("\n=== COHERE SON CEVABI ===")

final_response = co.chat(
    model="command-a-plus-05-2026",
    messages=messages,
    tools=tools,
)


for item in final_response.message.content or []:

    if getattr(item, "type", None) == "text":
        print(item.text)


print("\n=== CITATIONS ===")

print(final_response.message.citations)