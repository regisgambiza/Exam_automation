import logging
from playwright.sync_api import Page

def click_answer(page: Page, question_index: int, option: int) -> None:
    """Select the specified answer option for the given question index."""

def click_next(page: Page) -> bool:
    """Click the Next button to move to the next question, returning False if not found."""

def submit_exam(page: Page) -> None:
    """Submit the exam to trigger score display."""