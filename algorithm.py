import json
import logging
import random
import time
from typing import Dict, List
import os
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
        q_p.first.wait_for(state="visible", timeout=10000)  # Increased timeout
        question_text = "\n".join(q_p.all_inner_texts())
        choices = page.locator("div.choice p").all_inner_texts()
        logging.debug(f"Found question with {len(choices)} choices")
        return question_text, choices
    except Exception as e:
        logging.error(f"Failed to extract question and choices: {e}")
        return None, []

class SimpleGreedyExamSolver:
    def __init__(self, num_questions: int = 30, num_options: int = 4):
        if num_questions <= 0 or num_options <= 0:
            raise ValueError("num_questions and num_options must be positive integers")
        self.num_questions = num_questions
        self.num_options = num_options
        self.best_score = 0
        self.best_answers = [1] * num_questions  # All initial answers are option 1
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
        """Load memory and progress from disk."""
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
        """Reset solver to initial state."""
        self.best_score = 0
        self.best_answers = [1] * self.num_questions  # Fixed: use self.num_questions
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
                    try:
                        page.get_by_role('button', name='Next >').click(timeout=2000)  # Increased timeout
                        page.wait_for_timeout(1000)  # Increased wait
                    except Exception as e:
                        logging.error(f"Failed to click 'Next >' for Q{q_idx + 1}: {e}")
                        break
            with open(self.questions_file, "w") as f:
                json.dump(questions_data, f, indent=2)
            logging.info(f"Saved {len(questions_data)} questions to {self.questions_file}")
        except Exception as e:
            logging.error(f"Failed to retrieve questions: {e}")
        return questions_data

    def try_option_for_question(self, question_idx: int, option: int, exam_callback) -> int:
        """Try a specific option with robust error handling and throttling."""
        self.total_trials += 1
        guess = [1] * self.num_questions  # Always use all 1s except for the tested question
        guess[question_idx] = option
        
        # Anti-flood throttling (progressive delay)
        delay_seconds = min(5.0, 0.5 + (0.1 * self.total_trials))
        logging.debug(f"Delaying {delay_seconds:.1f}s before attempt #{self.total_trials}")
        time.sleep(delay_seconds)
        
        max_score_attempts = 3  # Retry score extraction up to 3 times
        for attempt in range(max_score_attempts):
            try:
                logging.debug(f"Trying Q{question_idx + 1} with option {option}, attempt {attempt + 1}/{max_score_attempts}")
                result_text, score_text = exam_callback(guess)
                
                # Robust score parsing
                if score_text is None or result_text is None:
                    logging.warning(f"No score or result text returned on attempt {attempt + 1}")
                    if attempt < max_score_attempts - 1:
                        logging.info("Retrying score extraction after 5s")
                        time.sleep(5)
                        continue
                    return 0
                
                # Try standard "X/Y" format
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
                        logging.error(f"Unparseable score: '{score_text}' on attempt {attempt + 1}")
                        if attempt < max_score_attempts - 1:
                            logging.info("Retrying score extraction after 5s")
                            time.sleep(5)
                            continue
                        return 0
                
                # Validate score range
                if not (0 <= score <= self.num_questions):
                    logging.warning(f"Illegal score value {score} from '{score_text}' on attempt {attempt + 1}")
                    if attempt < max_score_attempts - 1:
                        logging.info("Retrying score extraction after 5s")
                        time.sleep(5)
                        continue
                    return 0
                
                logging.info(f"Q{question_idx + 1}, option {option} scored {score}/{self.num_questions}")
                return score
                
            except Exception as e:
                logging.error(f"Evaluation crashed for Q{question_idx+1}, option {option}, attempt {attempt + 1}: {str(e)}")
                if attempt < max_score_attempts - 1:
                    logging.info("Retrying submission after 5s")
                    time.sleep(5)
                    continue
                return 0

        logging.error(f"Failed to get valid score for Q{question_idx+1}, option {option} after {max_score_attempts} attempts")
        return 0

    def systematic_trial_phase(self, exam_callback, attempt_num: int) -> bool:
        """Try options 2, 3, and 4 for each question, logging summary after each submission."""
        improved = False
        changed_questions = []
        failed_options = []
        baseline_score = self.best_score  # Fixed baseline score from initial submission
        logging.info(f"Starting systematic trial phase with baseline score: {baseline_score}/{self.num_questions}")

        for q_idx in range(self.num_questions):
            if self.correct_answers[q_idx] is not None:
                logging.debug(f"Q{q_idx + 1} already confirmed as option {self.correct_answers[q_idx]} ✅")
                continue

            # Test options 2, 3, and 4 only
            options_to_test = [2, 3, 4]
            logging.info(f"Systematic trial for Q{q_idx + 1}: Testing options {options_to_test}")

            for option in options_to_test:
                # Skip if option already tested
                if option in self.memory[q_idx]["options"]:
                    logging.debug(f"Q{q_idx + 1}: Option {option} already tested, skipping")
                    continue

                score = self.try_option_for_question(q_idx, option, exam_callback)
                if score == 0:
                    logging.warning(f"Q{q_idx + 1}: Invalid score for option {option}, skipping")
                    self.log_summary_report(attempt_num, changed_questions, failed_options)
                    continue

                self.memory[q_idx]["options"][option] = score
                logging.info(f"Q{q_idx + 1}, option {option} scored {score}/{self.num_questions}")

                if score > baseline_score:
                    # Score increased: lock this option and move to next question
                    self.correct_answers[q_idx] = option
                    self.memory[q_idx]["best_option"] = option
                    self.memory[q_idx]["best_score"] = score
                    improved = True
                    changed_questions.append((q_idx, 1, option))  # Option 1 was baseline
                    logging.info(f"Q{q_idx + 1}: Locked option {option} (score increased to {score}) ✅")
                    self.log_summary_report(attempt_num, changed_questions, failed_options)
                    break
                elif score < baseline_score:
                    # Score decreased: lock option 1 and move to next question
                    self.correct_answers[q_idx] = 1
                    self.memory[q_idx]["best_option"] = 1
                    self.memory[q_idx]["best_score"] = baseline_score
                    failed_options.append((q_idx, option))
                    logging.info(f"Q{q_idx + 1}: Locked baseline option 1 (score decreased to {score}) ✅")
                    self.log_summary_report(attempt_num, changed_questions, failed_options)
                    break
                else:
                    # Score unchanged: mark option as incorrect and continue
                    failed_options.append((q_idx, option))
                    logging.debug(f"Q{q_idx + 1}: Option {option} score unchanged ({score})")
                    self.log_summary_report(attempt_num, changed_questions, failed_options)

                # Save memory after each test
                self.save_memory()

            # If all options tested and no score increase, lock option 1 by elimination
            tested_options = list(self.memory[q_idx]["options"].keys())
            if (set(tested_options).issuperset({2, 3, 4}) and 
                self.correct_answers[q_idx] is None):
                last_option = 1  # Default to option 1 if all others tested
                self.correct_answers[q_idx] = last_option
                self.memory[q_idx]["best_option"] = last_option
                # Test option 1 to confirm score
                score = self.try_option_for_question(q_idx, last_option, exam_callback)
                self.memory[q_idx]["options"][last_option] = score
                self.memory[q_idx]["best_score"] = score
                logging.info(f"Q{q_idx + 1}: Locked option 1 by elimination (score {score}) ✅")
                changed_questions.append((q_idx, 1, last_option))
                self.log_summary_report(attempt_num, changed_questions, failed_options)

            # Save memory after each question
            self.save_memory()

            # Check if perfect score achieved
            if baseline_score == self.num_questions:
                logging.info("Perfect score achieved! Stopping systematic trial.")
                break

        return improved

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
        """Solve the exam, ensuring all correct_answers are non-null and submitting final answers."""
        logging.info("Starting exam solver")
        self.exam_callback = exam_callback

        # Load questions
        try:
            questions_data = self.retrieve_questions(page)
            if not questions_data:
                logging.error("No questions retrieved, aborting solver")
                return self.correct_answers
        except Exception as e:
            logging.error(f"Failed to retrieve questions: {e}")
            return self.correct_answers

        # Initialize with option 1 for all answers
        self.best_answers = [1] * self.num_questions
        for q_idx in range(self.num_questions):
            self.memory[q_idx]["best_option"] = 1
        # Test initial answers to set baseline score
        try:
            score = self.try_option_for_question(0, 1, exam_callback)  # Uses all 1s
            if score > 0:
                self.memory[0]["options"][1] = score
                self.best_score = score  # Set baseline score, not updated later
                logging.info(f"Initial answers (all option 1) score: {score}/{self.num_questions}")
                self.log_summary_report(1, [], [])  # Log initial summary
            else:
                logging.warning("Invalid initial score, proceeding with baseline score 0")
            self.save_memory()
        except Exception as e:
            logging.error(f"Failed to test initial answers: {e}")
            self.save_memory()

        attempt_num = 1
        max_retries = 3  # Handle exam restarts and browser crashes
        retry_count = 0

        while any(ans is None for ans in self.correct_answers) and retry_count < max_retries:
            logging.info(f"Attempt {attempt_num}: Starting systematic trial phase (Retry {retry_count + 1}/{max_retries})")
            try:
                improved = self.systematic_trial_phase(exam_callback, attempt_num)
                
                if self.best_score == self.num_questions:
                    logging.info("Perfect score achieved!")
                    break

                if not improved:
                    logging.info("No improvements this attempt, checking for untested questions")
                    untested_questions = [i for i, ans in enumerate(self.correct_answers) if ans is None]
                    if not untested_questions:
                        logging.warning("No untested questions remain, but not all answers confirmed")
                        break
                
                attempt_num += 1
            except Exception as e:
                logging.error(f"Systematic trial phase failed: {e}")
                retry_count += 1
                if retry_count < max_retries:
                    logging.info("Restarting exam due to error or browser crash")
                    self.save_memory()
                    time.sleep(15)  # Increased wait before retry
                    # Reset page state if possible
                    try:
                        page.reload()
                        page.wait_for_load_state("networkidle", timeout=30000)
                    except Exception as reload_e:
                        logging.error(f"Failed to reload page: {reload_e}")
                else:
                    logging.error(f"Max retries ({max_retries}) reached, stopping solver")
                    break

        # Submit final correct answers
        if all(ans is not None for ans in self.correct_answers):
            logging.info(f"Submitting final correct answers: {self.correct_answers}")
            try:
                result_text, score_text = exam_callback(self.correct_answers)
                logging.info(f"Final submission result: {result_text}, score: {score_text}")
                if score_text and int(re.search(r'(\d+)', score_text).group(1)) == self.num_questions:
                    logging.info("Perfect score of 30/30 achieved! ✅")
                else:
                    logging.error(f"Final score not 30/30: {score_text}")
            except Exception as e:
                logging.error(f"Final submission failed: {e}")
        else:
            logging.error("Not all answers confirmed, cannot submit final answers")

        self.save_memory()
        return self.correct_answers