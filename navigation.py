import os
from playwright.sync_api import Page
from tenacity import retry, stop_after_attempt, wait_fixed
import ollama
import time
import re
import logging  # Logging module imported

# Configure logging to capture detailed debug information
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

exam_page_url = None
selected_module_name = None  # Global declaration

def click_answer_by_index(page, answer_index):
    """Click the answer by index, restart exam if click fails."""
    logging.debug(f"Selecting answer option {answer_index}")
    try:
        locator = page.locator("div.col-12 button").nth(answer_index - 1)
        if wait_and_click(locator, f"answer option {answer_index}"):
            logging.info(f"Clicked answer option {answer_index}")
            return True
        else:
            raise Exception(f"Failed to click answer option {answer_index}")
    except Exception as e:
        logging.error(f"Failed to select answer option {answer_index}: {e}")
        restart_exam(page)  # Restart the exam on failure
        raise  # Re-raise to trigger retry in complete_exam

def wait_and_click(locator, description, max_retries=3, timeout=10000):
    """Helper function to wait for and click an element with retries."""
    for attempt in range(1, max_retries + 1):
        try:
            locator.wait_for(state="visible", timeout=timeout)
            locator.scroll_into_view_if_needed()
            locator.wait_for(state="attached", timeout=timeout)
            locator.click(timeout=timeout)
            logging.info(f"Successfully clicked {description}")
            return True
        except Exception as e:
            logging.warning(f"Attempt {attempt} failed for {description}: {e}")
            if attempt == max_retries:
                logging.error(f"Max retries reached for {description}")
                return False
            time.sleep(2)
    return False

def click_next(page):
    """Click the 'Next >' button."""
    logging.debug("Attempting to click 'Next >' button")
    try:
        page.get_by_role('button', name='Next >').click(timeout=500)
        logging.info("Clicked 'Next >' button")
        return True
    except Exception as e:
        logging.error(f"Failed to click 'Next >': {e}")
        logging.info("No 'Next >' button found")
        return False

def submit_exam(page):
    """Submit the exam and extract the result."""
    logging.debug("Initiating exam submission")
    logging.info("Submitting exam")
    try:
        page.get_by_role('button', name='Submit').click(timeout=1000)
        logging.info("Clicked 'Submit' button")
    except Exception as e:
        logging.error(f"Failed to click 'Submit': {e}")

    page.wait_for_timeout(2000)
    logging.debug("Waited 2s post-submission")

    submit_buttons = page.locator('button', has_text='Submit')
    count = submit_buttons.count()
    logging.debug(f"Found {count} submit buttons")

    if count >= 2:
        logging.debug("Clicking second 'Submit' button")
        try:
            submit_buttons.nth(1).click(timeout=1000)
            logging.info("Clicked second 'Submit' for confirmation")
            page.wait_for_timeout(2000)
        except Exception as e:
            logging.error(f"Failed to click second 'Submit': {e}")
    elif count == 1:
        logging.debug("Clicking single 'Submit' button")
        try:
            submit_buttons.nth(0).click(timeout=1000)
            logging.info("Clicked single 'Submit' button")
            page.wait_for_timeout(2000)
        except Exception as e:
            logging.error(f"Failed to click single 'Submit': {e}")
    else:
        logging.warning("No additional 'Submit' button found")

    try:
        from extract_result import extract_exam_result
        logging.debug("Extracting exam result")
        result = extract_exam_result(page)
        logging.info(f"Extracted result: {result}")
        return result
    except Exception as e:
        logging.error(f"Failed to extract result: {e}")
        try:
            restart_exam(page, retry_count=0, max_retries=3)
        except Exception as restart_error:
            logging.error(f"Failed to restart exam: {restart_error}")
        return None, None

def restart_exam(page, retry_count=0, max_retries=3):
    """Restart the exam after submission."""
    global selected_module_name
    exam_button_name = f"Final Exam {selected_module_name} batch"
    logging.debug(f"Restarting exam: {exam_button_name} (Retry {retry_count + 1}/{max_retries})")

    logging.info("Restarting exam")
    try:
        page.get_by_text('View Lesson').click()
        logging.info("Clicked 'View Lesson'")
    except Exception as e:
        logging.error(f"Failed to click 'View Lesson': {e}")

    try:
        page.get_by_text(exam_button_name, exact=False).click()
        logging.info(f"Clicked '{exam_button_name}'")
    except Exception as e:
        logging.error(f"Failed to click '{exam_button_name}': {e}")

    try:
        option = page.get_by_role('option', name=exam_button_name)
        option.get_by_role('paragraph').click()
        logging.info(f"Clicked paragraph in '{exam_button_name}'")
    except Exception as e:
        logging.error(f"Failed to click paragraph in '{exam_button_name}': {e}")

    # Modified section: Wait 30 seconds for page to load, then try clicking 'EXAM AGAIN' or 'START EXAM'
    max_attempts = 30  # Maximum number of retry attempts for button
    attempt = 1
    logging.info("Waiting 60 seconds for page to load before attempting to click exam button")
    time.sleep(60)  # 30-second wait for site to load
    while attempt <= max_attempts:
        try:
            logging.debug(f"Attempt {attempt} to click 'EXAM AGAIN' or 'START EXAM' button")
            # Try both possible button texts
            button_locator = page.locator('button:has-text("EXAM AGAIN"), button:has-text("START EXAM")')
            button_locator.wait_for(state="visible", timeout=15000)  # 15-second wait per attempt
            button_locator.scroll_into_view_if_needed()
            button_locator.click(timeout=1000)
            logging.info("Clicked 'EXAM AGAIN' or 'START EXAM'")
            break  # Exit loop on success
        except Exception as e:
            logging.warning(f"Attempt {attempt} failed to click 'EXAM AGAIN' or 'START EXAM': {e}")
            if attempt == max_attempts:
                logging.error(f"Failed to click exam button after {max_attempts} attempts")
                if retry_count < max_retries - 1:
                    logging.info(f"Retrying entire restart process (Retry {retry_count + 2}/{max_retries})")
                    time.sleep(5)  # Brief pause before retrying
                    restart_exam(page, retry_count=retry_count + 1, max_retries=max_retries)
                    return  # Exit after recursive call
                else:
                    logging.error(f"Max retries ({max_retries}) reached for restarting exam")
                    raise Exception(f"Failed to restart exam after {max_retries} attempts")
            time.sleep(3)  # 3-second delay between retries
            attempt += 1

    # Retry clicking 'EN' with longer timeout
    max_attempts = 5  # Fewer attempts for 'EN'
    attempt = 1
    while attempt <= max_attempts:
        try:
            logging.debug(f"Attempt {attempt} to click 'EN' button")
            button_locator = page.locator('text="EN"')
            button_locator.wait_for(state="visible", timeout=15000)  # 15-second wait per attempt
            button_locator.scroll_into_view_if_needed()
            button_locator.click(timeout=1000)
            logging.info("Clicked 'EN' button")
            time.sleep(3)  # Retain 3-second pause
            logging.debug("Waited 3s after 'EN' click")
            break  # Exit loop on success
        except Exception as e:
            logging.warning(f"Attempt {attempt} failed to click 'EN': {e}")
            if attempt == max_attempts:
                logging.error(f"Failed to click 'EN' after {max_attempts} attempts")
                raise Exception(f"Failed to click 'EN' after {max_attempts} attempts")
            time.sleep(3)  # 3-second delay between retries
            attempt += 1

def complete_exam(page, answers):
    """Complete the exam in the browser by selecting answers and submitting."""
    logging.debug(f"Starting exam with {len(answers)} answers")
    logging.info(f"Automating exam for {len(answers)} questions")
    for idx, answer_index in enumerate(answers):
        logging.info(f"Answering Q{idx+1}: Option {answer_index}")
        try:
            page.wait_for_selector('button, input[type="radio"], input[type="checkbox"]', timeout=10000)
            click_answer_by_index(page, answer_index)
            page.wait_for_timeout(500)  # Ensure selection registers
            if not click_next(page):
                logging.info("No 'Next >' button, submitting exam")
                result = submit_exam(page)
                if result[1] is None:
                    logging.error("Failed to extract score")
                    return None, None
                restart_exam(page)  # Restart after submission
                return result
        except Exception as e:
            logging.error(f"Failed to answer Q{idx+1}: {e}")
            return None, None
    logging.debug("All questions answered, submitting")
    try:
        result = submit_exam(page)
        if result[1] is None:
            logging.error("Failed to extract score")
            return None, None
        restart_exam(page)  # Restart after submission
        return result
    except Exception as e:
        logging.error(f"Failed to submit exam: {e}")
        return None, None

def navigate_to_actual_exam_page(page, selected_module_name, retry_count=0, max_retries=3):
    # Module-specific link clicks for modules 4, 5, 6
    global exam_page_url
    logging.debug(f"Navigating to exam page for {selected_module_name} (Retry {retry_count + 1}/{max_retries})")
    if selected_module_name == "Module 4":
        try:
            page.get_by_role('link', name='Module 4 - 002 (ENG)').locator('a').click()
            logging.info("Clicked Module 4 link")
        except Exception as e:
            logging.error(f"Failed to click Module 4 link: {e}")
    elif selected_module_name == "Module 5":
        try:
            page.get_by_role('link', name='Module 5 - 001 (ENG) Use of').locator('a').click()
            logging.info("Clicked Module 5 link")
        except Exception as e:
            logging.error(f"Failed to click Module 5 link: {e}")
    elif selected_module_name == "Module 6":
        try:
            page.get_by_role('link', name='Module 6 - 001 (ENG) Design').locator('a').click()
            logging.info("Clicked Module 6 link")
        except Exception as e:
            logging.error(f"Failed to click Module 6 link: {e}")

    logging.info(f"Accessing exam for {selected_module_name}")
    try:
        try:
            page.get_by_role('button', name='Start Classes').click()
            logging.info("Clicked 'Start Classes'")
        except Exception as e:
            logging.error(f"Failed to click 'Start Classes': {e}")

        try:
            page.get_by_text('View Lesson').click()
            logging.info("Clicked 'View Lesson'")
        except Exception as e:
            logging.error(f"Failed to click 'View Lesson': {e}")

        exam_button_name = f"Final Exam {selected_module_name} batch"
        try:
            page.get_by_role('button', name=exam_button_name).click()
            logging.info(f"Clicked '{exam_button_name}'")
        except Exception as e:
            logging.error(f"Failed to click '{exam_button_name}': {e}")

        try:
            option = page.get_by_role('option', name=exam_button_name)
            option.get_by_role('paragraph').click()
            logging.info(f"Clicked paragraph in '{exam_button_name}'")
        except Exception as e:
            logging.error(f"Failed to click paragraph in '{exam_button_name}': {e}")

        # Modified section: Wait 30 seconds for page to load, then try clicking 'EXAM AGAIN' or 'START EXAM'
        max_attempts = 30  # Maximum number of retry attempts for button
        attempt = 1
        logging.info("Waiting 60 seconds for page to load before attempting to click exam button")
        time.sleep(60)  # 30-second wait for site to load
        while attempt <= max_attempts:
            try:
                logging.debug(f"Attempt {attempt} to click 'EXAM AGAIN' or 'START EXAM' button")
                button_locator = page.locator('button:has-text("EXAM AGAIN"), button:has-text("START EXAM")')
                button_locator.wait_for(state="visible", timeout=15000)  # 15-second wait
                button_locator.scroll_into_view_if_needed()
                button_locator.click(timeout=1000)
                logging.info("Clicked 'EXAM AGAIN' or 'START EXAM'")
                break  # Exit loop on success
            except Exception as e:
                logging.warning(f"Attempt {attempt} failed to click 'EXAM AGAIN' or 'START EXAM': {e}")
                if attempt == max_attempts:
                    logging.error(f"Failed to click exam button after {max_attempts} attempts")
                    if retry_count < max_retries - 1:
                        logging.info(f"Retrying entire navigation process (Retry {retry_count + 2}/{max_retries})")
                        time.sleep(5)  # Brief pause before retrying
                        navigate_to_actual_exam_page(page, selected_module_name, retry_count=retry_count + 1, max_retries=max_retries)
                        return  # Exit after recursive call
                    else:
                        logging.error(f"Max retries ({max_retries}) reached for navigating to exam page")
                        raise Exception(f"Failed to navigate to exam page after {max_retries} attempts")
                time.sleep(3)  # Shorter delay between retries
                attempt += 1

        try:
            page.get_by_text("EN", exact=True).click()
            logging.info("Clicked 'EN' button")
            time.sleep(3)
            logging.debug("Waited 3s after 'EN' click")
        except Exception as e:
            logging.error(f"Failed to click 'EN': {e}")

        logging.debug("Waiting for exam page load")
        page.wait_for_load_state('load')
        exam_page_url = page.url
        logging.info(f"Exam page URL: {exam_page_url}")

        logging.info("Reached exam page")
        return exam_page_url
    except Exception as e:
        logging.error(f"Failed to navigate to exam page: {e}")
        return False

def select_module(page):
    """Extract available modules, display them, and prompt user to select one."""
    global selected_module_name
    logging.debug("Prompting module selection")
    modules = [f"Module {i}" for i in range(1, 8)]
    logging.debug(f"Modules: {modules}")
    print("Available modules:")
    for idx, name in enumerate(modules, 1):
        print(f"{idx}: {name}")
    while True:
        try:
            choice = int(input("Enter the number of the module you want to use: ")) - 1
            logging.debug(f"Selected module index: {choice + 1}")
            if 0 <= choice < len(modules):
                selected_module_name = modules[choice]
                print(f"You selected: {selected_module_name}")
                logging.info(f"Selected module: {selected_module_name}")
                try:
                    page.locator('div').filter(has_text=selected_module_name).nth(1).click()
                    logging.info(f"Clicked module: {selected_module_name}")
                    return selected_module_name
                except Exception as e:
                    logging.error(f"Failed to click module {selected_module_name}: {e}")
                    return None
            else:
                logging.debug(f"Invalid module index: {choice + 1}")
                print("Invalid selection. Please try again.")
        except ValueError as e:
            logging.error(f"Invalid module input: {e}")
            print("Please enter a valid number.")

def get_selector_suggestion(page, target_description):
    logging.debug(f"Requesting selector for: {target_description}")
    dom_html = page.content()
    logging.debug(f"DOM size: {len(dom_html)} chars")
    prompt = (
        f"Given this HTML:\n{dom_html}\n"
        f"Suggest a Playwright selector for: {target_description}. "
        "Return only the selector string"
    )
    logging.debug(f"Sending prompt to Ollama (size: {len(prompt)} chars)")
    try:
        response = ollama.chat(model="llama3.1:8b", messages=[{"role": "user", "content": prompt}])
        selector = response['message']['content'].strip().splitlines()[0]
        logging.debug(f"Ollama selector: {selector}")
        selector = selector.strip('`"\' ').split()[0]
        selector = selector.rstrip(';,.')
        logging.debug(f"Processed selector: {selector}")
        if selector in ('//', '', '.', '#', 'None', 'null'):
            logging.error(f"Invalid selector returned: {selector}")
            return None
        return selector
    except Exception as e:
        logging.error(f"Ollama selector request failed: {e}")
        return None

@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
def navigate_to_exam(page: Page, config: dict) -> bool:
    """Navigate to the exam page by performing login and clicking through menus."""
    logging.debug("Starting exam navigation")
    try:
        logging.info("Navigating to base URL")
        page.goto(config["BASE_URL"])
        logging.debug(f"Reached URL: {config['BASE_URL']}")
        
        logging.info("Checking for initial close button")
        try:
            page.wait_for_selector('button:has-text("close")', timeout=7000)
            page.click('button:has-text("close")')
            logging.info("Closed initial popup")
        except Exception as e:
            logging.error(f"Failed to close initial popup: {e}")
            try:
                page.wait_for_selector('button.close', timeout=7000)
                page.click('button.close')
                logging.info("Closed initial popup (fallback)")
            except Exception as e:
                logging.error(f"Failed fallback close button: {e}")
                logging.warning("No close button found")

        logging.info("Clicking Login link")
        try:
            page.wait_for_selector('a:has-text("Login")', timeout=7000)
            page.click('a:has-text("Login")')
            logging.info("Clicked Login link")
        except Exception as e:
            logging.error(f"Failed to click Login link: {e}")
            try:
                page.wait_for_selector('a.login', timeout=7000)
                page.click('a.login')
                logging.info("Clicked Login link (fallback)")
            except Exception as e:
                logging.error(f"Failed fallback Login link: {e}")
                logging.warning("No login link found")

        logging.info("Entering ID card number")
        try:
            page.wait_for_selector('input#input-201', timeout=7000)
            page.fill('input#input-201', config["EXAM_USERNAME"])
            logging.info("Entered ID card number")
        except Exception as e:
            logging.error(f"Failed to enter ID card: {e}")
            try:
                page.wait_for_selector('input[placeholder*="ID card number"]', timeout=7000)
                page.fill('input[placeholder*="ID card number"]', config["EXAM_USERNAME"])
                logging.info("Entered ID card number (fallback)")
            except Exception as e:
                logging.error(f"Failed fallback ID card input: {e}")
                logging.warning("No ID card input found")

        logging.info("Entering password")
        try:
            page.wait_for_selector('input#password', timeout=7000)
            page.fill('input#password', config["EXAM_PASSWORD"])
            logging.info("Entered password")
        except Exception as e:
            logging.error(f"Failed to enter password: {e}")
            try:
                page.wait_for_selector('input[type="password"]', timeout=7000)
                page.fill('input[type="password"]', config["EXAM_PASSWORD"])
                logging.info("Entered password (fallback)")
            except Exception as e:
                logging.error(f"Failed fallback password input: {e}")
                logging.warning("No password input found")

        logging.info("Clicking login button")
        try:
            page.wait_for_selector('button:has-text("login")', timeout=7000)
            page.click('button:has-text("login")')
            logging.info("Clicked login button")
        except Exception as e:
            logging.error(f"Failed to click login button: {e}")
            try:
                page.wait_for_selector('button.login', timeout=7000)
                page.click('button.login')
                logging.info("Clicked login button (fallback)")
            except Exception as e:
                logging.error(f"Failed fallback login button: {e}")
                logging.warning("No login button found")

        logging.info("Checking for post-login close button")
        try:
            page.wait_for_selector('button:has-text("close")', timeout=7000)
            page.click('button:has-text("close")')
            logging.info("Closed post-login popup")
        except Exception as e:
            logging.error(f"Failed to close post-login popup: {e}")
            try:
                page.wait_for_selector('button.close', timeout=7000)
                page.click('button.close')
                logging.info("Closed post-login popup (fallback)")
            except Exception as e:
                logging.error(f"Failed fallback post-login close: {e}")
                logging.warning("No post-login close button found")

        logging.info("Clicking My courses link")
        try:
            page.wait_for_selector('a:has-text("My courses")', timeout=7000)
            page.click('a:has-text("My courses")')
            logging.info("Clicked My courses link")
        except Exception as e:
            logging.error(f"Failed to click My courses link: {e}")
            try:
                page.wait_for_selector('a.my-courses', timeout=7000)
                page.click('a.my-courses')
                logging.info("Clicked My courses link (fallback)")
            except Exception as e:
                logging.error(f"Failed fallback My courses link: {e}")
                logging.warning("No My courses link found")

        logging.info("Navigation completed")
        return True
    except Exception as e:
        logging.error(f"Navigation failed: {e}")
        return False