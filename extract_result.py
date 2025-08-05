import logging
from playwright.sync_api import sync_playwright, Page
import re

def extract_exam_result(page: Page):
    """
    Extracts the exam result and total score from the notification or popup after submission.
    Returns a tuple: (result_text, score_text) where score_text is like '23/30'.
    """
    result_text = None
    score_text = None
    try:
        # Wait for the result heading to appear (Fail or Pass)
        for status in ['Fail', 'Pass']:
            try:
                heading = f'Examination results : {status}'
                result_heading = page.get_by_role('heading', name=heading)
                result_heading.wait_for(timeout=5000)
                result_heading.click()
                logging.info(f"Clicked result heading: {heading}")
                result_text = heading
                break
            except Exception:
                continue
        if not result_text:
            logging.error("Failed to find result heading")
        # Now look for score text like '23/30' in the popup
        # Try to find any element containing the score pattern
        score_pattern = re.compile(r'\b(\d{1,2}/30)\b')
        # Search all visible text on the page
        all_text = page.content()
        match = score_pattern.search(all_text)
        if match:
            score_text = match.group(1)
            logging.info(f"Extracted score: {score_text}")
        else:
            logging.warning("No score found in page content")
        return result_text, score_text
    except Exception as e:
        logging.error(f"Failed to extract result: {e}")
        return None, None

if __name__ == "__main__":
    # Example usage (for manual testing)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        # ...navigate to exam and submit...
        result = extract_exam_result(page)
        print(f"Exam result: {result}")
