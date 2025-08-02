import json
import logging
import random


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

    def generate_guess(self):
        """
        Change only one unknown answer from the current best set.
        """
        guess = self.best_answers[:]
        unknown_indices = [i for i in range(self.num_questions) if self.correct_answers[i] is None]

        if not unknown_indices:
            return guess  # Nothing left to guess

        self.last_changed_index = random.choice(unknown_indices)
        old_value = guess[self.last_changed_index]
        choices = [x for x in range(1, self.num_options + 1) if x != old_value]
        self.last_changed_value = random.choice(choices)
        guess[self.last_changed_index] = self.last_changed_value

        logging.debug(f"Generated guess by changing Q{self.last_changed_index + 1} to {self.last_changed_value}")
        return guess

    def update_with_score(self, answers, score):
        self.attempts.append((answers[:], score))
        if score > self.best_score:
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

    def fill_remaining_with_best(self):
        for i in range(self.num_questions):
            if self.correct_answers[i] is None:
                self.correct_answers[i] = self.best_answers[i]

    def export_log(self, filename="solver_log.json"):
        with open(filename, "w") as f:
            json.dump({
                "attempts": [{"answers": a, "score": s} for a, s in self.attempts],
                "final_answers": self.correct_answers
            }, f, indent=2)
        logging.info(f"Solver log exported to {filename}")

    def solve(self, exam_callback):
        attempt_num = 1
        while self.best_score < self.num_questions:
            logging.info(f"Attempt {attempt_num}")
            answers = self.generate_guess()
            result_text, score_text = exam_callback(answers)

            if not score_text or '/' not in score_text:
                logging.warning("Invalid score text. Skipping.")
                continue

            score = int(score_text.split('/')[0])
            self.update_with_score(answers, score)
            self.mark_correct(score)

            if self.best_score == self.num_questions:
                logging.info("Perfect score achieved!")
                break

            if self.stuck_counter >= self.max_stuck_attempts:
                logging.warning("Stuck too long. Resetting guesses for remaining unknowns.")
                # Brute-force one unknown value
                for i in range(self.num_questions):
                    if self.correct_answers[i] is None:
                        for opt in range(1, self.num_options + 1):
                            new_guess = self.best_answers[:]
                            new_guess[i] = opt
                            _, score_text = exam_callback(new_guess)
                            score = int(score_text.split('/')[0])
                            self.update_with_score(new_guess, score)
                            if score > self.best_score:
                                self.correct_answers[i] = opt
                                logging.info(f"Recovered Q{i+1} = {opt} via brute force")
                                break
                        break
                self.stuck_counter = 0

            attempt_num += 1

        self.fill_remaining_with_best()
        self.export_log()
        logging.info(f"Final answers: {self.correct_answers}")
        return self.correct_answers


# === Example usage ===
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    def dummy_exam_callback(answers):
        correct = [1] * 30
        score = sum(1 for a, c in zip(answers, correct) if a == c)
        result = 'Pass' if score == 30 else 'Fail'
        return result, f"{score}/30"

    solver = AdaptiveGreedyExamSolver()
    solver.solve(dummy_exam_callback)
