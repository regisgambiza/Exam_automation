import time
import logging
import os
from playwright.sync_api import Page
from tenacity import retry, stop_after_attempt, wait_fixed
import ollama

# Example list of answer indices for testing (20 questions, random choices)
test_answers = [1, 2, 3, 4, 2, 1, 4, 3, 2, 1, 3, 4, 2, 1, 4, 3, 2, 1, 3, 4,1, 2, 3, 4, 2, 1, 4, 3, 2, 1]

def click_answer_by_index(page, answer_index):
    """Click the answer button by index, with AI fallback."""
    try:
        answer_buttons = page.query_selector_all('button')
        for btn in answer_buttons:
            btn_text = btn.inner_text().strip()
            if btn_text.startswith(f"{answer_index}."):
                btn.click()
                logging.info(f"Clicked answer button: {btn_text}")
                return True
        raise Exception("Answer button not found by index.")
    except Exception:
        selector = get_selector_suggestion(page, f"answer button for option {answer_index}")
        page.click(selector)
        logging.info(f"Clicked answer button (AI selector: {selector}) for option {answer_index}")
        return False

def click_next(page):
    """Click the 'Next >' button, with AI fallback."""
    try:
        # Use a short timeout to quickly detect missing button
        page.get_by_role('button', name='Next >').click(timeout=500)
        logging.info("Clicked 'Next >' button.")
        return True
    except Exception:
        logging.info("'Next >' button not found.")
        return False

def submit_exam(page):
    """Submit the exam using robust logic and AI fallback."""
    logging.info("Submitting exam...")

    # First Submit button (main page)
    try:
        page.get_by_role('button', name='Submit').click(timeout=1000)
        logging.info("Clicked 'Submit' button (by role).")
    except Exception:
        logging.warning("Could not find 'Submit' button (by role).")

    # Wait for confirmation button to appear (if needed)
    page.wait_for_timeout(1000)

    # Second Submit button (confirmation dialog)
    try:
        submit_buttons = page.locator('button', has_text='Submit')
        count = submit_buttons.count()
        logging.info(f"Found {count} 'Submit' buttons.")

        if count >= 2:
            submit_buttons.nth(1).click(timeout=1000)
            logging.info("Clicked second 'Submit' button (confirmation).")
        elif count == 1:
            submit_buttons.nth(0).click(timeout=1000)
            logging.info("Clicked only available 'Submit' button.")
        else:
            logging.warning("No 'Submit' button found in fallback locator.")
    except Exception as e:
        logging.error(f"Error clicking second 'Submit' button: {e}")

    logging.info("Exam automation complete.")



def run_ocr_and_cleanup():
    from ocr import extract_text_from_pics_and_get_score
    score = extract_text_from_pics_and_get_score()
    logging.info(f"[RESULT] Final score: {score}/30")
    try:
        for fname in os.listdir("pics"):
            if fname.lower().endswith(".png"):
                os.remove(os.path.join("pics", fname))
        print("[debug] All pics deleted since score was successfully found.")
    except Exception as e:
        print(f"[error] Failed to delete pics: {e}")

def take_exam_screenshots(page, num_shots=20, delay=0.2):
    os.makedirs("pics", exist_ok=True)
    for i in range(50):
        fname = f"pics/exam_submit_{i+1}.png"
        page.screenshot(path=fname)
        print(f"[debug] Screenshot saved: {fname}")
        time.sleep(0.1)

def complete_exam(page, answers):
    """Complete the exam in the browser by selecting answers and submitting, using AI selector fallback if needed."""
    logging.info(f"Starting exam automation for {len(answers)} questions...")
    for idx, answer_index in enumerate(answers):
        logging.info(f"Answering question {idx+1}: Option {answer_index}")
        click_answer_by_index(page, answer_index)
        if not click_next(page):
            logging.info("'Next >' button not found. Submitting exam immediately...")
            take_exam_screenshots(page)
            submit_exam(page)
            run_ocr_and_cleanup()
            return
    

def navigate_to_actual_exam_page(page, selected_module_name):
    # Module-specific link clicks for modules 4, 5, 6
    if selected_module_name == "Module 4":
        try:
            page.get_by_role('link', name='Module 4 - 002 (ENG)').locator('a').click()
            logging.info("Clicked Module 4 specific link.")
        except Exception:
            selector = get_selector_suggestion(page, "Module 4 - 002 (ENG) link")
            page.click(selector)
            logging.info(f"Clicked Module 4 specific link (AI selector: {selector}).")
    elif selected_module_name == "Module 5":
        try:
            page.get_by_role('link', name='Module 5 - 001 (ENG) Use of').locator('a').click()
            logging.info("Clicked Module 5 specific link.")
        except Exception:
            selector = get_selector_suggestion(page, "Module 5 - 001 (ENG) Use of link")
            page.click(selector)
            logging.info(f"Clicked Module 5 specific link (AI selector: {selector}).")
    elif selected_module_name == "Module 6":
        try:
            page.get_by_role('link', name='Module 6 - 001 (ENG) Design').locator('a').click()
            logging.info("Clicked Module 6 specific link.")
        except Exception:
            selector = get_selector_suggestion(page, "Module 6 - 001 (ENG) Design link")
            page.click(selector)
            logging.info(f"Clicked Module 6 specific link (AI selector: {selector}).")
    """Navigate to the actual exam page after module selection, using robust selectors and Ollama for fallback."""
    logging.info(f"Navigating to actual exam page for {selected_module_name}...")
    try:
        # Click 'Start Classes' button
        try:
            page.get_by_role('button', name='Start Classes').click()
            logging.info("Clicked 'Start Classes' button.")
        except Exception:
            selector = get_selector_suggestion(page, "Start Classes button")
            page.click(selector)
            logging.info(f"Clicked 'Start Classes' button (AI selector: {selector}).")

        # Click 'View Lesson'
        try:
            page.get_by_text('View Lesson').click()
            logging.info("Clicked 'View Lesson'.")
        except Exception:
            selector = get_selector_suggestion(page, "View Lesson link/button")
            page.click(selector)
            logging.info(f"Clicked 'View Lesson' (AI selector: {selector}).")

        # Click 'Final Exam' button (module-specific)
        exam_button_name = f"Final Exam {selected_module_name} batch"
        try:
            page.get_by_role('button', name=exam_button_name).click()
            logging.info(f"Clicked '{exam_button_name}' button.")
        except Exception:
            selector = get_selector_suggestion(page, f"{exam_button_name} button")
            page.click(selector)
            logging.info(f"Clicked '{exam_button_name}' button (AI selector: {selector}).")

        # Click option (paragraph) for exam batch
        try:
            option = page.get_by_role('option', name=exam_button_name)
            option.get_by_role('paragraph').click()
            logging.info(f"Clicked paragraph in option '{exam_button_name}'.")
        except Exception:
            selector = get_selector_suggestion(page, f"paragraph in option for {exam_button_name}")
            page.click(selector)
            logging.info(f"Clicked paragraph in option (AI selector: {selector}).")

        # Click 'Exam Again' button
        try:
            page.get_by_role('button', name='Exam Again').click()
            logging.info("Clicked 'Exam Again' button.")
        except Exception:
            selector = get_selector_suggestion(page, "Exam Again button")
            page.click(selector)
            logging.info(f"Clicked 'Exam Again' button (AI selector: {selector}).")

        # Click 'EN' button (exact match)
        try:
            page.get_by_role('button', name='EN', exact=True).click()
            logging.info("Clicked 'EN' button.")
        except Exception:
            selector = get_selector_suggestion(page, "EN button (exact match)")
            page.click(selector)
            logging.info(f"Clicked 'EN' button (AI selector: {selector}).")

        # Wait for page to fully load
        page.wait_for_load_state('load')
        exam_page_url = page.url
        logging.info(f"Exam page URL: {exam_page_url}")

        # Store the URL for later use (return it)
        logging.info("Successfully navigated to the actual exam page.")
        return exam_page_url
    except Exception as e:
        logging.error(f"Failed to navigate to actual exam page: {e}")
        return False


def select_module(page):
    """Extract available modules, display them, and prompt user to select one."""
    
    modules = [f"Module {i}" for i in range(1, 8)]
    print("Available modules:")
    for idx, name in enumerate(modules, 1):
        print(f"{idx}: {name}")
    while True:
        try:
            choice = int(input("Enter the number of the module you want to use: ")) - 1
            if 0 <= choice < len(modules):
                selected_name = modules[choice]
                print(f"You selected: {selected_name}")
                logging.info(f"User selected module: {selected_name}")
                # Use locator template to click correct module
                try:
                    page.locator('div').filter(has_text=selected_name).nth(1).click()
                    logging.info(f"Clicked on module card using locator: {selected_name}")
                    return selected_name
                except Exception as e:
                    logging.error(f"Could not click module card for: {selected_name}. Error: {e}")
                    return None
            else:
                print("Invalid selection. Please try again.")
        except ValueError:
            print("Please enter a valid number.")


def get_selector_suggestion(page, target_description):
    dom_html = page.content()
    prompt = (
        f"Given this HTML:\n{dom_html}\n"
        f"Suggest a Playwright selector for: {target_description}. "
        "Return only the selector string."
    )
    response = ollama.chat(model="llama3.1:8b", messages=[{"role": "user", "content": prompt}])
    selector = response['message']['content'].strip().splitlines()[0]
    selector = selector.strip('`"\' ').split()[0]  # Remove backticks, quotes, whitespace, and take first word
    selector = selector.rstrip(';,.')
    # If selector is clearly invalid, return None
    if selector in ('//', '', '.', '#', 'None', 'null'):
        logging.error(f"AI returned invalid selector: '{selector}' for {target_description}")
        return None
    return selector


@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
def navigate_to_exam(page: Page, config: dict) -> bool:
    """Navigate to the exam page by performing login and clicking through menus."""
    try:
        logging.info("Navigating to base URL...")
        page.goto(config["BASE_URL"])
        # Close popup
        logging.info("Looking for initial close button...")
        try:
            page.wait_for_selector('button:has-text("close")', timeout=7000)
            page.click('button:has-text("close")')
            logging.info("Closed initial popup.")
        except Exception:
            try:
                page.wait_for_selector('button.close', timeout=7000)
                page.click('button.close')
                logging.info("Closed initial popup (fallback selector).")
            except Exception:
                logging.warning("No close button found. Trying AI suggestion...")
                try:
                    selector = get_selector_suggestion(page, "close button")
                    page.wait_for_selector(selector, timeout=7000)
                    page.click(selector)
                    logging.info(f"Closed initial popup (AI selector: {selector}).")
                except Exception:
                    logging.warning("AI-suggested close button also failed.")
        # Click Login
        logging.info("Clicking Login link...")
        try:
            page.wait_for_selector('a:has-text("Login")', timeout=7000)
            page.click('a:has-text("Login")')
            logging.info("Clicked Login link.")
        except Exception:
            try:
                page.wait_for_selector('a.login', timeout=7000)
                page.click('a.login')
                logging.info("Clicked Login link (fallback selector).")
            except Exception:
                logging.warning("No login link found. Trying AI suggestion...")
                try:
                    selector = get_selector_suggestion(page, "login link")
                    page.wait_for_selector(selector, timeout=7000)
                    page.click(selector)
                    logging.info(f"Clicked Login link (AI selector: {selector}).")
                except Exception:
                    logging.warning("AI-suggested login link also failed.")
        # Fill ID card number
        logging.info("Entering ID card number...")
        try:
            page.wait_for_selector('input#input-201', timeout=7000)
            page.fill('input#input-201', config["EXAM_USERNAME"])
            logging.info("Entered ID card number in #input-201.")
        except Exception:
            try:
                page.wait_for_selector('input[placeholder*="ID card number"]', timeout=7000)
                page.fill('input[placeholder*="ID card number"]', config["EXAM_USERNAME"])
                logging.info("Entered ID card number in placeholder input.")
            except Exception:
                logging.warning("No ID card input found. Trying AI suggestion...")
                try:
                    selector = get_selector_suggestion(page, "ID card number textbox")
                    page.wait_for_selector(selector, timeout=7000)
                    page.fill(selector, config["EXAM_USERNAME"])
                    logging.info(f"Entered ID card number (AI selector: {selector}).")
                except Exception:
                    logging.warning("AI-suggested ID card input also failed.")
        # Fill password
        logging.info("Entering password...")
        try:
            page.wait_for_selector('input#password', timeout=7000)
            page.fill('input#password', config["EXAM_PASSWORD"])
            logging.info("Entered password in #password.")
        except Exception:
            try:
                page.wait_for_selector('input[type="password"]', timeout=7000)
                page.fill('input[type="password"]', config["EXAM_PASSWORD"])
                logging.info("Entered password in type=password input.")
            except Exception:
                logging.warning("No password input found. Trying AI suggestion...")
                try:
                    selector = get_selector_suggestion(page, "password textbox")
                    page.wait_for_selector(selector, timeout=7000)
                    page.fill(selector, config["EXAM_PASSWORD"])
                    logging.info(f"Entered password (AI selector: {selector}).")
                except Exception:
                    logging.warning("AI-suggested password input also failed.")
        # Click login button
        logging.info("Clicking login button...")
        try:
            page.wait_for_selector('button:has-text("login")', timeout=7000)
            page.click('button:has-text("login")')
            logging.info("Clicked login button.")
        except Exception:
            try:
                page.wait_for_selector('button.login', timeout=7000)
                page.click('button.login')
                logging.info("Clicked login button (fallback selector).")
            except Exception:
                logging.warning("No login button found. Trying AI suggestion...")
                try:
                    selector = get_selector_suggestion(page, "login button")
                    page.wait_for_selector(selector, timeout=7000)
                    page.click(selector)
                    logging.info(f"Clicked login button (AI selector: {selector}).")
                except Exception:
                    logging.warning("AI-suggested login button also failed.")
        # Close post-login popup
        logging.info("Looking for post-login close button...")
        try:
            page.wait_for_selector('button:has-text("close")', timeout=7000)
            page.click('button:has-text("close")')
            logging.info("Closed post-login popup.")
        except Exception:
            try:
                page.wait_for_selector('button.close', timeout=7000)
                page.click('button.close')
                logging.info("Closed post-login popup (fallback selector).")
            except Exception:
                logging.warning("No post-login close button found. Trying AI suggestion...")
                try:
                    selector = get_selector_suggestion(page, "post-login close button")
                    page.wait_for_selector(selector, timeout=7000)
                    page.click(selector)
                    logging.info(f"Closed post-login popup (AI selector: {selector}).")
                except Exception:
                    logging.warning("AI-suggested post-login close button also failed.")
        # Click My courses
        logging.info("Clicking My courses link...")
        try:
            page.wait_for_selector('a:has-text("My courses")', timeout=7000)
            page.click('a:has-text("My courses")')
            logging.info("Clicked My courses link.")
        except Exception:
            try:
                page.wait_for_selector('a.my-courses', timeout=7000)
                page.click('a.my-courses')
                logging.info("Clicked My courses link (fallback selector).")
            except Exception:
                logging.warning("No My courses link found. Trying AI suggestion...")
                try:
                    selector = get_selector_suggestion(page, "My courses link")
                    page.wait_for_selector(selector, timeout=7000)
                    page.click(selector)
                    logging.info(f"Clicked My courses link (AI selector: {selector}).")
                except Exception:
                    logging.warning("AI-suggested My courses link also failed.")
        logging.info("Navigation successful.")
        return True
    except Exception as e:
        logging.error(f"Navigation failed: {e}")
        return False