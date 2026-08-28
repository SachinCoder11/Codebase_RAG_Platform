# backend/test_huggingface.py
"""
Standalone Hugging Face Connectivity Test
==========================================
Validates API connectivity independently of the ProviderFactory.
Run this BEFORE integrating HuggingFace into the main pipeline.

Usage:
    cd backend
    python test_huggingface.py
"""
import os
import sys
import time

# ── Load .env manually (no dependency on app.core.config) ──────────────────
def _load_dotenv():
    """Minimal .env loader — no external dependencies required."""
    env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    if not os.path.exists(env_path):
        env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())

_load_dotenv()

SEPARATOR = "=" * 50


def _print_header():
    print(f"\n{SEPARATOR}")
    print("  Hugging Face Connectivity Test")
    print(SEPARATOR)


def _print_result(label: str, value: str, ok: bool = True):
    mark = "[PASS]" if ok else "[FAIL]"
    print(f"  {label:<22}: {value} {mark}")


def _print_footer(passed: bool):
    print(SEPARATOR)
    if passed:
        print("  ALL CHECKS PASSED")
    else:
        print("  SOME CHECKS FAILED - see errors above")
    print(f"{SEPARATOR}\n")


def run_test():
    _print_header()
    all_passed = True

    # ── 1. Check API Key ───────────────────────────────────────────────────
    api_key = os.environ.get("HUGGINGFACE_API_KEY", "").strip()
    if not api_key:
        _print_result("API Key", "MISSING", ok=False)
        print("\n  Hugging Face API key missing.\n")
        print("  Please configure:\n")
        print("      HUGGINGFACE_API_KEY=hf_xxxxxxxxx\n")
        print("  in your .env file.\n")
        _print_footer(False)
        sys.exit(1)
    _print_result("API Key", "Configured")

    # ── 2. Read Model Name ─────────────────────────────────────────────────
    model = os.environ.get("HF_MODEL", "meta-llama/Llama-3.1-8B-Instruct").strip()
    _print_result("Model", model)

    # ── 3. Test API Connection & Model Access ──────────────────────────────
    try:
        from huggingface_hub import InferenceClient
    except ImportError:
        _print_result("huggingface-hub", "NOT INSTALLED", ok=False)
        print("\n  Install it with:  pip install huggingface-hub>=0.23.0\n")
        _print_footer(False)
        sys.exit(1)

    client = InferenceClient(model=model, token=api_key, timeout=120)

    # Test authentication and model reachability
    try:
        client.chat_completion(
            messages=[{"role": "user", "content": "Ping"}],
            max_tokens=1
        )
        _print_result("API Connected", "Yes")
        _print_result("Model Available", "Yes")
    except Exception as e:
        error_msg = str(e)
        if "401" in error_msg or "Unauthorized" in error_msg or "token" in error_msg.lower():
            _print_result("API Connected", "Auth Failed", ok=False)
            print("\n  Your API key was rejected. Check that it is valid and has\n"
                  "  access to the model. For gated models like Llama, accept the license at:\n"
                  f"  https://huggingface.co/{model}\n")
        elif "404" in error_msg or "not found" in error_msg.lower():
            _print_result("Model Available", f"NOT FOUND: {model}", ok=False)
            print(f"\n  Model '{model}' does not exist or you lack access.\n")
        else:
            _print_result("API Connected", f"Error: {error_msg[:60]}", ok=False)
        all_passed = False

    # ── 4. Test Response Generation & Measure Latency ──────────────────────
    if all_passed:
        test_prompt = "Explain what a Python decorator is in one sentence."
        try:
            start_time = time.time()
            messages = [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": test_prompt}
            ]
            chat_resp = client.chat_completion(
                messages=messages,
                max_tokens=128,
                temperature=0.7,
            )
            response = chat_resp.choices[0].message.content
            elapsed = time.time() - start_time

            if response and len(response.strip()) > 0:
                _print_result("Response Generated", f"({len(response)} chars)")
                _print_result("Latency", f"{elapsed:.2f} seconds")
            else:
                _print_result("Response Generated", "Empty response", ok=False)
                all_passed = False
        except Exception as e:
            error_msg = str(e)
            if "rate" in error_msg.lower() or "429" in error_msg:
                _print_result("Response Generated", "RATE LIMITED", ok=False)
                print("\n  You are being rate-limited. Wait a moment and retry.\n")
            elif "503" in error_msg or "loading" in error_msg.lower():
                _print_result("Response Generated", "MODEL LOADING", ok=False)
                print("\n  The model is still loading. Retry in 30-60 seconds.\n")
            else:
                _print_result("Response Generated", f"Error: {error_msg[:60]}", ok=False)
            all_passed = False

    _print_footer(all_passed)
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    run_test()
