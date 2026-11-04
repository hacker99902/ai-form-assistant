
import json
from groq import Groq
from app.core.config import settings


client = Groq(
    api_key=settings.GROQ_API_KEY
)


def test_groq():

    response = client.chat.completions.create(
        model=settings.GROQ_MODEL,

        messages=[
            {
                "role": "system",
                "content": (
                    "You are a JSON response generator. "
                    "Return valid JSON only."
                )
            },
            {
                "role": "user",
                "content": (
                    "Extract these details into JSON: "
                    "Name: Rahul Sharma, "
                    "Year of Birth: 1998, "
                    "City: Bengaluru."
                )
            }
        ],

        response_format={
            "type": "json_object"
        },

        temperature=0.1,
        max_tokens=500,
        reasoning_effort="low",
        include_reasoning=False
    )

    content = response.choices[0].message.content

    if not content:
        raise RuntimeError("Groq returned empty content")

    result = json.loads(content)

    print("Groq connection successful!")
    print(json.dumps(result, indent=4))


if __name__ == "__main__":
    test_groq()
