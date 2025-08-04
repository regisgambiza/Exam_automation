import json
import logging
import random
from datetime import datetime

class AdaptiveGreedyExamSolver:
    def __init__(self, num_questions=30, num_options=4, max_stuck_attempts=5):
        self.num_questions = num_questions
        self.num_options = num_options
        self.max_stuck_attempts = max_stuck_attempts
        self.best_score = 0
        self.best_answers = [1] * num_questions
        self.correct_answers = [None] * num_questions
        self.stuck_counter = 0
        self.tested_options = {i: set() for i in range(num_questions)}
        self.attempts = []
        self.last_changed_index = None
        self.last_changed_value = None
        logging.debug(f"Initialized solver: {num_questions} questions, {num_options} options, max_stuck_attempts={max_stuck_attempts}")

    def generate_guess(self):
        """Generate a new guess by changing one untested option for an unknown question."""
        logging.debug("Generating guess...")
        guess = self.best_answers.copy()
        unknown_indices = [i for i in range(self.num_questions) if self.correct_answers[i] is None]

        if not unknown_indices:
            logging.info("No unknown answers remain. Returning best answers.")
            return guess

        self.last_changed_index = random.choice(unknown_indices)
        untested_options = [opt for opt in range(1, self.num_options + 1) if opt not in self.tested_options[self.last_changed_index]]
        
        if untested_options:
            self.last_changed_value = random.choice(untested_options)
        else:
            logging.debug(f"All options tested for Q{self.last_changed_index + 1}. Resetting tested options.")
            self.tested_options[self.last_changed_index].clear()
            self.last_changed_value = random.choice(range(1, self.num_options + 1))
        
        guess[self.last_changed_index] = self.last_changed_value
        self.tested_options[self.last_changed_index].add(self.last_changed_value)
        logging.debug(f"Changed Q{self.last_changed_index + 1} to {self.last_changed_value}. Tested options: {self.tested_options[self.last_changed_index]}, Guess: {guess}")
        return guess

    def update_with_score(self, answers, score):
        """Update solver state with the score from the latest attempt."""
        self.attempts.append({"answers": answers.copy(), "score": score})
        if score > self.best_score:
            logging.info(f"New best score: {score}/{self.num_questions}, updating best_answers: {answers}")
            self.best_score = score
            self.best_answers = answers.copy()
            self.stuck_counter = 0
        else:
            self.stuck_counter += 1
            logging.debug(f"Score {score}/{self.num_questions} <= best_score {self.best_score}/{self.num_questions}, stuck_counter: {self.stuck_counter}")

    def mark_correct(self, score):
        """Mark an answer as correct if the score improves by exactly 1."""
        if len(self.attempts) < 2:
            logging.debug("Not enough attempts to mark correct answers.")
            return
        prev_score = self.attempts[-2]["score"]
        logging.debug(f"Comparing scores: current={score}, previous={prev_score}")
        if score == prev_score + 1 and self.last_changed_index is not None:
            i = self.last_changed_index
            val = self.last_changed_value
            if self.correct_answers[i] is None:
                self.correct_answers[i] = val
                logging.info(f"Q{i + 1}: Marked {val} as correct (score improved from {prev_score} to {score})")
                self.tested_options[i].clear()
                self.tested_options[i].add(val)
            else:
                logging.debug(f"Q{i + 1} already has correct answer: {self.correct_answers[i]}")
        else:
            logging.debug(f"No correct answer marked: score_diff={score - prev_score}, last_changed_index={self.last_changed_index}")

    def fill_remaining_with_best(self):
        """Fill any remaining unknown answers with the best known answers."""
        for i in range(self.num_questions):
            if self.correct_answers[i] is None:
                self.correct_answers[i] = self.best_answers[i]
                logging.debug(f"Q{i + 1}: Filled with best answer {self.best_answers[i]}")

    def export_log(self, filename=None):
        """Export solver state to a JSON log file."""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"solver_log_{timestamp}.json"
        log_data = {
            "attempts": self.attempts,
            "best_score": self.best_score,
            "best_answers": self.best_answers,
            "correct_answers": self.correct_answers,
            "stuck_counter": self.stuck_counter,
            "tested_options": {str(i): list(self.tested_options[i]) for i in range(self.num_questions)}
        }
        try:
            with open(filename, "w") as f:
                json.dump(log_data, f, indent=2)
            logging.info(f"Solver log exported to {filename}")
        except Exception as e:
            logging.error(f"Failed to export log: {e}")

    def solve(self, exam_callback):
        """Run the solver to find correct answers using a greedy approach with brute-force fallback."""
        attempt_num = 1
        while self.best_score < self.num_questions:
            if all(self.correct_answers):
                logging.info("All correct answers identified. Terminating early.")
                break
            logging.info(f"Attempt {attempt_num}")
            answers = self.generate_guess()
            try:
                result_text, score_text = exam_callback(answers)
                logging.debug(f"Received from exam_callback: result_text={result_text}, score_text={score_text}")
                if not score_text or '/' not in score_text:
                    logging.warning(f"Invalid score text: {score_text}. Retrying.")
                    self.export_log()
                    continue
                score = int(score_text.split('/')[0])
                logging.debug(f"Parsed score: {score}/{self.num_questions}")
                if score < 0 or score > self.num_questions:
                    logging.warning(f"Invalid score value {score}. Retrying.")
                    self.export_log()
                    continue
            except Exception as e:
                logging.warning(f"Failed to process exam_callback: {e}. Retrying.")
                self.export_log()
                continue

            self.update_with_score(answers, score)
            self.mark_correct(score)
            self.export_log()

            if self.best_score == self.num_questions:
                logging.info("Perfect score achieved!")
                break

            if self.stuck_counter >= self.max_stuck_attempts:
                logging.info(f"Stuck for {self.stuck_counter} attempts. Starting brute-force.")
                unknown_indices = [i for i in range(self.num_questions) if self.correct_answers[i] is None]
                max_questions_to_brute_force = min(2, len(unknown_indices))
                for i in random.sample(unknown_indices, max_questions_to_brute_force):
                    logging.info(f"Brute-forcing question {i + 1}")
                    for opt in range(1, self.num_options + 1):
                        if opt in self.tested_options[i]:
                            continue
                        new_guess = self.best_answers.copy()
                        new_guess[i] = opt
                        self.tested_options[i].add(opt)
                        logging.debug(f"Testing Q{i + 1} = {opt}: {new_guess}")
                        try:
                            result_text, score_text = exam_callback(new_guess)
                            score = int(score_text.split('/')[0])
                            logging.debug(f"Brute-force result: score={score}/{self.num_questions}")
                            self.update_with_score(new_guess, score)
                            if score > self.best_score:
                                logging.info(f"Found correct answer for Q{i + 1} = {opt}")
                                self.correct_answers[i] = opt
                                self.tested_options[i].clear()
                                self.tested_options[i].add(opt)
                                break
                        except Exception as e:
                            logging.warning(f"Brute-force error for Q{i + 1} = {opt}: {e}")
                            continue
                    self.export_log()
                self.stuck_counter = 0

            attempt_num += 1

        self.fill_remaining_with_best()
        self.export_log()
        logging.info(f"Final answers: {self.correct_answers}")
        return self.correct_answers