import logging
from playwright.sync_api import sync_playwright
from config import load_config
from navigation import navigate_to_exam, select_module, navigate_to_actual_exam_page, complete_exam
from extract_result import extract_exam_result
from algorithm import AdaptiveGreedyExamSolver

def run_exam_automation() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    logging.info("Loading configuration...")
    try:
        config = load_config()
    except ValueError as e:
        logging.error(f"Configuration error: {e}")
        return

    logging.info("Starting Playwright and launching Chrome browser...")
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=False)
        page = browser.new_page()

        logging.info("Navigating to exam page and logging in...")
        success = navigate_to_exam(page, config)
        if not success:
            logging.error("Failed to navigate to exam page. Exiting.")
            browser.close()
            return

        logging.info("Successfully navigated to exam page. Asking user to select module...")
        selected_module_name = select_module(page)
        if not selected_module_name:
            logging.error("No module selected. Exiting.")
            browser.close()
            return

        logging.info(f"User selected module: {selected_module_name}. Navigating to actual exam page...")
        exam_page_url = navigate_to_actual_exam_page(page, selected_module_name)
        if not exam_page_url:
            logging.error("Failed to navigate to actual exam page.")
            browser.close()
            return

        logging.info(f"Exam page URL: {exam_page_url}")

        # Define callback for the AI solver
        def exam_callback(answers):
            logging.info(f"Submitting answers: {answers}")
            try:
                complete_exam(page, answers)
                logging.info("Extracting exam result...")
                result_text, score_text = extract_exam_result(page)
                if not score_text:
                    logging.error("Failed to extract score. Defaulting to 0/30.")
                    score_text = "0/30"
                logging.info(f"Exam result: {score_text}")
                
                

                return "Done", score_text
            except Exception as e:
                logging.error(f"Error in exam callback: {e}")
                return "Error", "0/30"
        page.goto(exam_page_url)
        # Run the AI exam solver
        logging.info("Starting AdaptiveGreedyExamSolver...")
        solver = AdaptiveGreedyExamSolver(num_questions=30, num_options=4, max_stuck_attempts=10)
        final_answers = solver.solve(exam_callback)

        logging.info(f"Final correct answers: {final_answers}")
        browser.close()

if __name__ == "__main__":
    run_exam_automation()