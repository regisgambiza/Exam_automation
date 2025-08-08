import json
import time
import ollama
import os

MEMORY_FILE = "solver_memory.json"
MODEL_NAME = "llama3.1:8b"
POLL_INTERVAL = 60  # seconds

def load_solver_memory():
    if not os.path.exists(MEMORY_FILE):
        print(f"[Warning] Memory file {MEMORY_FILE} not found.")
        return None
    try:
        with open(MEMORY_FILE, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"[Error] Failed to load memory file: {e}")
        return None

def create_prompt(memory_json):
    # We limit the memory size shown for readability (truncate if large)
    truncated_memory = dict(memory_json)
    if "memory" in truncated_memory and len(truncated_memory["memory"]) > 10:
        keys = list(truncated_memory["memory"].keys())[:10]
        truncated_memory["memory"] = {k: truncated_memory["memory"][k] for k in keys}
        truncated_memory["memory"]["..."] = "truncated for brevity"

    prompt = f"""
You are analyzing the state of an exam-solving AI. Here is its current memory snapshot as JSON:

{json.dumps(truncated_memory, indent=2)}

Please analyze and summarize:

- Current best score and how good it is compared to total questions (30).
- How many questions have confirmed correct answers.
- Which questions have been tested with multiple options and which options scored best.
- Are there any clear patterns or issues (e.g., many unanswered questions, no improvement recently).
- Suggest next steps or strategies for the solver.

Provide the summary in clear, concise bullet points.
"""
    return prompt

def main():
    last_summary = None
    print("Starting solver memory monitor (press Ctrl+C to stop)...")
    while True:
        memory = load_solver_memory()
        if memory:
            prompt = create_prompt(memory)
            try:
                response = ollama.chat(
                    model=MODEL_NAME,
                    messages=[{"role": "user", "content": prompt}]
                )
                summary = response['message']['content'].strip()
                if summary != last_summary:
                    print("\n--- AI Summary ---")
                    print(summary)
                    print("------------------")
                    last_summary = summary
                else:
                    print("[Info] No change in summary since last check.")
            except Exception as e:
                print(f"[Error] Ollama API call failed: {e}")
        else:
            print("[Info] No memory data to analyze.")

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
