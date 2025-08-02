import os
import json
import csv
import time
import hashlib
import random
import re
from collections import defaultdict, Counter
from PIL import Image
import pytesseract
from playwright.sync_api import sync_playwright, Playwright

# Configuration
CONFIG = {
    "MEMORY_FILE": "question_memory.json",
    "CSV_FILE": "questions_log.csv",
    "STATE_FILE": "run_state.json",
    "PICS_DIR": "pics",
    "TOTAL_QUESTIONS": 30,
    "NUM_OPTIONS": 4,
    "BASE_URL": "https://ksp-7module.one.th/",
    "EXAM_URL": "https://ksp-exam.alldemics.com/exam/4155",
    "LOGIN_CREDENTIALS": {
        "id": "0047841106017",
        "password": "Ednicewonder1984"
    },
    "TESSERACT_PATH": r"C:\Program Files\Tesseract-OCR\tesseract.exe"
}

# Set Tesseract path
pytesseract.pytesseract.tesseract_cmd = CONFIG["TESSERACT_PATH"]

def question_hash(text):
    """Generate a hash for a question text."""
    return hashlib.md5(text.encode()).hexdigest()

def load_memory():
    """Load question memory from JSON file."""
    if os.path.exists(CONFIG["MEMORY_FILE"]):
        try:
            with open(CONFIG["MEMORY_FILE"], "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[error] Failed to load memory: {e}")
    return {}

def save_memory(memory):
    """Save question memory to JSON file."""
    with open(CONFIG["MEMORY_FILE"], "w", encoding="utf-8") as f:
        json.dump(memory, f, indent=2, ensure_ascii=False)

def append_to_csv(run_number, q_hash, question_text, options, picked_answer, score=None):
    """Append question data to CSV file."""
    rows = {}
    if os.path.exists(CONFIG["CSV_FILE"]):
        with open(CONFIG["CSV_FILE"], "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            next(reader, None)
            for row in reader:
                rows[row[1]] = row
    rows[q_hash] = [
        str(run_number), q_hash, question_text, "|".join(options),
        str(picked_answer), str(score if score else "")
    ]
    while len(rows) > CONFIG["TOTAL_QUESTIONS"]:
        key = next(iter(rows))
        del rows[key]
    with open(CONFIG["CSV_FILE"], "w", newline='', encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["run", "question_hash", "question_text", "options", "picked_answer", "score"])
        for row in rows.values():
            writer.writerow(row)

def load_state():
    """Load run state from JSON file."""
    if os.path.exists(CONFIG["STATE_FILE"]):
        try:
            with open(CONFIG["STATE_FILE"], "r", encoding="utf-8") as f:
                state = json.load(f)
                return state.get("run_number", 0), state.get("current_question_index", 0)
        except Exception as e:
            print(f"[error] Failed to load state: {e}")
    return 0, 0

def save_state(run_number, current_question_index):
    """Save run state to JSON file."""
    with open(CONFIG["STATE_FILE"], "w", encoding="utf-8") as f:
        json.dump({"run_number": run_number, "current_question_index": current_question_index}, f, indent=2)

def extract_text_from_pics_and_get_score():
    """Extract score from screenshots using OCR."""
    os.makedirs(CONFIG["PICS_DIR"], exist_ok=True)
    all_texts = []
    for fname in sorted(os.listdir(CONFIG["PICS_DIR"])):
        if fname.lower().endswith(".png"):
            img_path = os.path.join(CONFIG["PICS_DIR"], fname)
            try:
                img = Image.open(img_path)
                text = pytesseract.image_to_string(img, lang="eng+tha")
                all_texts.append(text)
            except Exception as e:
                print(f"[error] Failed to process {fname}: {e}")
    combined_text = "\n".join(all_texts)
    matches = re.findall(r'Score\s+(\d+)/30', combined_text, re.IGNORECASE)
    matches += re.findall(r'(\d+)\s*คะแนน', combined_text)
    if matches:
        last_score = int(matches[-1])
        for fname in os.listdir(CONFIG["PICS_DIR"]):
            if fname.lower().endswith(".png"):
                os.remove(os.path.join(CONFIG["PICS_DIR"], fname))
        return last_score
    return None

def deduce_best_options(question_data):
    """Deduce best options based on average scores."""
    best_options = {}
    for question_id, data in question_data.items():
        option_stats = defaultdict(lambda: {"total_score": 0, "count": 0})
        for attempt in data["tries"]:
            option = attempt["option"]
            score = attempt["score"]
            option_stats[option]["total_score"] += score
            option_stats[option]["count"] += 1
        option_averages = {opt: stats["total_score"] / stats["count"] for opt, stats in option_stats.items()}
        best_option = max(option_averages, key=lambda k: option_averages[k]) if option_averages else 1
        best_options[question_id] = {
            "best_option": best_option,
            "average_scores": option_averages,
            "tries": {opt: option_stats[opt]["count"] for opt in option_stats}
        }
    return best_options

def perform_login(page):
    """Perform login sequence."""
    page.goto(CONFIG["BASE_URL"])
    page.get_by_role("button", name="close").click()
    page.get_by_role("link", name="Login").click()
    page.get_by_role("textbox", name="ID card number / KSP ID").fill(CONFIG["LOGIN_CREDENTIALS"]["id"])
    page.get_by_role("textbox", name="Password").fill(CONFIG["LOGIN_CREDENTIALS"]["password"])
    page.get_by_role("button", name="login").click()
    page.get_by_role("button", name="close").click()
    page.get_by_role("link", name="My courses").click()
    page.locator("div").filter(has_text=re.compile(r"^Module 6$")).nth(1).click()
    page.get_by_role("button", name="Start Classes").click()

def navigate_to_exam(page):
    """Navigate to the exam page."""
    page.get_by_text("View Lesson").click()
    page.get_by_role("button", name="Final Exam Module 6 batch").click()
    page.get_by_role("option", name="Final Exam Module 6 batch").get_by_role("paragraph").click()
    page.get_by_role("button", name="Exam Again").click()
    page.get_by_role("button", name="TH", exact=True).click()
    page.get_by_role("button", name="EN", exact=True).click()

def extract_from_page(page):
    """Extract question text and choices from the page."""
    q_p = page.locator("div.container.app div.question p")
    q_p.first.wait_for(state="visible", timeout=5000)
    question_text = "\n".join(q_p.all_inner_texts())
    choices = page.locator("div.choice p").all_inner_texts()
    return question_text, choices

def click_answer(page, answer):
    """Click the specified answer option."""
    locator = page.locator("div.col-12 button").nth(answer-1)
    locator.wait_for(state="visible", timeout=5000)
    locator.click()

def click_next_or_break(page):
    """Click the Next button if available."""
    try:
        btn = page.locator('span.v-btn__content', has_text="Next >").first
        btn.wait_for(state="visible", timeout=5000)
        btn.click()
        return True
    except:
        return False

def submit_exam(page):
    """Submit the exam and capture screenshots."""
    page.locator("button").filter(has_text=re.compile(r"^Submit$")).click()
    page.locator("button").filter(has_text=re.compile(r"^Submit$")).click()
    start_time = time.time()
    count = 0
    while time.time() - start_time < 10:
        snap_path = os.path.join(CONFIG["PICS_DIR"], f"popup_{count}.png")
        page.screenshot(path=snap_path)
        count += 1
        time.sleep(0.2)
    return extract_text_from_pics_and_get_score()

def run_greedy_search():
    """Run the greedy search algorithm to optimize answers."""
    memory = load_memory()
    run_number, _ = load_state()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, channel="chrome")
        page = browser.new_page()
        perform_login(page)
        navigate_to_exam(page)

        # Collect all questions
        question_hashes, question_texts, question_choices_list = [], [], []
        while len(question_hashes) < CONFIG["TOTAL_QUESTIONS"]:
            question_text, choices = extract_from_page(page)
            q_hash = question_hash(question_text)
            if q_hash not in memory:
                memory[q_hash] = {"tries": [], "current_option": 1, "best_option": 1, "best_score": 0}
            question_hashes.append(q_hash)
            question_texts.append(question_text)
            question_choices_list.append(choices)
            if not click_next_or_break(page):
                break
        total_questions = len(question_hashes)

        # Initialize answers
        answers = {qh: memory[qh]["best_option"] for qh in question_hashes}
        attempts = 0

        while True:
            navigate_to_exam(page)
            for i, qh in enumerate(question_hashes):
                click_answer(page, answers[qh])
                append_to_csv(run_number, qh, question_texts[i], question_choices_list[i], answers[qh])
                if i < total_questions - 1:
                    if not click_next_or_break(page):
                        break
                time.sleep(0.5)

            score = submit_exam(page)
            attempts += 1
            print(f"[GreedySearch] Run {attempts} score: {score}/{total_questions}")

            for i, qh in enumerate(question_hashes):
                append_to_csv(run_number, qh, question_texts[i], question_choices_list[i], answers[qh], score)

            if score == total_questions:
                print("\n=== RESULTS SUMMARY ===")
                print(f"Total Questions: {total_questions}")
                print(f"Total Attempts: {attempts}")
                print("Answers:")
                for idx, qh in enumerate(question_hashes):
                    print(f"  Question {idx+1}: Option {answers[qh]}")
                save_memory(memory)
                browser.close()
                return

            # Greedy improvement
            improved = False
            question_order = question_hashes.copy()
            random.shuffle(question_order)

            for q_hash in question_order:
                best_option = answers[q_hash]
                best_score = score

                for opt in range(1, CONFIG["NUM_OPTIONS"] + 1):
                    if opt == answers[q_hash]:
                        continue
                    trial_answers = answers.copy()
                    trial_answers[q_hash] = opt

                    navigate_to_exam(page)
                    for i, qh in enumerate(question_hashes):
                        click_answer(page, trial_answers[qh])
                        if i < total_questions - 1:
                            if not click_next_or_break(page):
                                break
                        time.sleep(0.5)

                    trial_score = submit_exam(page)
                    attempts += 1
                    print(f"[GreedySearch] Trial {attempts}: Q{question_hashes.index(q_hash)+1} = {opt}, Score = {trial_score}/{total_questions}")

                    memory[q_hash]["tries"].append({"option": opt, "score": trial_score})
                    if trial_score > memory[q_hash]["best_score"]:
                        memory[q_hash]["best_score"] = trial_score
                        memory[q_hash]["best_option"] = opt

                    if trial_score > best_score:
                        best_score = trial_score
                        best_option = opt
                        improved = True

                    if trial_score == total_questions:
                        print("\n=== RESULTS SUMMARY ===")
                        print(f"Total Questions: {total_questions}")
                        print(f"Total Attempts: {attempts}")
                        print("Answers:")
                        for idx, qh in enumerate(question_hashes):
                            print(f"  Question {idx+1}: Option {trial_answers[qh]}")
                        save_memory(memory)
                        browser.close()
                        return

                if best_option != answers[q_hash]:
                    answers[q_hash] = best_option
                    memory[q_hash]["current_option"] = best_option
                    improved = True

            save_memory(memory)
            run_number += 1
            save_state(run_number, 0)

            if not improved:
                q_hash = random.choice(question_hashes)
                current_opt = answers[q_hash]
                new_opt = random.choice([i for i in range(1, CONFIG["NUM_OPTIONS"] + 1) if i != current_opt])
                answers[q_hash] = new_opt
                memory[q_hash]["current_option"] = new_opt
                print(f"[GreedySearch] Randomly set Q{question_hashes.index(q_hash)+1} to Option {new_opt}")

if __name__ == "__main__":
    run_greedy_search()