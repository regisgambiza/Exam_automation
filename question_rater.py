import requests
import json
from typing import List, Dict
from concurrent.futures import ThreadPoolExecutor
import logging
import statistics
import os

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

class OllamaMCQAnalyzer:
    """Handles MCQ analysis using multiple Ollama models via local API."""
    
    def __init__(self):
        """Initialize with Ollama endpoint and model list."""
        self.endpoint = "http://localhost:11434/api/generate"
        self.models = [
                        "mistral:7b-instruct-q4_0",
                        "qwen2:7b-instruct-q4_0",
                        "gemma2:9b",
                        "llama3.1:8b",
                        "nous-hermes2:10.7b",   
                    ]

        self.system_prompt = """
You are an expert MCQ analyst. For the question below, give:
1) A numeric confidence for each option A, B, C, D on a 0-100 scale (integers).
2) A 1-2 sentence rationale for each option.
3) A 1-sentence final answer (the option you consider best) and its confidence.

Format your reply exactly as JSON with fields:
{
  "scores": {"A": int, "B": int, "C": int, "D": int},
  "rationales": {"A": "text", "B": "text", "C": "text", "D": "text"},
  "final": {"choice": "A|B|C|D", "confidence": int}
}

Only output the JSON. Ensure the scores are integers 0-100.
"""
        self.rebuttal_prompt = """
You are an expert MCQ analyst. You previously rated a question and now see other models' initial ratings and rationales. Re-evaluate the question and options below. You may keep or adjust your scores. Provide a 1-paragraph rebuttal or endorsement explaining your reasoning for any adjustments or why you kept your scores.

Format your reply exactly as JSON with fields:
{
  "scores": {"A": int, "B": int, "C": int, "D": int},
  "rebuttal": "text",
  "final": {"choice": "A|B|C|D", "confidence": int}
}

Only output the JSON. Ensure the scores are integers 0-100.
"""

    def _call_model(self, model_name: str, prompt: str, question_id: int) -> Dict:
        logging.info(f"Processing question {question_id} with model {model_name}")
        payload = {
            "model": model_name,
            "prompt": f"{self.system_prompt.strip()}\n\n{prompt.strip()}",
            "stream": False
        }
        try:
            response = requests.post(self.endpoint, json=payload, timeout=60)
            response.raise_for_status()
            data = response.json()
            txt = data.get("response", "")

            start = txt.find('{')
            end = txt.rfind('}') + 1
            if start == -1 or end <= start:
                raise ValueError(f"No JSON object found in output: {txt}")

            return json.loads(txt[start:end])

        except Exception as e:
            logging.error(f"Failed to call {model_name} for question {question_id}: {e}")
            return {
                "scores": {"A": 0, "B": 0, "C": 0, "D": 0},
                "rationales": {"A": "", "B": "", "C": "", "D": ""},
                "final": {"choice": "A", "confidence": 0}
            }

    def _call_model_rebuttal(self, model_name: str, question: str, options: List[str], summary: str, question_id: int) -> Dict:
        """Call a model for Round 2 re-evaluation with a summary of Round 1."""
        logging.info(f"Processing question {question_id} with model {model_name} (Round 2)")
        prompt = f"""
    Question: {question}
    A) {options[0]}
    B) {options[1]}
    C) {options[2]}
    D) {options[3]}

    Round 1 Summary: {summary}
    """
        payload = {
            "model": model_name,
            "prompt": f"{self.rebuttal_prompt.strip()}\n\n{prompt.strip()}",
            "stream": False
        }
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = requests.post(self.endpoint, json=payload, timeout=60)
                response.raise_for_status()
                data = response.json()
                txt = data.get("response", "")
                start = txt.find('{')
                end = txt.rfind('}') + 1
                if start == -1 or end <= start:
                    raise ValueError(f"No JSON object found in output: {txt}")
                return json.loads(txt[start:end])
            except (ValueError, json.JSONDecodeError) as e:
                logging.error(f"Failed to parse JSON for {model_name} on question {question_id} (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    logging.info("Retrying after 5s")
                    time.sleep(5)
                    continue
                logging.error(f"Max retries reached for {model_name} on question {question_id}")
                return {
                    "scores": {"A": 0, "B": 0, "C": 0, "D": 0},
                    "rebuttal": "",
                    "final": {"choice": "A", "confidence": 0}
                }
            except Exception as e:
                logging.error(f"Failed to call {model_name} for question {question_id} (Round 2): {e}")
                return {
                    "scores": {"A": 0, "B": 0, "C": 0, "D": 0},
                    "rebuttal": "",
                    "final": {"choice": "A", "confidence": 0}
                }

    def _aggregate_results(self, results: List[Dict], round_num: int = 1) -> Dict:
        options = ["A", "B", "C", "D"]
        scores_by_option = {o: [] for o in options}
        rationales_by_option = {o: [] for o in options} if round_num == 1 else None
        
        for result in results:
            for opt in options:
                try:
                    scores_by_option[opt].append(int(result["scores"][opt]))
                    if round_num == 1:
                        rationales_by_option[opt].append(result["rationales"][opt])
                except (KeyError, ValueError):
                    continue
        
        aggregated = {}
        for opt in options:
            vals = scores_by_option[opt]
            mean = statistics.mean(vals) if vals else 0.0
            sd = statistics.stdev(vals) if len(vals) > 1 else 0.0
            aggregated[opt] = {"mean": round(mean, 1), "sd": round(sd, 1)}
            if round_num == 1:
                aggregated[opt]["rationales"] = rationales_by_option[opt]
        
        winner_data = max(aggregated.items(), key=lambda x: x[1]["mean"])
        winner = {
            "choice": winner_data[0],
            "mean_score": winner_data[1]["mean"],
            "consensus_sd": winner_data[1]["sd"]
        }
        
        return {
            "aggregated_scores": {k: v["mean"] for k, v in aggregated.items()},
            "winner": winner,
            "rationales": {k: v["rationales"] for k, v in aggregated.items()} if round_num == 1 else None
        }

    def _create_round1_summary(self, aggregated_results: Dict) -> str:
        summary = []
        for opt in ["A", "B", "C", "D"]:
            mean_score = aggregated_results["aggregated_scores"][opt]
            rationales = aggregated_results["rationales"][opt][:3]
            rationales = [r for r in rationales if r]
            summary.append(f"Option {opt}: Mean score = {mean_score}, Rationales: {'; '.join(rationales)}")
        return "\n".join(summary)

    def analyze_question(self, question_id: int, question: str, options: List[str], mode: str = "quick") -> Dict:
        logging.info(f"Analyzing question {question_id} in {mode} mode")
        prompt = f"""
Question: {question}
A) {options[0]}
B) {options[1]}
C) {options[2]}
D) {options[3]}
"""
        with ThreadPoolExecutor(max_workers=len(self.models)) as executor:
            results = list(executor.map(
                lambda m: self._call_model(m, prompt, question_id),
                self.models
            ))
        
        round1_results = self._aggregate_results(results, round_num=1)
        
        if mode == "quick":
            return {
                "question_id": question_id,
                **round1_results
            }
        
        summary = self._create_round1_summary(round1_results)
        with ThreadPoolExecutor(max_workers=len(self.models)) as executor:
            round2_results = list(executor.map(
                lambda m: self._call_model_rebuttal(m, question, options, summary, question_id),
                self.models
            ))
        
        return {
            "question_id": question_id,
            **self._aggregate_results(round2_results, round_num=2),
            "round1_summary": summary
        }

def run_mcq_debate(mode: str, input_file: str, output_file: str) -> List[Dict]:
    try:
        with open(input_file, "r") as f:
            question_data = json.load(f)
    except FileNotFoundError:
        raise FileNotFoundError(f"Input file {input_file} not found.")
    except json.JSONDecodeError:
        raise ValueError(f"Invalid JSON format in {input_file}.")

    questions = [
        {"question": q["question"], "options": q["options"]}
        for q in question_data.values()
    ]
    
    for q in questions:
        if len(q.get('options', [])) != 4:
            raise ValueError("Each question must have exactly 4 options.")
    
    if not questions:
        raise ValueError("No questions found in the input file.")

    analyzer = OllamaMCQAnalyzer()
    results = []
    
    for i, q in enumerate(questions, 1):
        result = analyzer.analyze_question(i, q['question'], q['options'], mode)
        results.append(result)
        logging.info(f"Completed analysis for question {i} in {mode} mode")
    
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)
    
    return results

if __name__ == "__main__":
    input_file = "questions_database.json"
    os.makedirs("results", exist_ok=True)
    
    run_mcq_debate("quick", input_file, "results/results_quick.json")
    run_mcq_debate("debate", input_file, "results/results_debate.json")
