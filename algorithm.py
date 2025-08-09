import json
import logging
import random
import time
from typing import Dict, List
import os
import ollama
import re

# Configure logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

def extract_from_page(page):
    """Extract question and choices from the page with error detection."""
    logging.debug("Extracting question and choices from page")
    try:
        # Check for exam errors before extraction
        if "error" in page.title().lower() or "too many" in page.title().lower():
            logging.error("Error page detected during extraction")
            return None, []
        
        q_p = page.locator("div.container.app div.question p")
        q_p.first.wait_for(state="visible", timeout=5000)
        question_text = "\n".join(q_p.all_inner_texts())
        choices = page.locator("div.choice p").all_inner_texts()
        logging.debug(f"Found question with {len(choices)} choices")
        return question_text, choices
    except Exception as e:
        logging.error(f"Failed to extract question and choices: {e}")
        return None, []

class SimpleGreedyExamSolver:
    def __init__(self, num_questions: int = 30, num_options: int = 4):
        self.num_questions = num_questions
        self.num_options = num_options
        self.best_score = 0
        self.best_answers = [1] * num_questions
        self.correct_answers = [None] * num_questions
        self.memory = {i: {"options": {}, "best_option": 1, "best_score": 0} for i in range(num_questions)}
        self.questions_file = "questions_database.json"
        self.memory_file = "solver_memory.json"
        self.attempts = [] 
        self.start_time = time.time()
        self.total_trials = 0  # Track total attempts for throttling
        self.load_memory()
        logging.debug(f"Initialized solver: {num_questions} questions, {num_options} options")

    def save_memory(self):
        """Save memory and progress to disk."""
        progress = {
            "best_score": self.best_score,
            "best_answers": self.best_answers,
            "correct_answers": self.correct_answers,
            "memory": {str(k): {"options": {str(opt): score for opt, score in v["options"].items()},
                               "best_option": v["best_option"], "best_score": v["best_score"]}
                       for k, v in self.memory.items()},
            "total_trials": self.total_trials
        }
        try:
            with open(self.memory_file, "w") as f:
                json.dump(progress, f, indent=2)
            logging.debug(f"Saved memory to {self.memory_file}")
        except Exception as e:
            logging.error(f"Failed to save memory: {e}")

    def load_memory(self):
        """Load memory and progress from disk with anti-plateau measures."""
        if os.path.exists(self.memory_file) and os.path.getsize(self.memory_file) > 0:
            try:
                with open(self.memory_file, "r") as f:
                    progress = json.load(f)
                self.best_score = progress.get("best_score", 0)
                self.best_answers = progress.get("best_answers", [1] * self.num_questions)
                self.correct_answers = progress.get("correct_answers", [None] * self.num_questions)
                self.memory = {
                    int(k): {
                        "options": {int(opt): score for opt, score in v["options"].items()},
                        "best_option": v["best_option"],
                        "best_score": v["best_score"]
                    } for k, v in progress.get("memory", {}).items()
                }
                self.total_trials = progress.get("total_trials", 0)
                
                # Anti-plateau measure: Clear memory if stuck at high score
                if self.best_score >= 17:
                    logging.info("Clearing memory post-17 score to prevent plateau")
                    for i in range(self.num_questions):
                        if self.correct_answers[i] is None:
                            self.memory[i] = {"options": {}, "best_option": 1, "best_score": 0}
                
                confirmed_count = sum(1 for ans in self.correct_answers if ans is not None)
                logging.info(f"Loaded memory: best_score={self.best_score}, "
                             f"confirmed={confirmed_count}/{self.num_questions}")
            except Exception as e:
                logging.error(f"Failed to load memory: {e}")
                self.reset_state()
        else:
            logging.info(f"No valid {self.memory_file} found, initializing with default state")
            self.reset_state()
            
    def reset_state(self):
        """Reset solver to initial state"""
        self.best_score = 0
        self.best_answers = [1] * self.num_questions
        self.correct_answers = [None] * self.num_questions
        self.memory = {i: {"options": {}, "best_option": 1, "best_score": 0} for i in range(self.num_questions)}
        self.total_trials = 0

    def retrieve_questions(self, page) -> Dict:
        """Retrieve questions and options if JSON is missing or empty."""
        if os.path.exists(self.questions_file) and os.path.getsize(self.questions_file) > 0:
            try:
                with open(self.questions_file, "r") as f:
                    questions_data = json.load(f)
                if questions_data and len(questions_data) == self.num_questions:
                    logging.info(f"Loaded {len(questions_data)} questions from {self.questions_file}")
                    return questions_data
            except Exception as e:
                logging.error(f"Failed to load questions from {self.questions_file}: {e}")

        logging.info("Retrieving questions from exam page...")
        questions_data = {}
        try:
            for q_idx in range(self.num_questions):
                question_text, options = extract_from_page(page)
                if question_text is None or len(options) != self.num_options:
                    logging.error(f"Failed to retrieve Q{q_idx + 1}: question_text={question_text}, options={options}")
                    continue
                questions_data[f"q{q_idx + 1}"] = {
                    "question": question_text,
                    "options": options
                }
                logging.debug(f"Retrieved Q{q_idx + 1}: {question_text} with {len(options)} options")
                if q_idx < self.num_questions - 1:
                    page.get_by_role('button', name='Next >').click(timeout=1000)
                    page.wait_for_timeout(500)
            with open(self.questions_file, "w") as f:
                json.dump(questions_data, f, indent=2)
            logging.info(f"Saved {len(questions_data)} questions to {self.questions_file}")
        except Exception as e:
            logging.error(f"Failed to retrieve questions: {e}")
        return questions_data

    def ai_debate_answers(self, questions_data: Dict) -> List[int]:
        """Use multiple Ollama models with weighted voting for initial answers."""
        models = [
            ("llama3.1:8b", 1.4),
            ("gemma2:9b", 1.3),
            ("qwen2:7b-instruct-q4_0", 1.2),
            ("mistral:7b-instruct-q4_0", 1.0),
            ("phi3:latest", 0.9)
        ]
        answers = [1] * self.num_questions
        logging.info("Starting AI debate for initial answers...")

        for q_idx in range(self.num_questions):
            q_key = f"q{q_idx + 1}"
            if q_key not in questions_data:
                logging.warning(f"Question {q_key} not found in data")
                continue

            question = questions_data[q_key]["question"]
            options = questions_data[q_key]["options"]
            prompt = (
                f"You are answering a multiple-choice question.\n"
                f"Question: {question}\n"
                f"Options:\n" +
                "\n".join([f"{i + 1}. {opt}" for i, opt in enumerate(options)]) +
                "\nPick the best option (1-4) and briefly explain why, but put ONLY the number on the first line."
            )

            weighted_votes = {}
            for model, weight in models:
                try:
                    response = ollama.chat(model=model, messages=[{"role": "user", "content": prompt}])
                    response_text = response['message']['content'].strip()
                    match = re.search(r'\b[1-4]\b', response_text)
                    if match:
                        answer = int(match.group(0))
                        weighted_votes[answer] = weighted_votes.get(answer, 0) + weight
                        logging.debug(f"Model {model} ({weight}x) answered {answer} for Q{q_idx + 1}")
                    else:
                        logging.warning(f"Invalid answer format '{response_text}' from {model} for Q{q_idx + 1}")
                except Exception as e:
                    logging.error(f"Model {model} failed for Q{q_idx + 1}: {e}")

            if weighted_votes:
                best_answer = max(weighted_votes.items(), key=lambda x: x[1])[0]
                answers[q_idx] = best_answer
            else:
                answers[q_idx] = random.randint(1, self.num_options)
                logging.warning(f"Q{q_idx + 1}: No valid model answers, using random option {answers[q_idx]}")

        logging.info(f"AI debate completed: Initial answers {answers}")
        return answers

    def try_option_for_question(self, question_idx: int, option: int, exam_callback) -> int:
        """Try a specific option with robust error handling and throttling."""
        self.total_trials += 1
        guess = self.best_answers.copy()
        guess[question_idx] = option
        
        # Anti-flood throttling (progressive delay)
        delay_seconds = min(5.0, 0.5 + (0.1 * self.total_trials))
        logging.debug(f"Delaying {delay_seconds:.1f}s before attempt #{self.total_trials}")
        time.sleep(delay_seconds)
        
        try:
            logging.debug(f"Trying Q{question_idx + 1} with option {option}")
            result_text, score_text = exam_callback(guess)
            
            # Robust score parsing
            if score_text is None:
                logging.warning("No score text returned")
                return 0
                
            # First try standard "X/Y" format
            match = re.search(r'(\d+)\s*/\s*\d+', score_text)
            if match:
                score = int(match.group(1))
                logging.debug(f"Standard score format detected: {score}/{self.num_questions}")
            else:
                # Fallback: extract first number
                nums = re.findall(r'\d+', score_text)
                if nums:
                    score = int(nums[0])
                    logging.warning(f"Non-standard score format: '{score_text}'. Using first number: {score}")
                else:
                    logging.error(f"Unparseable score: '{score_text}'")
                    return 0
            
            # Validate score range
            if not (0 <= score <= self.num_questions):
                logging.warning(f"Illegal score value {score} from '{score_text}'")
                return 0
                
            logging.info(f"Q{question_idx + 1}, option {option} scored {score}/{self.num_questions}")
            return score
            
        except Exception as e:
            logging.error(f"Evaluation crashed for Q{question_idx+1}, option {option}: {str(e)}")
            return 0

    def systematic_trial_phase(self, exam_callback, attempt_num: int) -> bool:
        """Try all options for each question systematically, updating memory."""
        improved = False
        changed_questions = []
        failed_options = []

        for q_idx in range(self.num_questions):
            if self.correct_answers[q_idx] is not None:
                logging.debug(f"Q{q_idx + 1} already confirmed as option {self.correct_answers[q_idx]} ✅")
                continue

            # Try each untried option for this question
            untried_options = [opt for opt in range(1, self.num_options + 1)
                               if opt not in self.memory[q_idx]["options"]]
            if not untried_options:
                logging.debug(f"Q{q_idx + 1}: All options tried")
                continue

            logging.info(f"Systematic trial for Q{q_idx + 1}: Testing options {untried_options}")
            prev_option = self.best_answers[q_idx]
            for option in untried_options:
                score = self.try_option_for_question(q_idx, option, exam_callback)
                
                # Only record valid attempts (score > 0)
                if score > 0:
                    self.memory[q_idx]["options"][option] = score
                    
                    # Track changed questions
                    if option != prev_option:
                        changed_questions.append((q_idx, prev_option, option))

                    # Update best option for this question
                    if score > self.memory[q_idx]["best_score"]:
                        self.memory[q_idx]["best_score"] = score
                        self.memory[q_idx]["best_option"] = option
                        logging.info(f"Q{q_idx + 1}: New best option {option} with score {score} 🆕")
                        improved = True

                    # Update global best if overall score improves
                    if score > self.best_score:
                        self.best_score = score
                        self.best_answers[q_idx] = option
                        logging.info(f"New global best score: {self.best_score}/{self.num_questions} 🌟")
                        
                        # Confirm correct answers if perfect score
                        if score == self.num_questions:
                            self.correct_answers[q_idx] = option
                            logging.info(f"Q{q_idx + 1}: Confirmed correct answer {option} ✅")
                            
                        self.save_memory()
                    elif score < self.best_score:
                        failed_options.append((q_idx, option))

                    # Update best answer for this question
                    self.best_answers[q_idx] = self.memory[q_idx]["best_option"]
                else:
                    logging.warning(f"Invalid score for Q{q_idx+1}, option {option} - not recorded")

            if self.best_score == self.num_questions:
                logging.info("Perfect score achieved! Stopping systematic trial.")
                break

        # Log comprehensive summary report
        self.log_summary_report(attempt_num, changed_questions, failed_options)

        self.save_memory()
        return improved

    def random_forced_change(self):
        """Make a random change to escape local maxima."""
        changeable_indices = [i for i, ans in enumerate(self.correct_answers) if ans is None]
        if not changeable_indices:
            logging.info("No questions left to change (all confirmed)")
            return False, []

        q_idx = random.choice(changeable_indices)
        current_option = self.best_answers[q_idx]
        possible_options = [opt for opt in range(1, self.num_options + 1) if opt != current_option]
        if not possible_options:
            logging.debug(f"Q{q_idx + 1}: No alternative options available")
            return False, []

        new_option = random.choice(possible_options)
        self.best_answers[q_idx] = new_option
        logging.info(f"Forced random change: Q{q_idx + 1} changed from {current_option} to {new_option} 🔄")
        self.save_memory()
        return True, [(q_idx, current_option, new_option)]

    def log_summary_report(self, attempt_num: int, changed_questions: List, failed_options: List):
        """Log a comprehensive summary report for the attempt."""
        elapsed_time = time.time() - self.start_time
        minutes, seconds = divmod(elapsed_time, 60)
        confirmed_count = sum(1 for ans in self.correct_answers if ans is not None)
        confirmed_percentage = (confirmed_count / self.num_questions) * 100
        unknown_count = self.num_questions - confirmed_count

        logging.info(f"\n=== Summary Report for Attempt {attempt_num} ===")
        logging.info(f"Attempt Number & Score:")
        logging.info(f"  - Attempt: {attempt_num}")
        logging.info(f"  - Score: {self.best_score}/{self.num_questions}")

        logging.info(f"\nChanged Questions This Attempt:")
        if changed_questions:
            for q_idx, prev_option, new_option in changed_questions:
                logging.info(f"  - Q{q_idx + 1}: Changed from option {prev_option} to {new_option}")
        else:
            logging.info(f"  - No questions changed")

        logging.info(f"\nConfirmed Correct Answers So Far:")
        logging.info(f"  - Count: {confirmed_count}/{self.num_questions} ({confirmed_percentage:.1f}%)")
        confirmed_list = [f"Q{i + 1}: {ans}" for i, ans in enumerate(self.correct_answers) if ans is not None]
        if confirmed_list:
            logging.info(f"  - Confirmed answers: {', '.join(confirmed_list)}")
        else:
            logging.info(f"  - No answers confirmed yet")

        logging.info(f"\nFailed Answers Tried This Attempt:")
        if failed_options:
            for q_idx, option in failed_options:
                logging.info(f"  - Q{q_idx + 1}: Option {option} rejected (score={self.memory[q_idx]['options'].get(option, 'N/A')})")
        else:
            logging.info(f"  - No failed options this attempt")

        logging.info(f"\nOverall Progress Summary:")
        logging.info(f"  - Confirmed answers: {confirmed_count}/{self.num_questions}")
        logging.info(f"  - Unknown questions left: {unknown_count}")
        logging.info(f"  - Best score so far: {self.best_score}/{self.num_questions}")
        logging.info(f"  - Elapsed time: {int(minutes)}m {int(seconds)}s")
        logging.info(f"  - Total trials: {self.total_trials}")
        logging.info(f"============================\n")

    def solve(self, exam_callback, page) -> List[int]:
        """Solve the exam using systematic trials with plateau detection."""
        logging.info("Starting exam solver")
        self.exam_callback = exam_callback

        # Load questions
        questions_data = self.retrieve_questions(page)

        # Initialize with AI answers only if memory is empty
        if not any(self.memory[i]["options"] for i in range(self.num_questions)):
            logging.info("No memory found, initializing with AI answers")
            self.best_answers = self.ai_debate_answers(questions_data)
            for q_idx, option in enumerate(self.best_answers):
                self.memory[q_idx]["best_option"] = option
            # Test initial AI answers
            score = self.try_option_for_question(0, self.best_answers[0], exam_callback)
            if score > 0:
                self.memory[0]["options"][self.best_answers[0]] = score
                self.best_score = score
                logging.info(f"Initial AI answers score: {score}/{self.num_questions}")
                self.save_memory()

        attempt_num = 1
        plateau_counter = 0
        MAX_PLATEAU_ATTEMPTS = 5
        
        while self.best_score < self.num_questions:
            if all(self.correct_answers):
                logging.info("All answers confirmed, stopping early")
                break

            # Reset exam if stuck at plateau
            if plateau_counter >= MAX_PLATEAU_ATTEMPTS:
                logging.warning(f"Plateau detected at {self.best_score}/{self.num_questions} for {MAX_PLATEAU_ATTEMPTS} attempts")
                if hasattr(exam_callback, 'reset_exam'):
                    logging.info("Resetting exam state...")
                    exam_callback.reset_exam()
                    time.sleep(3)
                    # Reload questions after reset
                    questions_data = self.retrieve_questions(page)
                    plateau_counter = 0
                else:
                    logging.warning("Reset capability not available in callback")

            logging.info(f"Attempt {attempt_num}: Starting systematic trial phase")
            improved = self.systematic_trial_phase(exam_callback, attempt_num)
            
            if self.best_score == self.num_questions:
                logging.info("Perfect score achieved!")
                break

            if improved:
                plateau_counter = 0  # Reset plateau counter on improvement
            else:
                plateau_counter += 1
                logging.info(f"No improvement this attempt (plateau counter: {plateau_counter}/{MAX_PLATEAU_ATTEMPTS})")

            if not improved:
                logging.info("No improvements from systematic trials, attempting random forced change")
                success, changed_questions = self.random_forced_change()
                if success:
                    # Test the random change
                    q_idx, prev_option, new_option = changed_questions[0]
                    score = self.try_option_for_question(q_idx, new_option, exam_callback)
                    
                    if score > 0:
                        self.memory[q_idx]["options"][new_option] = score
                        if score > self.best_score:
                            self.best_score = score
                            self.memory[q_idx]["best_score"] = score
                            self.memory[q_idx]["best_option"] = new_option
                            logging.info(f"Random change improved score to {score}/{self.num_questions} 🌟")
                            plateau_counter = 0
                            if score == self.num_questions:
                                self.correct_answers[q_idx] = new_option
                                logging.info(f"Q{q_idx + 1}: Confirmed correct answer {new_option} ✅")
                        self.log_summary_report(attempt_num, changed_questions, 
                                                [(q_idx, new_option)] if score <= self.best_score else [])
                        self.save_memory()
                else:
                    logging.warning("No changes possible, stopping solver")
                    break

            attempt_num += 1

        # Fill remaining unknown answers with best guesses
        for i in range(self.num_questions):
            if self.correct_answers[i] is None:
                self.correct_answers[i] = self.memory[i]["best_option"]
                logging.debug(f"Q{i + 1}: Using best guess option {self.correct_answers[i]}")

        logging.info(f"Final answers: {self.correct_answers}, best score: {self.best_score}/{self.num_questions}")
        self.save_memory()
        return self.correct_answers