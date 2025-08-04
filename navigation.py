import time
import logging
import os
from playwright.sync_api import Page
from tenacity import retry, stop_after_attempt, wait_fixed
import ollama

# Configure logging to capture detailed debug information
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

exam_page_url = None
selected_module_name = None  # Global declaration

def click_answer_by_index(page, answer_index):
    """Click the answer button by index, with AI fallback."""
    logging.debug(f"Entering click_answer_by_index with answer_index: {answer_index}")
    try:
        logging.debug("Querying all button elements")
        answer_buttons = page.query_selector_all('button')
        logging.debug(f"Found {len(answer_buttons)} button elements")
        for btn in answer_buttons:
            btn_text = btn.inner_text().strip()
            logging.debug(f"Checking button with text: '{btn_text}'")
            if btn_text.startswith(f"{answer_index}."):
                logging.debug(f"Found matching button with text: '{btn_text}'")
                btn.click()
                logging.info(f"Clicked answer button: {btn_text}")
                return True
        logging.debug("No answer button found by index matching")
        raise Exception("Answer button not found by index.")
    except Exception as e:
        logging.error(f"Error in click_answer_by_index: {e}")
        logging.debug(f"Attempting AI fallback for answer button index {answer_index}")
        selector = get_selector_suggestion(page, f"answer button for option {answer_index}")
        logging.debug(f"AI suggested selector: '{selector}'")
        try:
            page.click(selector)
            logging.info(f"Clicked answer button (AI selector: {selector}) for option {answer_index}")
            return False
        except Exception as e:
            logging.error(f"AI selector click failed: {e}")
            raise

def click_next(page):
    """Click the 'Next >' button, with AI fallback."""
    logging.debug("Entering click_next")
    try:
        logging.debug("Attempting to click 'Next >' button by role")
        page.get_by_role('button', name='Next >').click(timeout=500)
        logging.info("Clicked 'Next >' button.")
        return True
    except Exception as e:
        logging.error(f"Failed to click 'Next >' button: {e}")
        logging.info("'Next >' button not found.")
        return False

def submit_exam(page):
    """Submit the exam and extract the result."""
    logging.debug("Entering submit_exam")
    logging.info("Submitting exam...")
    try:
        logging.debug("Attempting to click 'Submit' button by role")
        page.get_by_role('button', name='Submit').click(timeout=1000)
        logging.info("Clicked 'Submit' button (by role).")
    except Exception as e:
        logging.error(f"Failed to click 'Submit' button by role: {e}")

    page.wait_for_timeout(2000)  # Increased wait for result to load
    logging.debug("Waited 2000ms after clicking Submit")

    logging.debug("Locating submit buttons with text 'Submit'")
    submit_buttons = page.locator('button', has_text='Submit')
    count = submit_buttons.count()
    logging.debug(f"Found {count} submit buttons")

    if count >= 2:
        logging.debug("Attempting to click second 'Submit' button")
        try:
            submit_buttons.nth(1).click(timeout=1000)
            logging.info("Clicked second 'Submit' button (confirmation).")
            page.wait_for_timeout(2000)  # Wait for confirmation to process
        except Exception as e:
            logging.error(f"Failed to click second 'Submit' button: {e}")
    elif count == 1:
        logging.debug("Attempting to click only available 'Submit' button")
        try:
            submit_buttons.nth(0).click(timeout=1000)
            logging.info("Clicked only available 'Submit' button.")
            page.wait_for_timeout(2000)
        except Exception as e:
            logging.error(f"Failed to click only 'Submit' button: {e}")
    else:
        logging.warning("No additional 'Submit' button found.")

    try:
        from extract_result import extract_exam_result
        logging.debug("Extracting exam result")
        result = extract_exam_result(page)
        logging.info(f"Exam result extracted: {result}")
        return result  # Return result_text, score_text
    except Exception as e:
        logging.error(f"Failed to extract exam result: {e}")
        return None, None

def restart_exam(page):
    """Restart the exam after submission."""
    global selected_module_name
    exam_button_name = f"Final Exam {selected_module_name} batch"
    logging.debug(f"Entering restart_exam with exam_button_name: '{exam_button_name}'")

    logging.info("Restarting exam process...")
    try:
        logging.debug("Attempting to click 'View Lesson'")
        page.get_by_text('View Lesson').click()
        logging.info("Clicked 'View Lesson'.")
    except Exception as e:
        logging.error(f"Failed to click 'View Lesson': {e}")

    try:
        logging.debug(f"Attempting to click '{exam_button_name}'")
        page.get_by_text(exam_button_name, exact=False).click()
        logging.info(f"Clicked '{exam_button_name}'.")
    except Exception as e:
        logging.error(f"Failed to click '{exam_button_name}': {e}")

    # Fixed section: Handle paragraph click with robust selector and AI fallback
    try:
        logging.debug(f"Attempting to click paragraph in option '{exam_button_name}'")
        option = page.get_by_role('option', name=exam_button_name)
        option.get_by_role('paragraph').click()
        logging.info(f"Clicked paragraph in option '{exam_button_name}'.")
    except Exception as e:
        logging.error(f"Failed to click paragraph in option '{exam_button_name}': {e}")
        selector = get_selector_suggestion(page, f"paragraph in option for {exam_button_name}")
        logging.debug(f"AI suggested selector for paragraph option: '{selector}'")
        try:
            page.click(selector)
            logging.info(f"Clicked paragraph in option (AI selector: {selector}).")
        except Exception as e:
            logging.error(f"AI selector click for paragraph option failed: {e}")

    try:
        logging.debug("Attempting to click 'Exam Again' button")
        page.get_by_text("Exam Again", exact=False).click()
        logging.info("Clicked 'Exam Again' button.")
    except Exception as e:
        logging.error(f"Failed to click 'Exam Again' button: {e}")

    try:
        logging.debug("Attempting to click 'EN' button")
        page.get_by_text("EN", exact=True).click()
        logging.info("Clicked 'EN' button.")
        time.sleep(3)
        logging.debug("Waited 3 seconds after clicking 'EN' button")
    except Exception as e:
        logging.error(f"Failed to click 'EN' button: {e}")

def complete_exam(page, answers):
    """Complete the exam in the browser by selecting answers and submitting."""
    logging.debug(f"Entering complete_exam with {len(answers)} answers: {answers}")
    logging.info(f"Starting exam automation for {len(answers)} questions...")
    for idx, answer_index in enumerate(answers):
        logging.info(f"Answering question {idx+1}: Option {answer_index}")
        try:
            page.wait_for_selector('button, input[type="radio"], input[type="checkbox"]', timeout=10000)
            click_answer_by_index(page, answer_index)
            page.wait_for_timeout(500)  # Ensure selection registers
            if not click_next(page):
                logging.info("'Next >' button not found. Submitting exam...")
                result = submit_exam(page)
                if result[1] is None:
                    logging.error("Failed to extract score in submit_exam.")
                    return None, None
                restart_exam(page)  # Restart after submission
                return result
        except Exception as e:
            logging.error(f"Failed to answer question {idx+1}: {e}")
            return None, None
    logging.debug("Completed all questions, proceeding to submit")
    try:
        result = submit_exam(page)
        if result[1] is None:
            logging.error("Failed to extract score in submit_exam.")
            return None, None
        restart_exam(page)  # Restart after submission
        return result
    except Exception as e:
        logging.error(f"Failed to submit exam: {e}")
        return None, None

def navigate_to_actual_exam_page(page, selected_module_name):
    # Module-specific link clicks for modules 4, 5, 6
    global exam_page_url
    logging.debug(f"Entering navigate_to_actual_exam_page with selected_module_name: {selected_module_name}")
    if selected_module_name == "Module 4":
        try:
            logging.debug("Attempting to click Module 4 specific link")
            page.get_by_role('link', name='Module 4 - 002 (ENG)').locator('a').click()
            logging.info("Clicked Module 4 specific link.")
        except Exception as e:
            logging.error(f"Failed to click Module 4 link: {e}")
            selector = get_selector_suggestion(page, "Module 4 - 002 (ENG) link")
            logging.debug(f"AI suggested selector for Module 4: '{selector}'")
            try:
                page.click(selector)
                logging.info(f"Clicked Module 4 specific link (AI selector: {selector}).")
            except Exception as e:
                logging.error(f"AI selector click for Module 4 failed: {e}")
    elif selected_module_name == "Module 5":
        try:
            logging.debug("Attempting to click Module 5 specific link")
            page.get_by_role('link', name='Module 5 - 001 (ENG) Use of').locator('a').click()
            logging.info("Clicked Module 5 specific link.")
        except Exception as e:
            logging.error(f"Failed to click Module 5 link: {e}")
            selector = get_selector_suggestion(page, "Module 5 - 001 (ENG) Use of link")
            logging.debug(f"AI suggested selector for Module 5: '{selector}'")
            try:
                page.click(selector)
                logging.info(f"Clicked Module 5 specific link (AI selector: {selector}).")
            except Exception as e:
                logging.error(f"AI selector click for Module 5 failed: {e}")
    elif selected_module_name == "Module 6":
        try:
            logging.debug("Attempting to click Module 6 specific link")
            page.get_by_role('link', name='Module 6 - 001 (ENG) Design').locator('a').click()
            logging.info("Clicked Module 6 specific link.")
        except Exception as e:
            logging.error(f"Failed to click Module 6 link: {e}")
            selector = get_selector_suggestion(page, "Module 6 - 001 (ENG) Design link")
            logging.debug(f"AI suggested selector for Module 6: '{selector}'")
            try:
                page.click(selector)
                logging.info(f"Clicked Module 6 specific link (AI selector: {selector}).")
            except Exception as e:
                logging.error(f"AI selector click for Module 6 failed: {e}")

    logging.info(f"Navigating to actual exam page for {selected_module_name}...")
    try:
        try:
            logging.debug("Attempting to click 'Start Classes' button")
            page.get_by_role('button', name='Start Classes').click()
            logging.info("Clicked 'Start Classes' button.")
        except Exception as e:
            logging.error(f"Failed to click 'Start Classes' button: {e}")
            selector = get_selector_suggestion(page, "Start Classes button")
            logging.debug(f"AI suggested selector for Start Classes: '{selector}'")
            try:
                page.click(selector)
                logging.info(f"Clicked 'Start Classes' button (AI selector: {selector}).")
            except Exception as e:
                logging.error(f"AI selector click for Start Classes failed: {e}")

        try:
            logging.debug("Attempting to click 'View Lesson'")
            page.get_by_text('View Lesson').click()
            logging.info("Clicked 'View Lesson'.")
        except Exception as e:
            logging.error(f"Failed to click 'View Lesson': {e}")
            selector = get_selector_suggestion(page, "View Lesson link/button")
            logging.debug(f"AI suggested selector for View Lesson: '{selector}'")
            try:
                page.click(selector)
                logging.info(f"Clicked 'View Lesson' (AI selector: {selector}).")
            except Exception as e:
                logging.error(f"AI selector click for View Lesson failed: {e}")

        exam_button_name = f"Final Exam {selected_module_name} batch"
        try:
            logging.debug(f"Attempting to click '{exam_button_name}' button")
            page.get_by_role('button', name=exam_button_name).click()
            logging.info(f"Clicked '{exam_button_name}' button.")
        except Exception as e:
            logging.error(f"Failed to click '{exam_button_name}' button: {e}")
            selector = get_selector_suggestion(page, f"{exam_button_name} button")
            logging.debug(f"AI suggested selector for {exam_button_name}: '{selector}'")
            try:
                page.click(selector)
                logging.info(f"Clicked '{exam_button_name}' button (AI selector: {selector}).")
            except Exception as e:
                logging.error(f"AI selector click for {exam_button_name} failed: {e}")

        try:
            logging.debug(f"Attempting to click paragraph in option '{exam_button_name}'")
            option = page.get_by_role('option', name=exam_button_name)
            option.get_by_role('paragraph').click()
            logging.info(f"Clicked paragraph in option '{exam_button_name}'.")
        except Exception as e:
            logging.error(f"Failed to click paragraph in option '{exam_button_name}': {e}")
            selector = get_selector_suggestion(page, f"paragraph in option for {exam_button_name}")
            logging.debug(f"AI suggested selector for paragraph option: '{selector}'")
            try:
                page.click(selector)
                logging.info(f"Clicked paragraph in option (AI selector: {selector}).")
            except Exception as e:
                logging.error(f"AI selector click for paragraph option failed: {e}")

        try:
            logging.debug("Attempting to click 'Exam Again' button")
            page.get_by_role('button', name='Exam Again').click()
            logging.info("Clicked 'Exam Again' button.")
        except Exception as e:
            logging.error(f"Failed to click 'Exam Again' button: {e}")
            selector = get_selector_suggestion(page, "Exam Again button")
            logging.debug(f"AI suggested selector for Exam Again: '{selector}'")
            try:
                page.click(selector)
                logging.info(f"Clicked 'Exam Again' button (AI selector: {selector}).")
            except Exception as e:
                logging.error(f"AI selector click for Exam Again failed: {e}")

        try:
            logging.debug("Attempting to click 'EN' button")
            page.get_by_role('button', name='EN', exact=True).click()
            logging.info("Clicked 'EN' button.")
            time.sleep(3)
            logging.debug("Waited 3 seconds after clicking 'EN' button")
        except Exception as e:
            logging.error(f"Failed to click 'EN' button: {e}")
            selector = get_selector_suggestion(page, "EN button (exact match)")
            logging.debug(f"AI suggested selector for EN button: '{selector}'")
            try:
                page.click(selector)
                logging.info(f"Clicked 'EN' button (AI selector: {selector}).")
            except Exception as e:
                logging.error(f"AI selector click for EN button failed: {e}")

        logging.debug("Waiting for page to fully load")
        page.wait_for_load_state('load')
        exam_page_url = page.url
        logging.info(f"Exam page URL: {exam_page_url}")

        logging.info("Successfully navigated to the actual exam page.")
        return exam_page_url
    except Exception as e:
        logging.error(f"Failed to navigate to actual exam page: {e}")
        return False

def select_module(page):
    """Extract available modules, display them, and prompt user to select one."""
    global selected_module_name
    logging.debug("Entering select_module")
    modules = [f"Module {i}" for i in range(1, 8)]
    logging.debug(f"Available modules: {modules}")
    print("Available modules:")
    for idx, name in enumerate(modules, 1):
        print(f"{idx}: {name}")
    while True:
        try:
            choice = int(input("Enter the number of the module you want to use: ")) - 1
            logging.debug(f"User input choice: {choice + 1}")
            if 0 <= choice < len(modules):
                selected_module_name = modules[choice]
                print(f"You selected: {selected_module_name}")
                logging.info(f"User selected module: {selected_module_name}")
                try:
                    logging.debug(f"Attempting to click module card for: {selected_module_name}")
                    page.locator('div').filter(has_text=selected_module_name).nth(1).click()
                    logging.info(f"Clicked on module card using locator: {selected_module_name}")
                    return selected_module_name
                except Exception as e:
                    logging.error(f"Failed to click module card for {selected_module_name}: {e}")
                    return None
            else:
                logging.debug(f"Invalid selection: {choice + 1}")
                print("Invalid selection. Please try again.")
        except ValueError as e:
            logging.error(f"Invalid input for module selection: {e}")
            print("Please enter a valid number.")

def get_selector_suggestion(page, target_description):
    logging.debug(f"Entering get_selector_suggestion for target: {target_description}")
    dom_html = page.content()
    logging.debug(f"Retrieved DOM content length: {len(dom_html)}")
    prompt = (
        f"Given this HTML:\n{dom_html}\n"
        f"Suggest a Playwright selector for: {target_description}. "
        "Return only the selector string."
    )
    logging.debug(f"Sending prompt to Ollama with length: {len(prompt)}")
    try:
        response = ollama.chat(model="llama3.1:8b", messages=[{"role": "user", "content": prompt}])
        selector = response['message']['content'].strip().splitlines()[0]
        logging.debug(f"Ollama response selector: '{selector}'")
        selector = selector.strip('`"\' ').split()[0]
        selector = selector.rstrip(';,.')
        logging.debug(f"Processed selector: '{selector}'")
        if selector in ('//', '', '.', '#', 'None', 'null'):
            logging.error(f"AI returned invalid selector: '{selector}' for {target_description}")
            return None
        return selector
    except Exception as e:
        logging.error(f"Failed to get selector suggestion from Ollama: {e}")
        return None

@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
def navigate_to_exam(page: Page, config: dict) -> bool:
    """Navigate to the exam page by performing login and clicking through menus."""
    logging.debug(f"Entering navigate_to_exam with config: {config}")
    try:
        logging.info("Navigating to base URL...")
        page.goto(config["BASE_URL"])
        logging.debug(f"Navigated to URL: {config['BASE_URL']}")
        
        logging.info("Looking for initial close button...")
        try:
            logging.debug("Waiting for close button selector 'button:has-text(\"close\")'")
            page.wait_for_selector('button:has-text("close")', timeout=7000)
            page.click('button:has-text("close")')
            logging.info("Closed initial popup.")
        except Exception as e:
            logging.error(f"Failed to find/close initial popup: {e}")
            try:
                logging.debug("Trying fallback selector 'button.close'")
                page.wait_for_selector('button.close', timeout=7000)
                page.click('button.close')
                logging.info("Closed initial popup (fallback selector).")
            except Exception as e:
                logging.error(f"Failed fallback close button: {e}")
                logging.warning("No close button found. Trying AI suggestion...")
                try:
                    selector = get_selector_suggestion(page, "close button")
                    logging.debug(f"AI suggested selector for close button: '{selector}'")
                    page.wait_for_selector(selector, timeout=7000)
                    page.click(selector)
                    logging.info(f"Closed initial popup (AI selector: {selector}).")
                except Exception as e:
                    logging.error(f"AI-suggested close button failed: {e}")
                    logging.warning("AI-suggested close button also failed.")

        logging.info("Clicking Login link...")
        try:
            logging.debug("Waiting for Login link selector 'a:has-text(\"Login\")'")
            page.wait_for_selector('a:has-text("Login")', timeout=7000)
            page.click('a:has-text("Login")')
            logging.info("Clicked Login link.")
        except Exception as e:
            logging.error(f"Failed to find/click Login link: {e}")
            try:
                logging.debug("Trying fallback selector 'a.login'")
                page.wait_for_selector('a.login', timeout=7000)
                page.click('a.login')
                logging.info("Clicked Login link (fallback selector).")
            except Exception as e:
                logging.error(f"Failed fallback Login link: {e}")
                logging.warning("No login link found. Trying AI suggestion...")
                try:
                    selector = get_selector_suggestion(page, "login link")
                    logging.debug(f"AI suggested selector for login link: '{selector}'")
                    page.wait_for_selector(selector, timeout=7000)
                    page.click(selector)
                    logging.info(f"Clicked Login link (AI selector: {selector}).")
                except Exception as e:
                    logging.error(f"AI-suggested login link failed: {e}")
                    logging.warning("AI-suggested login link also failed.")

        logging.info("Entering ID card number...")
        try:
            logging.debug("Waiting for ID card input selector 'input#input-201'")
            page.wait_for_selector('input#input-201', timeout=7000)
            page.fill('input#input-201', config["EXAM_USERNAME"])
            logging.info("Entered ID card number in #input-201.")
        except Exception as e:
            logging.error(f"Failed to find/fill ID card input: {e}")
            try:
                logging.debug("Trying fallback selector 'input[placeholder*=\"ID card number\"]'")
                page.wait_for_selector('input[placeholder*="ID card number"]', timeout=7000)
                page.fill('input[placeholder*="ID card number"]', config["EXAM_USERNAME"])
                logging.info("Entered ID card number in placeholder input.")
            except Exception as e:
                logging.error(f"Failed fallback ID card input: {e}")
                logging.warning("No ID card input found. Trying AI suggestion...")
                try:
                    selector = get_selector_suggestion(page, "ID card number textbox")
                    logging.debug(f"AI suggested selector for ID card input: '{selector}'")
                    page.wait_for_selector(selector, timeout=7000)
                    page.fill(selector, config["EXAM_USERNAME"])
                    logging.info(f"Entered ID card number (AI selector: {selector}).")
                except Exception as e:
                    logging.error(f"AI-suggested ID card input failed: {e}")
                    logging.warning("AI-suggested ID card input also failed.")

        logging.info("Entering password...")
        try:
            logging.debug("Waiting for password input selector 'input#password'")
            page.wait_for_selector('input#password', timeout=7000)
            page.fill('input#password', config["EXAM_PASSWORD"])
            logging.info("Entered password in #password.")
        except Exception as e:
            logging.error(f"Failed to find/fill password input: {e}")
            try:
                logging.debug("Trying fallback selector 'input[type=\"password\"]'")
                page.wait_for_selector('input[type="password"]', timeout=7000)
                page.fill('input[type="password"]', config["EXAM_PASSWORD"])
                logging.info("Entered password in type=password input.")
            except Exception as e:
                logging.error(f"Failed fallback password input: {e}")
                logging.warning("No password input found. Trying AI suggestion...")
                try:
                    selector = get_selector_suggestion(page, "password textbox")
                    logging.debug(f"AI suggested selector for password input: '{selector}'")
                    page.wait_for_selector(selector, timeout=7000)
                    page.fill(selector, config["EXAM_PASSWORD"])
                    logging.info(f"Entered password (AI selector: {selector}).")
                except Exception as e:
                    logging.error(f"AI-suggested password input failed: {e}")
                    logging.warning("AI-suggested password input also failed.")

        logging.info("Clicking login button...")
        try:
            logging.debug("Waiting for login button selector 'button:has-text(\"login\")'")
            page.wait_for_selector('button:has-text("login")', timeout=7000)
            page.click('button:has-text("login")')
            logging.info("Clicked login button.")
        except Exception as e:
            logging.error(f"Failed to find/click login button: {e}")
            try:
                logging.debug("Trying fallback selector 'button.login'")
                page.wait_for_selector('button.login', timeout=7000)
                page.click('button.login')
                logging.info("Clicked login button (fallback selector).")
            except Exception as e:
                logging.error(f"Failed fallback login button: {e}")
                logging.warning("No login button found. Trying AI suggestion...")
                try:
                    selector = get_selector_suggestion(page, "login button")
                    logging.debug(f"AI suggested selector for login button: '{selector}'")
                    page.wait_for_selector(selector, timeout=7000)
                    page.click(selector)
                    logging.info(f"Clicked login button (AI selector: {selector}).")
                except Exception as e:
                    logging.error(f"AI-suggested login button failed: {e}")
                    logging.warning("AI-suggested login button also failed.")

        logging.info("Looking for post-login close button...")
        try:
            logging.debug("Waiting for post-login close button selector 'button:has-text(\"close\")'")
            page.wait_for_selector('button:has-text("close")', timeout=7000)
            page.click('button:has-text("close")')
            logging.info("Closed post-login popup.")
        except Exception as e:
            logging.error(f"Failed to find/close post-login popup: {e}")
            try:
                logging.debug("Trying fallback selector 'button.close'")
                page.wait_for_selector('button.close', timeout=7000)
                page.click('button.close')
                logging.info("Closed post-login popup (fallback selector).")
            except Exception as e:
                logging.error(f"Failed fallback post-login close button: {e}")
                logging.warning("No post-login close button found. Trying AI suggestion...")
                try:
                    selector = get_selector_suggestion(page, "post-login close button")
                    logging.debug(f"AI suggested selector for post-login close button: '{selector}'")
                    page.wait_for_selector(selector, timeout=7000)
                    page.click(selector)
                    logging.info(f"Closed post-login popup (AI selector: {selector}).")
                except Exception as e:
                    logging.error(f"AI-suggested post-login close button failed: {e}")
                    logging.warning("AI-suggested post-login close button also failed.")

        logging.info("Clicking My courses link...")
        try:
            logging.debug("Waiting for My courses link selector 'a:has-text(\"My courses\")'")
            page.wait_for_selector('a:has-text("My courses")', timeout=7000)
            page.click('a:has-text("My courses")')
            logging.info("Clicked My courses link.")
        except Exception as e:
            logging.error(f"Failed to find/click My courses link: {e}")
            try:
                logging.debug("Trying fallback selector 'a.my-courses'")
                page.wait_for_selector('a.my-courses', timeout=7000)
                page.click('a.my-courses')
                logging.info("Clicked My courses link (fallback selector).")
            except Exception as e:
                logging.error(f"Failed fallback My courses link: {e}")
                logging.warning("No My courses link found. Trying AI suggestion...")
                try:
                    selector = get_selector_suggestion(page, "My courses link")
                    logging.debug(f"AI suggested selector for My courses link: '{selector}'")
                    page.wait_for_selector(selector, timeout=7000)
                    page.click(selector)
                    logging.info(f"Clicked My courses link (AI selector: {selector}).")
                except Exception as e:
                    logging.error(f"AI-suggested My courses link failed: {e}")
                    logging.warning("AI-suggested My courses link also failed.")

        logging.info("Navigation successful.")
        return True
    except Exception as e:
        logging.error(f"Navigation failed: {e}")
        return False