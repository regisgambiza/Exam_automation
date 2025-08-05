import json
import logging
import random
import time
from datetime import datetime
from typing import List, Dict, Set, Tuple, Optional
import math
import numpy as np
import os

class AdaptiveGreedyExamSolver:
    def __init__(self, num_questions: int = 30, num_options: int = 4, max_stuck_attempts: int = 10, exploration_rate: float = 0.1, max_changes_per_guess: int = 3, confidence_threshold: float = 0.9, log_mode: str = "overwrite"):
        self.num_questions = num_questions
        self.num_options = num_options
        self.max_stuck_attempts = max_stuck_attempts
        self.exploration_rate = exploration_rate
        self.max_changes_per_guess = max_changes_per_guess
        self.confidence_threshold = confidence_threshold
        self.best_score = 0
        self.best_answers = [1] * num_questions
        self.correct_answers = [None] * num_questions
        self.stuck_counter = 0
        self.tested_options: Dict[int, Set[int]] = {i: set() for i in range(num_questions)}
        self.option_scores: Dict[int, Dict[int, float]] = {i: {opt: 1.0 for opt in range(1, num_options + 1)} for i in range(num_questions)}
        self.attempts: List[Dict[str, any]] = []
        self.start_time = time.time()
        self.guess_history: Set[str] = set()
        self.test_mode = False
        self.clusters: List[List[int]] = []
        self.log_mode = log_mode
        self.state_file = "solver_state.json"
        self.load_state()
        logging.debug(f"Initialized solver: {num_questions} questions, {num_options} options, max_stuck_attempts={max_stuck_attempts}, exploration_rate={exploration_rate}, max_changes_per_guess={max_changes_per_guess}, confidence_threshold={confidence_threshold}, log_mode={log_mode}")

    def set_test_mode(self, correct_answers: List[int]) -> None:
        self.test_mode = True
        self.test_correct_answers = correct_answers
        logging.info(f"Test mode enabled with correct answers: {correct_answers}")

    def load_state(self) -> None:
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, "r") as f:
                    state = json.load(f)
                self.correct_answers = state.get("correct_answers", [None] * self.num_questions)
                self.tested_options = {int(k): set(v) for k, v in state.get("tested_options", {}).items()}
                self.attempts = state.get("attempts", [])[-10:]
                self.best_score = state.get("last_score", 0)
                self.best_answers = state.get("best_answers", [1] * self.num_questions)
                self.guess_history = set(state.get("guess_history", []))
                self.option_scores = {int(k): {int(opt): score for opt, score in v.items()} for k, v in state.get("option_scores", {}).items()}
                self.stuck_counter = state.get("stuck_counter", 0)
                logging.info(f"Loaded state from {self.state_file}: best_score={self.best_score}, confirmed={sum(1 for ans in self.correct_answers if ans is not None)}/{self.num_questions}")
            except Exception as e:
                logging.error(f"Failed to load state from {self.state_file}: {e}")
                self._initialize_default_state()
        else:
            self._initialize_default_state()

    def _initialize_default_state(self) -> None:
        self.correct_answers = [None] * self.num_questions
        self.tested_options = {i: set() for i in range(self.num_questions)}
        self.option_scores = {i: {opt: 1.0 for opt in range(1, self.num_options + 1)} for i in range(self.num_questions)}
        self.attempts = []
        self.best_score = 0
        self.best_answers = [1] * self.num_questions
        self.guess_history = set()
        self.stuck_counter = 0
        logging.debug("Initialized default solver state.")

    def save_state(self) -> None:
        state = {
            "correct_answers": self.correct_answers,
            "tested_options": {str(i): list(self.tested_options[i]) for i in range(self.num_questions)},
            "attempts": self.attempts[-10:],
            "last_score": self.best_score,
            "best_answers": self.best_answers,
            "guess_history": list(self.guess_history)[-100:],
            "option_scores": {str(i): self.option_scores[i] for i in range(self.num_questions)},
            "stuck_counter": self.stuck_counter,
            "question_entropy": {str(i): self._compute_confidence(i)[1] for i in range(self.num_questions)}
        }
        try:
            with open(self.state_file, "w") as f:
                json.dump(state, f, indent=2)
            logging.debug(f"Saved state to {self.state_file}")
        except Exception as e:
            logging.error(f"Failed to save state to {self.state_file}: {e}")

    def _compute_confidence(self, question: int) -> Tuple[float, float]:
        scores = [self.option_scores[question][opt] for opt in range(1, self.num_options + 1)]
        total = sum(scores)
        if total == 0:
            return 0.0, 1.0
        probs = [s / total for s in scores]
        max_prob = max(probs)
        entropy = -sum(p * math.log2(p) for p in probs if p > 0)
        uncertainty = entropy / math.log2(self.num_options)
        return max_prob, uncertainty

    def _cluster_questions(self) -> None:
        uncertainties = [(i, self._compute_confidence(i)[1]) for i in range(self.num_questions) if self.correct_answers[i] is None]
        if not uncertainties:
            self.clusters = []
            return
        uncertainties.sort(key=lambda x: x[1], reverse=True)
        num_clusters = min(3, len(uncertainties))
        cluster_size = max(1, len(uncertainties) // num_clusters)
        self.clusters = [uncertainties[i:i + cluster_size] for i in range(0, len(uncertainties), cluster_size)]
        self.clusters = [[i for i, _ in cluster] for cluster in self.clusters]
        logging.debug(f"Clustered questions: {self.clusters}")

    def generate_guess(self) -> List[int]:
        logging.debug("Generating guess...")
        guess = self.best_answers.copy()
        unknown_indices = [i for i in range(self.num_questions) if self.correct_answers[i] is None]
        
        if not unknown_indices:
            logging.info("No unknown answers remain. Returning best answers.")
            return guess

        num_changes = random.randint(1, min(self.max_changes_per_guess, len(unknown_indices)))
        confidences = [(i, self._compute_confidence(i)) for i in unknown_indices]
        confidences.sort(key=lambda x: x[1][1], reverse=True)
        change_indices = [i for i, _ in confidences[:num_changes]]

        if random.random() < self.exploration_rate:
            logging.debug("Exploration mode: making random changes")
            for i in change_indices:
                options = list(range(1, self.num_options + 1))
                weights = [1.0 / (self.option_scores[i][opt] + 1e-10) for opt in options]
                guess[i] = random.choices(options, weights=weights, k=1)[0]
                self.tested_options[i].add(guess[i])
        else:
            for i in change_indices:
                options = [opt for opt in range(1, self.num_options + 1) if opt not in self.tested_options[i]]
                if not options:
                    logging.debug(f"All options tested for Q{i + 1}. Resetting tested options.")
                    self.tested_options[i].clear()
                    options = list(range(1, self.num_options + 1))
                weights = [self.option_scores[i][opt] + 1e-10 for opt in options]
                guess[i] = random.choices(options, weights=weights, k=1)[0]
                self.tested_options[i].add(guess[i])

        guess_str = str(guess)
        if guess_str in self.guess_history:
            logging.debug("Guess already tried. Generating new guess.")
            if len(self.guess_history) > 1000:  # Prevent infinite recursion
                logging.warning("Guess history too large. Clearing to avoid infinite loop.")
                self.guess_history.clear()
            return self.generate_guess()
        self.guess_history.add(guess_str)
        self.last_changed_indices = change_indices
        logging.debug(f"Generated guess: {guess}, changed indices: {change_indices}")
        return guess

    def _evaluate_guess(self, guess: List[int]) -> Tuple[str, Optional[str]]:
        for retry in range(3):
            try:
                if self.test_mode:
                    score = sum(1 for a, c in zip(guess, self.test_correct_answers) if a == c)
                    return "Done", f"{score}/{self.num_questions}"
                result_text, score_text = self.exam_callback(guess)
                if not score_text or '/' not in score_text:
                    raise ValueError(f"Invalid score text: {score_text}")
                score = int(score_text.split('/')[0])
                if score < 0 or score > self.num_questions:
                    raise ValueError(f"Invalid score value: {score}")
                return result_text, score_text
            except Exception as e:
                logging.warning(f"exam_callback failed for {guess} (retry {retry + 1}/3): {e}")
                if retry == 2:
                    return "Error", None
                time.sleep(2 ** retry)
        return "Error", None

    def update_with_score(self, answers: List[int], score: int, changed_indices: List[int]) -> None:
        self.attempts.append({"answers": answers.copy(), "score": score, "changed_indices": changed_indices})
        if score > self.best_score:
            logging.info(f"New best score: {score}/{self.num_questions}, updating best_answers: {answers}, changed: {changed_indices}")
            self.best_score = score
            self.best_answers = answers.copy()
            self.stuck_counter = 0
            for i in changed_indices:
                if self.correct_answers[i] is None:
                    self.option_scores[i][answers[i]] += 1.0
        else:
            self.stuck_counter += 1
            for i in changed_indices:
                if self.correct_answers[i] is None:
                    self.option_scores[i][answers[i]] = max(0, self.option_scores[i][answers[i]] - 0.2)
            logging.debug(f"Score {score}/{self.num_questions} <= best_score {self.best_score}/{self.num_questions}, stuck_counter: {self.stuck_counter}")
        self.save_state()

    def mark_correct(self, score: int, answers: List[int], changed_indices: List[int]) -> None:
        if len(self.attempts) < 2:
            logging.debug("Not enough attempts to mark correct answers.")
            return
        prev_score = self.attempts[-2]["score"]
        prev_answers = self.attempts[-2]["answers"]
        logging.debug(f"Comparing scores: current={score}, previous={prev_score}")
        if score > prev_score:
            if len(changed_indices) == 1:
                i = changed_indices[0]
                if self.correct_answers[i] is None:
                    val = answers[i]
                    self.correct_answers[i] = val
                    logging.info(f"Q{i + 1}: Marked {val} as correct (score improved from {prev_score} to {score})")
                    self.tested_options[i].clear()
                    self.tested_options[i].add(val)
                    self.option_scores[i][val] += 2.0
            elif score - prev_score <= len(changed_indices):
                logging.debug(f"Multiple changes {changed_indices}, score diff {score - prev_score}. Probing to confirm.")
                for i in changed_indices:
                    if self.correct_answers[i] is None:
                        new_guess = self.best_answers.copy()
                        new_guess[i] = answers[i]
                        result_text, score_text = self._evaluate_guess(new_guess)
                        if score_text:
                            score_new = int(score_text.split('/')[0])
                            if score_new > self.best_score:
                                self.correct_answers[i] = answers[i]
                                logging.info(f"Q{i + 1}: Confirmed {answers[i]} as correct via probing")
                                self.tested_options[i].clear()
                                self.tested_options[i].add(answers[i])
                                self.option_scores[i][answers[i]] += 2.0
                                self.update_with_score(new_guess, score_new, [i])
        self.save_state()

    def _should_stop_early(self) -> bool:
        confirmed = sum(1 for ans in self.correct_answers if ans is not None)
        confidences = [self._compute_confidence(i)[0] for i in range(self.num_questions) if self.correct_answers[i] is None]
        high_confidence = all(c >= self.confidence_threshold for c in confidences) if confidences else True
        stalled = self.stuck_counter > self.max_stuck_attempts * 2 and self.best_score == self.attempts[-1]["score"] if self.attempts else False
        logging.debug(f"Early stopping check: confirmed={confirmed}/{self.num_questions}, high_confidence={high_confidence}, stalled={stalled}")
        return confirmed >= self.num_questions * 0.9 or (high_confidence and stalled)

    def fill_remaining_with_best(self) -> None:
        for i in range(self.num_questions):
            if self.correct_answers[i] is None:
                best_option = max(range(1, self.num_options + 1), key=lambda opt: self.option_scores[i][opt])
                self.correct_answers[i] = best_option
                logging.debug(f"Q{i + 1}: Filled with best option {best_option} (score: {self.option_scores[i][best_option]})")
        self.save_state()

    def export_log(self) -> None:
        confirmed = [i + 1 for i, ans in enumerate(self.correct_answers) if ans is not None]
        guessed = [i + 1 for i, ans in enumerate(self.correct_answers) if ans is None]
        last_attempt = self.attempts[-1] if self.attempts else {"score": 0, "changed_indices": []}
        summary = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "total_attempts": len(self.attempts),
            "time_elapsed_seconds": round(time.time() - self.start_time, 2),
            "best_score": self.best_score,
            "confirmed_questions": confirmed,
            "guessed_questions": guessed,
            "unique_guesses": len(self.guess_history),
            "last_changed_indices": last_attempt.get("changed_indices", []),
            "clusters": self.clusters
        }
        log_entry = f"Summary: {json.dumps(summary, indent=2)}\n"
        try:
            mode = "w" if self.log_mode == "overwrite" else "a"
            with open("solver.log", mode) as f:
                if mode == "a" and os.path.getsize("solver.log") > 0:
                    f.write("\n---\n")
                f.write(log_entry)
            logging.debug(f"Log written to solver.log in {self.log_mode} mode: {summary}")
        except Exception as e:
            logging.error(f"Failed to write to solver.log: {e}")

    def solve(self, exam_callback) -> List[int]:
        self.exam_callback = exam_callback
        attempt_num = len(self.attempts) + 1
        temperature = 1.0
        cooling_rate = 0.95

        while self.best_score < self.num_questions and attempt_num <= 1000:
            if all(self.correct_answers):
                logging.info("All correct answers identified. Terminating early.")
                break
            if self._should_stop_early():
                logging.info("Early stopping triggered.")
                break
            logging.info(f"Attempt {attempt_num}, temperature={temperature:.3f}")
            
            guesses = [self.generate_guess() for _ in range(min(3, len([i for i in range(self.num_questions) if self.correct_answers[i] is None])))]
            guesses = [g for g in guesses if str(g) not in self.guess_history]
            if not guesses:
                logging.debug("No new unique guesses generated. Forcing new guess.")
                guesses = [self.generate_guess()]

            for guess in guesses:
                try:
                    result_text, score_text = self._evaluate_guess(guess)
                    if score_text is None:
                        logging.warning(f"Invalid score for guess {guess}. Skipping.")
                        continue
                    score = int(score_text.split('/')[0])
                    logging.debug(f"Evaluated guess {guess}: score={score}/{self.num_questions}")
                    changed_indices = [i for i, (a, b) in enumerate(zip(guess, self.best_answers)) if a != b]
                    self.update_with_score(guess, score, changed_indices)
                    self.mark_correct(score, guess, changed_indices)
                except Exception as e:
                    logging.warning(f"Error evaluating guess {guess}: {e}")

            self._cluster_questions()
            self.export_log()

            if self.best_score == self.num_questions:
                logging.info("Perfect score achieved!")
                break

            if self.stuck_counter >= self.max_stuck_attempts and self.clusters:
                logging.info(f"Stuck for {self.stuck_counter} attempts. Brute-forcing clusters: {self.clusters}")
                for cluster in self.clusters:
                    if not cluster:
                        continue
                    logging.info(f"Brute-forcing cluster: {cluster}")
                    for opt_combination in np.ndindex(*[self.num_options] * min(3, len(cluster))):  # Limit cluster size
                        new_guess = self.best_answers.copy()
                        for idx, opt in zip(cluster[:3], opt_combination):
                            option = opt + 1
                            if option in self.tested_options[idx]:
                                continue
                            new_guess[idx] = option
                            self.tested_options[idx].add(option)
                        guess_str = str(new_guess)
                        if guess_str in self.guess_history:
                            continue
                        self.guess_history.add(guess_str)
                        logging.debug(f"Testing cluster {cluster} with {new_guess}")
                        result_text, score_text = self._evaluate_guess(new_guess)
                        if score_text:
                            score = int(score_text.split('/')[0])
                            logging.debug(f"Cluster brute-force result: score={score}/{self.num_questions}")
                            self.update_with_score(new_guess, score, cluster[:3])
                            if score > self.best_score:
                                for idx, opt in zip(cluster[:3], opt_combination):
                                    if self.correct_answers[idx] is None:
                                        self.correct_answers[idx] = opt + 1
                                        logging.info(f"Q{idx + 1}: Confirmed {opt + 1} as correct via cluster brute-force")
                                        self.tested_options[idx].clear()
                                        self.tested_options[idx].add(opt + 1)
                                        self.option_scores[idx][opt + 1] += 2.0
                                break
                    self.export_log()
                self.stuck_counter = 0

            temperature *= cooling_rate
            attempt_num += 1

        self.fill_remaining_with_best()
        self.export_log()
        logging.info(f"Final answers: {self.correct_answers}")
        return self.correct_answers
