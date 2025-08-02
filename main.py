import logging
from playwright.sync_api import sync_playwright
from config import load_config
from navigation import navigate_to_exam, select_module, navigate_to_actual_exam_page, complete_exam
from browser import click_answer, click_next, submit_exam
from algorithm import load_question_data, select_answers, save_attempt_data, update_attempts
import threading
import time
import os

def run_ocr_in_background():
    """Run the OCR process in a separate thread (deactivated)."""
    logging.info("OCR process is deactivated.")
    return

def run_exam_automation() -> None:
    """Orchestrate the exam automation process, coordinating all modules."""
    logging.basicConfig(level=logging.INFO)
    logging.info("Loading configuration...")
    config = load_config()
    logging.info("Starting Playwright and launching Chrome browser...")
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=False)
        page = browser.new_page()
        logging.info("Navigating to exam page and logging in...")
        success = navigate_to_exam(page, config)
        if not success:
            logging.error("Failed to navigate to exam page. Exiting.")
            return
        logging.info("Successfully navigated to exam page. Asking user to select module...")
        selected_module_name = select_module(page)
        if selected_module_name is None:
            logging.error("No module selected. Exiting.")
            return
        logging.info("User selected a module. Navigating to actual exam page...")
        exam_page_url = navigate_to_actual_exam_page(page, selected_module_name)
        if not exam_page_url:
            logging.error("Failed to navigate to actual exam page.")
            return
        logging.info(f"Exam page URL: {exam_page_url}")
        # Complete the exam using the test_answers list
        from navigation import test_answers
        complete_exam(page, test_answers)
        

if __name__ == "__main__":
    run_exam_automation()