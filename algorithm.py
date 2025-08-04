import json
import logging
import random
from datetime import datetime

class AdaptiveGreedyExamSolver:
    def __init__(self, num_questions=30, num_options=4, max_stuck_attempts=10):
        self.num_questions = num_questions
        self.num_options = num_options
        self.correct_answers = [None] * num_questions
        self.attempts = []  # List of (answers, score)
        self.best_score = 0
        self.best_answers = [1] * num_questions
        self.last_changed_index = None
        self.last_changed_value = None
        self.max_stuck_attempts = max_stuck_attempts
        self.stuck_counter = 0
        self.tested_options = {i: set() for i in range(num_questions)}  # Track tested options per question

    def generate_guess(self):
        """
        Generate a new guess by selecting an untested option for an unknown question.
        """
        guess = self.best_answers[:]
        unknown_indices = [i for i in range(self.num_questions) if self.correct_answers[i] is None]

        if not unknown_indices:
            logging.debug("No unknown answers remain. Returning current best answers.")
            return guess

        self.last_changed_index = random.choice(unknown_indices)
        current_value = guess[self.last_changed_index]
        untested_options = [x for x in range(1, self.num_options + 1) if x not in self.tested_options[self.last_changed_index]]
        
        if untested_options:
            self.last_changed_value = untested_options[0]
        else:
            choices = [x for x in range(1, self.num_options + 1) if x != current_value]
            self.last_changed_value = random.choice(choices)
            self.tested_options[self.last_changed_index].clear()
        
        guess[self.last_changed_index] = self.last_changed_value
        self.tested_options[self.last_changed_index].add(self.last_changed_value)
        logging.debug(f"Generated guess by changing Q{self.last_changed_index + 1} to {self.last_changed_value}. Tested options: {self.tested_options[self.last_changed_index]}")
        return guess

    def update_with_score(self, answers, score):
        self.attempts.append((answers[:], score))
        if score >= self.best_score:
            self.best_score = score
            self.best_answers = answers[:]
            self.stuck_counter = 0
        else:
            self.stuck_counter += 1
        logging.info(f"Score: {score}/30 | Best so far: {self.best_score}/30 | Stuck count: {self.stuck_counter}")

    def mark_correct(self, score):
        if len(self.attempts) < 2:
            return
        prev_score = self.attempts[-2][1]
        if score > prev_score:
            i = self.last_changed_index
            val = self.last_changed_value
            if self.correct_answers[i] is None:
                self.correct_answers[i] = val
                logging.debug(f"Q{i + 1}: Marked {val} as correct")
                self.tested_options[i].clear()

    def fill_remaining_with_best(self):
        for i in range(self.num_questions):
            if self.correct_answers[i] is None:
                self.correct_answers[i] = self.best_answers[i]

    def export_log(self, filename=None):
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"solver_log_{timestamp}.json"
        log_data = {
            "attempts": [{"answers": a, "score": s} for a, s in self.attempts],
            "best_score": self.best_score,
            "best_answers": self.best_answers,
            "correct_answers": self.correct_answers,
            "stuck_counter": self.stuck_counter,
            "tested_options": {str(i): list(self.tested_options[i]) for i in range(self.num_questions)}
        }
        with open(filename, "w") as f:
            json.dump(log_data, f, indent=2)
        logging.info(f"Solver log exported to {filename}")

    def solve(self, exam_callback):
        attempt_num = 1
        while self.best_score < self.num_questions:
            if all(self.correct_answers):
                logging.info("All correct answers identified. Terminating early.")
                break
            logging.info(f"Attempt {attempt_num}")
            answers = self.generate_guess()
            result_text, score_text = exam_callback(answers)
            logging.debug(f"Received from exam_callback: result_text={result_text}, score_text={score_text}")

            if not score_text or '/' not in score_text:
                logging.warning(f"Invalid score text: {score_text}. Skipping.")
                self.export_log()
                continue

            try:
                score = int(score_text.split('/')[0])
                logging.debug(f"Parsed score: {score}")
                if score < 0 or score > self.num_questions:
                    logging.warning(f"Invalid score value {score}. Skipping.")
                    self.export_log()
                    continue
            except ValueError:
                logging.warning(f"Failed to parse score_text: {score_text}. Skipping.")
                self.export_log()
                continue

            self.update_with_score(answers, score)
            self.mark_correct(score)
            self.export_log()

            if self.best_score == self.num_questions:
                logging.info("Perfect score achieved!")
                break

            if self.stuck_counter >= self.max_stuck_attempts:
                logging.warning("Stuck too long. Resetting guesses for remaining unknowns.")
                unknown_indices = [i for i in range(self.num_questions) if self.correct_answers[i] is None]
                max_questions_to_brute_force = min(2, len(unknown_indices))
                for i in unknown_indices[:max_questions_to_brute_force]:
                    for opt in range(1, self.num_options + 1):
                        new_guess = self.best_answers[:]
                        new_guess[i] = opt
                        self.tested_options[i].add(opt)
                        result_text, score_text = exam_callback(new_guess)
                        logging.debug(f"Brute-force: result_text={result_text}, score_text={score_text}")
                        try:
                            score = int(score_text.split('/')[0])
                            if score < 0 or score > self.num_questions:
                                logging.warning(f"Invalid score value {score}. Skipping.")
                                continue
                        except ValueError:
                            logging.warning(f"Failed to parse score_text in brute-force: {score_text}. Skipping.")
                            continue
                        self.update_with_score(new_guess, score)
                        if score > self.best_score:
                            self.correct_answers[i] = opt
                            logging.info(f"Recovered Q{i+1} = {opt} via brute force")
                            self.tested_options[i].clear()
                            break
                    self.export_log()
                self.stuck_counter = 0

            attempt_num += 1

        self.fill_remaining_with_best()
        self.export_log()
        logging.info(f"Final answers: {self.correct_answers}")
        return self.correct_answers
