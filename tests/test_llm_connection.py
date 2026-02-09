"""Quick smoke test to verify Gemini API connectivity and response."""

from browserfriend.config import get_config


def test_api_key_loaded():
    """GEMINI_API_KEY or GOOGLE_API_KEY is present in config."""
    config = get_config()
    api_key = config.google_api_key or config.gemini_api_key
    assert api_key, "No API key found. Set GEMINI_API_KEY or GOOGLE_API_KEY in .env"
    assert api_key != "your_google_api_key_here", "API key is still the placeholder value"
    print(f"API key loaded: {api_key[:8]}...{api_key[-4:]}")


def test_genai_package_importable():
    """google-genai package is installed and importable."""
    from google import genai

    assert genai is not None
    print("google-genai imported successfully")


def test_gemini_api_responds():
    """Gemini API accepts the key and returns a response."""
    from google import genai

    config = get_config()
    api_key = config.google_api_key or config.gemini_api_key

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents="Reply with exactly: HELLO",
    )

    assert response.text is not None
    assert len(response.text.strip()) > 0
    print(f"Gemini replied: {response.text.strip()}")
