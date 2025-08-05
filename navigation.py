import logging
import os
from playwright.sync_api import Page
from tenacity import retry, stop_after_attempt, wait_fixed
import ollama
import time
import re  # Already present in your code, retained for consistency

# Configure logging to capture detailed debug information
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

exam_page_url = None
selected_module_name = None  # Global declaration

def click_answer_by_index(page, answer_index):
    """Click the answer by index, with AI fallback."""
    logging.debug(f"Selecting answer option {answer_index}")
    try:
        # Target the button within div.col-12, indexed from 0 (e.g., answer_index - 1)
        locator = page.locator("div.col-12 button").nth(answer_index - 1)
        if wait_and_click(locator, f"answer option {answer_index}"):
            logging.info(f"Clicked answer option {answer_index}")
            return True
        # AI fallback if direct match fails
        logging.debug(f"Trying AI fallback for option {answer_index}")
        selector = get_selector_suggestion(page, f"button for answer option {answer_index}")
        logging.debug(f"AI selector: {selector}")
        if selector:
            try:
                page.click(selector, timeout=5000)
                logging.info(f"Clicked answer option {answer_index} with AI selector: {selector}")
                return True
            except TimeoutError:
                logging.error(f"AI selector timeout for option {answer_index}: {selector}")
        logging.warning(f"No answer option {answer_index} found")
        return False  # Allow recovery in complete_exam
    except Exception as e:
        logging.error(f"Failed to select answer option {answer_index}: {e}")
        return False

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
    """Click the 'Next >' button, with AI fallback."""
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
        return None, None

# [Rest of the functions (restart_exam, complete_exam, navigate_to_actual_exam_page, select_module, get_selector_suggestion, navigate_to_exam) remain unchanged as per your provided code]

def restart_exam(page):
    """Restart the exam after submission."""
    global selected_module_name
    exam_button_name = f"Final Exam {selected_module_name} batch"
    logging.debug(f"Restarting exam: {exam_button_name}")

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

    # Fixed section: Handle paragraph click with robust selector and AI fallback
    try:
        option = page.get_by_role('option', name=exam_button_name)
        option.get_by_role('paragraph').click()
        logging.info(f"Clicked paragraph in '{exam_button_name}'")
    except Exception as e:
        logging.error(f"Failed to click paragraph in '{exam_button_name}': {e}")
        selector = get_selector_suggestion(page, f"paragraph in option for {exam_button_name}")
        logging.debug(f"AI selector for paragraph: {selector}")
        try:
            page.click(selector)
            logging.info(f"Clicked paragraph with AI selector: {selector}")
        except Exception as e:
            logging.error(f"AI selector failed for paragraph: {e}")

    try:
        page.get_by_role('button', name='Exam Again').click()
        logging.info("Clicked 'Exam Again'")
    except Exception as e:
        logging.error(f"Failed to click 'Exam Again': {e}")

    try:
        page.get_by_text("EN", exact=True).click()
        logging.info("Clicked 'EN' button")
        time.sleep(3)
        logging.debug("Waited 3s after 'EN' click")
    except Exception as e:
        logging.error(f"Failed to click 'EN': {e}")

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

def navigate_to_actual_exam_page(page, selected_module_name):
    # Module-specific link clicks for modules 4, 5, 6
    global exam_page_url
    logging.debug(f"Navigating to exam page for {selected_module_name}")
    if selected_module_name == "Module 4":
        try:
            page.get_by_role('link', name='Module 4 - 002 (ENG)').locator('a').click()
            logging.info("Clicked Module 4 link")
        except Exception as e:
            logging.error(f"Failed to click Module 4 link: {e}")
            selector = get_selector_suggestion(page, "Module 4 - 002 (ENG) link")
            logging.debug(f"AI selector for Module 4: {selector}")
            try:
                page.click(selector)
                logging.info(f"Clicked Module 4 with AI selector: {selector}")
            except Exception as e:
                logging.error(f"AI selector failed for Module 4: {e}")
    elif selected_module_name == "Module 5":
        try:
            page.get_by_role('link', name='Module 5 - 001 (ENG) Use of').locator('a').click()
            logging.info("Clicked Module 5 link")
        except Exception as e:
            logging.error(f"Failed to click Module 5 link: {e}")
            selector = get_selector_suggestion(page, "Module 5 - 001 (ENG) Use of link")
            logging.debug(f"AI selector for Module 5: {selector}")
            try:
                page.click(selector)
                logging.info(f"Clicked Module 5 with AI selector: {selector}")
            except Exception as e:
                logging.error(f"AI selector failed for Module 5: {e}")
    elif selected_module_name == "Module 6":
        try:
            page.get_by_role('link', name='Module 6 - 001 (ENG) Design').locator('a').click()
            logging.info("Clicked Module 6 link")
        except Exception as e:
            logging.error(f"Failed to click Module 6 link: {e}")
            selector = get_selector_suggestion(page, "Module 6 - 001 (ENG) Design link")
            logging.debug(f"AI selector for Module 6: {selector}")
            try:
                page.click(selector)
                logging.info(f"Clicked Module 6 with AI selector: {selector}")
            except Exception as e:
                logging.error(f"AI selector failed for Module 6: {e}")

    logging.info(f"Accessing exam for {selected_module_name}")
    try:
        try:
            page.get_by_role('button', name='Start Classes').click()
            logging.info("Clicked 'Start Classes'")
        except Exception as e:
            logging.error(f"Failed to click 'Start Classes': {e}")
            selector = get_selector_suggestion(page, "Start Classes button")
            logging.debug(f"AI selector for Start Classes: {selector}")
            try:
                page.click(selector)
                logging.info(f"Clicked 'Start Classes' with AI selector: {selector}")
            except Exception as e:
                logging.error(f"AI selector failed for Start Classes: {e}")

        try:
            page.get_by_text('View Lesson').click()
            logging.info("Clicked 'View Lesson'")
        except Exception as e:
            logging.error(f"Failed to click 'View Lesson': {e}")
            selector = get_selector_suggestion(page, "View Lesson link/button")
            logging.debug(f"AI selector for View Lesson: {selector}")
            try:
                page.click(selector)
                logging.info(f"Clicked 'View Lesson' with AI selector: {selector}")
            except Exception as e:
                logging.error(f"AI selector failed for View Lesson: {e}")

        exam_button_name = f"Final Exam {selected_module_name} batch"
        try:
            page.get_by_role('button', name=exam_button_name).click()
            logging.info(f"Clicked '{exam_button_name}'")
        except Exception as e:
            logging.error(f"Failed to click '{exam_button_name}': {e}")
            selector = get_selector_suggestion(page, f"{exam_button_name} button")
            logging.debug(f"AI selector for {exam_button_name}: {selector}")
            try:
                page.click(selector)
                logging.info(f"Clicked '{exam_button_name}' with AI selector: {selector}")
            except Exception as e:
                logging.error(f"AI selector failed for {exam_button_name}: {e}")

        try:
            option = page.get_by_role('option', name=exam_button_name)
            option.get_by_role('paragraph').click()
            logging.info(f"Clicked paragraph in '{exam_button_name}'")
        except Exception as e:
            logging.error(f"Failed to click paragraph in '{exam_button_name}': {e}")
            selector = get_selector_suggestion(page, f"paragraph in option for {exam_button_name}")
            logging.debug(f"AI selector for paragraph: {selector}")
            try:
                page.click(selector)
                logging.info(f"Clicked paragraph with AI selector: {selector}")
            except Exception as e:
                logging.error(f"AI selector failed for paragraph: {e}")

        try:
            page.get_by_role('button', name='Exam Again').click()
            logging.info("Clicked 'Exam Again'")
        except Exception as e:
            logging.error(f"Failed to click 'Exam Again': {e}")
            selector = get_selector_suggestion(page, "Exam Again button")
            logging.debug(f"AI selector for Exam Again: {selector}")
            try:
                page.click(selector)
                logging.info(f"Clicked 'Exam Again' with AI selector: {selector}")
            except Exception as e:
                logging.error(f"AI selector failed for Exam Again: {e}")

        try:
            page.get_by_role('button', name='EN', exact=True).click()
            logging.info("Clicked 'EN' button")
            time.sleep(3)
            logging.debug("Waited 3s after 'EN' click")
        except Exception as e:
            logging.error(f"Failed to click 'EN': {e}")
            selector = get_selector_suggestion(page, "EN button (exact match)")
            logging.debug(f"AI selector for EN button: {selector}")
            try:
                page.click(selector)
                logging.info(f"Clicked 'EN' with AI selector: {selector}")
            except Exception as e:
                logging.error(f"AI selector failed for EN: {e}")

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
        "Return only the selector string."
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
                logging.warning("Trying AI for close button")
                try:
                    selector = get_selector_suggestion(page, "close button")
                    logging.debug(f"AI selector for close: {selector}")
                    page.wait_for_selector(selector, timeout=7000)
                    page.click(selector)
                    logging.info(f"Closed popup with AI selector: {selector}")
                except Exception as e:
                    logging.error(f"AI close button failed: {e}")
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
                logging.warning("Trying AI for Login link")
                try:
                    selector = get_selector_suggestion(page, "login link")
                    logging.debug(f"AI selector for login: {selector}")
                    page.wait_for_selector(selector, timeout=7000)
                    page.click(selector)
                    logging.info(f"Clicked Login link with AI selector: {selector}")
                except Exception as e:
                    logging.error(f"AI login link failed: {e}")
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
                logging.warning("Trying AI for ID card input")
                try:
                    selector = get_selector_suggestion(page, "ID card number textbox")
                    logging.debug(f"AI selector for ID card: {selector}")
                    page.wait_for_selector(selector, timeout=7000)
                    page.fill(selector, config["EXAM_USERNAME"])
                    logging.info(f"Entered ID card with AI selector: {selector}")
                except Exception as e:
                    logging.error(f"AI ID card input failed: {e}")
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
                logging.warning("Trying AI for password input")
                try:
                    selector = get_selector_suggestion(page, "password textbox")
                    logging.debug(f"AI selector for password: {selector}")
                    page.wait_for_selector(selector, timeout=7000)
                    page.fill(selector, config["EXAM_PASSWORD"])
                    logging.info(f"Entered password with AI selector: {selector}")
                except Exception as e:
                    logging.error(f"AI password input failed: {e}")
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
                logging.warning("Trying AI for login button")
                try:
                    selector = get_selector_suggestion(page, "login button")
                    logging.debug(f"AI selector for login button: {selector}")
                    page.wait_for_selector(selector, timeout=7000)
                    page.click(selector)
                    logging.info(f"Clicked login button with AI selector: {selector}")
                except Exception as e:
                    logging.error(f"AI login button failed: {e}")
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
                logging.warning("Trying AI for post-login close")
                try:
                    selector = get_selector_suggestion(page, "post-login close button")
                    logging.debug(f"AI selector for post-login close: {selector}")
                    page.wait_for_selector(selector, timeout=7000)
                    page.click(selector)
                    logging.info(f"Closed post-login popup with AI selector: {selector}")
                except Exception as e:
                    logging.error(f"AI post-login close failed: {e}")
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
                logging.warning("Trying AI for My courses link")
                try:
                    selector = get_selector_suggestion(page, "My courses link")
                    logging.debug(f"AI selector for My courses: {selector}")
                    page.wait_for_selector(selector, timeout=7000)
                    page.click(selector)
                    logging.info(f"Clicked My courses link with AI selector: {selector}")
                except Exception as e:
                    logging.error(f"AI My courses link failed: {e}")
                    logging.warning("No My courses link found")

        logging.info("Navigation completed")
        return True
    except Exception as e:
        logging.error(f"Navigation failed: {e}")
        return False
