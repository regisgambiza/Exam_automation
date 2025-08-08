import logging
from playwright.sync_api import sync_playwright, Error as PlaywrightError
from config import load_config
from navigation import navigate_to_exam, select_module, navigate_to_actual_exam_page, complete_exam
from extract_result import extract_exam_result
from algorithm import SimpleGreedyExamSolver

def run_exam_automation() -> None:
    logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s")
    logging.info("Loading configuration...")
    try:
        config = load_config()
    except ValueError as e:
        logging.error(f"Configuration error: {e}")
        return

    logging.info("Starting Playwright and launching Chrome browser...")
    with sync_playwright() as p:
        try:
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

            # Define callback for the solver
            def exam_callback(answers):
                logging.info(f"Submitting answers: {answers}")
                try:
                    result_text, score_text = complete_exam(page, answers)
                    logging.info(f"Raw result from complete_exam: ({result_text}, {score_text})")
                    if not score_text:
                        logging.error("Failed to extract score. Defaulting to 0/30.")
                        score_text = "0/30"
                    return result_text or "Done", score_text
                except PlaywrightError as e:
                    logging.error(f"Playwright error in exam callback (browser may be closed): {e}")
                    raise  # Re-raise to trigger cleanup in outer try-except
                except Exception as e:
                    logging.error(f"Error in exam callback: {e}")
                    return "Error", "0/30"

            # Navigate to exam page with error handling
            try:
                logging.debug(f"Navigating to exam page: {exam_page_url}")
                page.goto(exam_page_url, timeout=30000)
                page.wait_for_load_state('load', timeout=30000)
                logging.info("Successfully loaded exam page.")
            except PlaywrightError as e:
                logging.error(f"Playwright error navigating to exam page (browser may be closed): {e}")
                browser.close()
                return
            except Exception as e:
                logging.error(f"Failed to navigate to exam page {exam_page_url}: {e}")
                browser.close()
                return

            # Run the solver with error handling
            try:
                logging.info("Starting SimpleGreedyExamSolver...")
                # Updated line: Removed max_attempts
                solver = SimpleGreedyExamSolver(num_questions=30, num_options=4)
                final_answers = solver.solve(exam_callback, page)
                logging.info(f"Final correct answers: {final_answers}")
            except PlaywrightError as e:
                logging.error(f"Playwright error running solver (browser may be closed): {e}")
            except Exception as e:
                logging.error(f"Error running solver: {e}")
        except PlaywrightError as e:
            logging.error(f"Browser connection lost (likely closed manually): {e}")
        finally:
            logging.info("Closing browser...")
            try:
                browser.close()
            except Exception as e:
                logging.warning(f"Error closing browser (may already be closed): {e}")
            logging.info("Exam automation completed.")

if __name__ == "__main__":
    run_exam_automation()