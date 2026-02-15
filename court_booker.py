from playwright.sync_api import sync_playwright
import logging
from dotenv import load_dotenv
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import time

# Configure detailed logging to track the booking process
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# UK timezone for all time calculations
UK_TZ = ZoneInfo('Europe/London')

# Cascading time blocks: try primary first, fall back to next
# Each tuple is (User1_slot, User2_slot)
TIME_BLOCKS = [
    ("11:00", "12:00"),  # Primary:  11am-1pm
    ("12:00", "13:00"),  # Fallback: 12pm-2pm
]


def wait_until_midnight_uk():
    """
    Wait until exactly midnight UK time (Europe/London), then return True.
    
    Handles three scenarios:
      1. Midnight is in the future and <= 75 minutes away: wait for it.
         (75 min covers both cron triggers during GMT + GitHub cron delays of ~30 min)
      2. Midnight JUST passed (within the last 10 minutes): proceed immediately.
         (handles GitHub delays that push the trigger past midnight)
      3. Otherwise: wrong cron trigger for this timezone period, return False.
    
    Uses coarse sleeping until the last 5 seconds, then tight polling for
    sub-200ms precision at the midnight boundary.
    """
    now_uk = datetime.now(UK_TZ)
    
    # Calculate today's midnight and tomorrow's midnight
    today_midnight = now_uk.replace(hour=0, minute=0, second=0, microsecond=0)
    next_midnight = today_midnight + timedelta(days=1)
    
    # How long since today's midnight, and how long until next midnight
    secs_since_midnight = (now_uk - today_midnight).total_seconds()
    secs_until_midnight = (next_midnight - now_uk).total_seconds()
    
    logging.info(f"Current UK time: {now_uk.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    logging.info(f"Seconds since today's midnight: {secs_since_midnight:.1f} ({secs_since_midnight/60:.1f} min)")
    logging.info(f"Seconds until next midnight: {secs_until_midnight:.1f} ({secs_until_midnight/60:.1f} min)")
    
    # Case 1: Midnight JUST passed (within 10 minutes ago) - proceed immediately
    if secs_since_midnight <= 600:
        logging.info(f"Midnight was {secs_since_midnight:.0f}s ago (within 10 min). Proceeding immediately!")
        return True
    
    # Case 2: Midnight is coming up within 75 minutes - wait for it
    if secs_until_midnight <= 4500:  # 75 minutes
        logging.info(f"Midnight is {secs_until_midnight:.0f}s away ({secs_until_midnight/60:.1f} min). Waiting...")
        
        # Coarse sleep in chunks, then tight poll for the last 5 seconds
        while True:
            remaining = (next_midnight - datetime.now(UK_TZ)).total_seconds()
            if remaining <= 0:
                break
            if remaining > 5:
                sleep_time = min(remaining - 3, 10)  # Sleep in 10s chunks max, leave 3s buffer
                time.sleep(sleep_time)
            else:
                time.sleep(0.05)  # 50ms tight polling for final seconds
        
        actual_time = datetime.now(UK_TZ)
        logging.info(f"Midnight reached! Actual UK time: {actual_time.strftime('%H:%M:%S.%f')}")
        return True
    
    # Case 3: Too far from midnight in either direction - wrong trigger
    logging.info("Midnight is not within the valid window (past 10 min or next 75 min). Wrong cron trigger.")
    return False


def calculate_booking_date():
    """
    Calculates a booking date exactly two weeks from today in UK time.
    
    Called after midnight Saturday UK time, so datetime.now(UK_TZ) gives Saturday.
    Two weeks from Saturday = the target Saturday for booking.
    
    Returns:
        datetime: The booking date (naive datetime for URL formatting)
    """
    uk_now = datetime.now(UK_TZ)
    
    # Use today's date at midnight as the base
    base_date = uk_now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    # If we're running on Friday night before midnight (shouldn't happen after wait,
    # but handle for test mode), advance to Saturday
    if base_date.weekday() == 4:  # Friday
        base_date += timedelta(days=1)
    
    booking_date = base_date + timedelta(weeks=2)
    
    # Return as naive datetime (strip tzinfo) for URL formatting
    booking_date_naive = booking_date.replace(tzinfo=None)
    
    logging.info(f"Date calculation:")
    logging.info(f"  UK time now: {uk_now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    logging.info(f"  Base date: {base_date.strftime('%Y-%m-%d (%A)')}")
    logging.info(f"  Booking date (2 weeks out): {booking_date_naive.strftime('%Y-%m-%d (%A)')}")
    
    return booking_date_naive


def handle_cookie_consent(page):
    """
    Handles the cookie consent banner if it appears on the page.
    Returns after accepting cookies or if no banner is found.
    """
    try:
        accept_button = page.get_by_role("button", name="Accept All")
        if accept_button.is_visible():
            logging.info("Accepting cookies...")
            accept_button.click()
            page.wait_for_timeout(500)
    except Exception as e:
        logging.warning(f"Cookie consent handling: {str(e)}")


def perform_login(page, username, password):
    """
    Perform the LTA login flow on the given page.
    Raises Exception if login fails.
    """
    logging.info("Starting login process...")
    page.wait_for_load_state('networkidle')
    
    page.screenshot(path=f"pre-login-{datetime.now().strftime('%Y%m%d-%H%M%S')}.png")
    
    logging.info("Clicking LTA login button...")
    lta_login_button = page.locator('button[name="idp"][value="LTA2"]')
    if not lta_login_button.is_visible(timeout=5000):
        page.screenshot(path=f"no-login-button-{datetime.now().strftime('%Y%m%d-%H%M%S')}.png")
        raise Exception("Login button not visible")
    
    lta_login_button.click()
    
    # Wait for login form to load
    page.wait_for_load_state('networkidle')
    page.wait_for_timeout(1000)
    
    page.screenshot(path=f"login-form-{datetime.now().strftime('%Y%m%d-%H%M%S')}.png")
    
    logging.info("Entering login credentials...")
    username_input = page.locator('input[placeholder="Username"]')
    if not username_input.is_visible(timeout=5000):
        page.screenshot(path=f"no-username-field-{datetime.now().strftime('%Y%m%d-%H%M%S')}.png")
        raise Exception("Username field not visible")
    
    username_input.fill(username)
    page.wait_for_timeout(300)
    
    password_input = page.locator('input[placeholder="Password"]')
    if not password_input.is_visible(timeout=5000):
        page.screenshot(path=f"no-password-field-{datetime.now().strftime('%Y%m%d-%H%M%S')}.png")
        raise Exception("Password field not visible")
    
    password_input.fill(password)
    page.wait_for_timeout(300)
    
    page.screenshot(path=f"pre-submit-{datetime.now().strftime('%Y%m%d-%H%M%S')}.png")
    
    logging.info("Submitting login form...")
    login_button = page.get_by_role("button", name="Log in")
    if not login_button.is_visible(timeout=5000):
        page.screenshot(path=f"no-submit-button-{datetime.now().strftime('%Y%m%d-%H%M%S')}.png")
        raise Exception("Submit button not visible")
    
    login_button.click()
    
    # Wait for login to complete
    page.wait_for_load_state('networkidle')
    page.wait_for_timeout(1000)
    
    page.screenshot(path=f"post-login-{datetime.now().strftime('%Y%m%d-%H%M%S')}.png")
    
    # Verify login success - if we still see the login button, login failed
    if page.locator('button[name="idp"][value="LTA2"]').is_visible(timeout=2000):
        page.screenshot(path=f"login-failed-{datetime.now().strftime('%Y%m%d-%H%M%S')}.png")
        raise Exception("Login failed - still on login page. Check credentials are correct and not wrapped in quotes.")
    
    logging.info("Login successful")


def setup_and_login(username_env_var, password_env_var):
    """
    Pre-warm phase: Start a Playwright browser, navigate to the booking site,
    and log in. Returns (playwright_instance, browser, page) tuple.
    
    Uses sync_playwright().start() instead of context manager so the session
    persists for later use.
    
    Raises Exception if credentials are missing or login fails.
    """
    username = os.getenv(username_env_var)
    password = os.getenv(password_env_var)
    
    if not username or not password:
        raise Exception(f"Missing credentials for {username_env_var}")
    
    logging.info(f"Setting up browser session for {username_env_var}...")
    
    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=True)  # No slow_mo - speed is critical
    context = browser.new_context()
    page = context.new_page()
    
    # Navigate to booking site and log in
    base_url = os.getenv('BOOKING_URL', 'https://telfordparktennisclub.co.uk')
    login_url = f"{base_url}/Booking/BookByDate"
    logging.info(f"Navigating to {login_url}")
    page.goto(login_url)
    
    handle_cookie_consent(page)
    perform_login(page, username, password)
    
    logging.info(f"Session ready for {username_env_var}")
    return pw, browser, page


def cleanup_session(pw, browser):
    """Safely close browser and stop Playwright."""
    try:
        if browser:
            browser.close()
    except Exception as e:
        logging.warning(f"Error closing browser: {e}")
    try:
        if pw:
            pw.stop()
    except Exception as e:
        logging.warning(f"Error stopping playwright: {e}")


def navigate_to_correct_date(page, target_date):
    """
    Navigates to the correct booking date by modifying the URL directly.
    Handles potential authentication loss during navigation.
    Returns True if successfully navigated to the date.
    """
    logging.info(f"Navigating to date: {target_date.strftime('%Y-%m-%d')}")
    
    try:
        formatted_date = target_date.strftime('%Y-%m-%d')
        
        page.screenshot(path=f"pre-navigation-{datetime.now().strftime('%Y%m%d-%H%M%S')}.png")
        
        # Brief wait for page stability
        page.wait_for_load_state('networkidle')
        page.wait_for_timeout(500)
        
        # Navigate directly to the date using the full URL
        base_url = os.getenv('BOOKING_URL', 'https://telfordparktennisclub.co.uk')
        full_url = f"{base_url}/Booking/BookByDate#?date={formatted_date}&role=member"
        
        page.goto(full_url, wait_until='networkidle')
        page.wait_for_timeout(1000)
        
        page.screenshot(path=f"post-navigation-initial-{datetime.now().strftime('%Y%m%d-%H%M%S')}.png")
        
        # Check if we're still on the login page (session expired)
        login_button = page.locator('button[name="idp"][value="LTA2"]')
        if login_button.is_visible(timeout=2000):
            logging.warning("Still on login page after navigation, session might be lost")
            return False
            
        # Wait for the booking sheet to be visible
        booking_sheet = page.locator('.booking-sheet')
        if not booking_sheet.is_visible(timeout=10000):
            logging.error("Booking sheet not visible after navigation")
            page.screenshot(path=f"no-booking-sheet-{datetime.now().strftime('%Y%m%d-%H%M%S')}.png")
            return False
            
        page.screenshot(path=f"post-navigation-final-{datetime.now().strftime('%Y%m%d-%H%M%S')}.png")
        
        # Verify we're on the correct date
        current_url = page.url
        if formatted_date in current_url and booking_sheet.is_visible():
            logging.info(f"Successfully navigated to date {formatted_date}")
            return True
        else:
            logging.error(f"Navigation failed - URL doesn't contain target date. Current URL: {current_url}")
            return False
            
    except Exception as e:
        logging.error(f"Error navigating to date: {str(e)}")
        page.screenshot(path=f"navigation-error-{datetime.now().strftime('%Y%m%d-%H%M%S')}.png")
        return False


def find_and_select_court(page, formatted_date, time_slot, preferred_court=None):
    """
    Attempts to find and book a court for the specified time slot.
    If preferred_court is specified, tries that court first.
    Then checks courts in order of preference: 5, 4, 3, 2, 1
    Returns (success, booking_details) tuple.
    """
    # Convert time (e.g., "11:00") to minutes since midnight for the booking system
    hour = int(time_slot.split(':')[0])
    minutes_since_midnight = hour * 60
    
    logging.info(f"Starting court selection for {time_slot} slot...")
    if preferred_court:
        logging.info(f"Will try {preferred_court} first (same court as first booking)")
    
    booking_details = {
        'time': time_slot,
        'date': formatted_date,
        'courts_checked': [],
        'booked_court': None,
        'status': 'Failed'
    }
    
    try:
        # Define courts in order of preference
        standard_courts = [
            ('Court 5', '7669fa63-1862-48a6-98ac-59527ed398f9'),
            ('Court 4', '8cce54b0-bef5-4258-a732-6c20bed0953c'),
            ('Court 3', '3af2c6ce-1577-45c4-9cd3-764bb6f3f0f8'),
            ('Court 2', '0ba85731-b946-4101-9427-c9ed310ad8b9'),
            ('Court 1', 'e541557c-c72f-4cef-adb3-285b2bf99f02')
        ]
        
        # Build ordered list: preferred court first, then remaining in standard order
        courts_to_try = []
        if preferred_court:
            preferred_court_details = next((c for c in standard_courts if c[0] == preferred_court), None)
            if preferred_court_details:
                courts_to_try.append(preferred_court_details)
        
        courts_to_try.extend([c for c in standard_courts if c[0] not in [ct[0] for ct in courts_to_try]])
        
        for court_name, court_id in courts_to_try:
            booking_details['courts_checked'].append(court_name)
            logging.info(f"Checking {court_name} availability...")
            
            try:
                # Look for the booking link for the specified time
                booking_selector = (
                    f'a.book-interval.not-booked[data-test-id='
                    f'"booking-{court_id}|{formatted_date}|{minutes_since_midnight}"]'
                )
                
                booking_element = page.locator(booking_selector)
                
                if booking_element.is_visible():
                    logging.info(f"{court_name} is available! Attempting to book...")
                    booking_element.click()
                    
                    # Wait for booking dialog
                    page.wait_for_selector('text="Make a booking"', timeout=5000)
                    logging.info("Booking dialog opened")
                    
                    # Click continue booking
                    continue_button = page.get_by_text("Continue booking")
                    if continue_button.is_visible():
                        logging.info(f"Confirming booking for {court_name}")
                        continue_button.click()
                        
                        # Wait for the booking details page
                        page.wait_for_timeout(1000)
                        
                        # Click the final confirm button
                        confirm_button = page.get_by_role("button", name="Confirm")
                        if confirm_button.is_visible():
                            logging.info("Clicking final confirm button...")
                            confirm_button.click()
                            
                            # Wait for confirmation
                            page.wait_for_timeout(1000)
                            booking_details['booked_court'] = court_name
                            booking_details['status'] = 'Success'
                            return True, booking_details
                        else:
                            logging.warning("Final confirm button not visible")
                    else:
                        logging.warning("Continue booking button not visible")
                else:
                    logging.info(f"{court_name} not available at {time_slot}")
                    
            except Exception as e:
                logging.warning(f"Error checking {court_name}: {str(e)}")
                continue
        
        logging.info(f"No courts available for booking at {time_slot}")
        return False, booking_details
        
    except Exception as e:
        logging.error(f"Error during court selection: {str(e)}")
        page.screenshot(path=f"error-booking-{datetime.now().strftime('%Y%m%d-%H%M%S')}.png")
        return False, booking_details


def write_results(booking_results_list, block_used, error=None):
    """
    Write booking results to file for the GitHub Action to read.
    Reports which time block was used and the outcome of each booking.
    """
    booked = [r for r in booking_results_list if r.get('status') == 'Success']
    
    with open('booking_results.txt', 'w') as f:
        f.write("Sport Court Booking Results\n")
        f.write("=" * 40 + "\n\n")
        
        if error:
            f.write(f"Error: {error}\n\n")
        
        # Summary line
        if len(booked) == 2:
            times = f"{booked[0]['time']} + {booked[1]['time']}"
            same_court = booked[0].get('booked_court') == booked[1].get('booked_court')
            court_info = f"on {booked[0]['booked_court']}" if same_court else f"on {booked[0]['booked_court']} and {booked[1]['booked_court']}"
            block_info = f" ({block_used} block)" if block_used else ""
            f.write(f"Summary: Successfully booked 2-hour session ({times}) {court_info}{block_info}\n\n")
        elif len(booked) == 1:
            block_info = f" ({block_used} block)" if block_used else ""
            f.write(f"Summary: Partial booking - {booked[0]['time']} on {booked[0].get('booked_court', '?')}{block_info}\n\n")
        else:
            f.write("Summary: No bookings made\n\n")
        
        # Time block info
        if block_used:
            for first_slot, second_slot in TIME_BLOCKS:
                if first_slot == (booked[0]['time'] if booked else None):
                    f.write(f"Time block used: {block_used} ({first_slot} + {second_slot})\n\n")
                    break
        
        # Individual booking details
        f.write("Booking Details:\n")
        f.write("-" * 40 + "\n")
        for result in booking_results_list:
            f.write(f"LTA Username: {result.get('actual_username', 'Unknown')}\n")
            f.write(f"Date: {result.get('date', 'N/A')}\n")
            f.write(f"Time: {result.get('time', 'N/A')}\n")
            f.write(f"Status: {result.get('status', 'Unknown')}\n")
            if result.get('booked_court'):
                f.write(f"Booked Court: {result['booked_court']}\n")
            elif result.get('courts_checked'):
                f.write(f"Courts checked but unavailable: {', '.join(result['courts_checked'])}\n")
            if result.get('error'):
                f.write(f"Error: {result['error']}\n")
            f.write("\n")
    
    logging.info("Results written to booking_results.txt")


def main():
    """
    Main function that coordinates the booking process:
    
    1. Pre-warm: Log in User1 before midnight (while waiting for runner is free time)
    2. Wait: Poll until exactly midnight UK time
    3. Book: Navigate to date and try cascading time blocks
       - Primary block: 11:00 (User1) + 12:00 (User2)
       - Fallback block: 12:00 (User1) + 13:00 (User2)
    4. Report: Write results and exit
    """
    load_dotenv()
    
    test_mode = os.getenv('TEST_MODE', 'false').lower() == 'true'
    trigger_event = os.getenv('TRIGGER_EVENT', 'unknown')
    is_manual = trigger_event == 'workflow_dispatch'
    skip_midnight_wait = test_mode or is_manual
    
    logging.info(f"Trigger event: {trigger_event}, Test mode: {test_mode}, Manual: {is_manual}")
    
    booking_results_list = []
    block_used = None
    pw1, browser1, page1 = None, None, None
    
    try:
        # ================================================================
        # Phase 1: Pre-warm User1 session (before midnight)
        # ================================================================
        logging.info("=" * 60)
        logging.info("PHASE 1: Pre-warming User1 session")
        logging.info("=" * 60)
        
        try:
            pw1, browser1, page1 = setup_and_login('LTA_USERNAME', 'LTA_PASSWORD')
        except Exception as e:
            logging.error(f"Failed to pre-warm User1 session: {e}")
            write_results([], None, error=f"User1 pre-warm failed: {e}")
            return
        
        # ================================================================
        # Phase 2: Wait for midnight UK time (scheduled runs only)
        # ================================================================
        if not skip_midnight_wait:
            logging.info("=" * 60)
            logging.info("PHASE 2: Waiting for midnight UK time")
            logging.info("=" * 60)
            
            if not wait_until_midnight_uk():
                logging.info("Wrong cron trigger for current timezone period. Exiting cleanly.")
                cleanup_session(pw1, browser1)
                pw1, browser1, page1 = None, None, None
                write_results([], None, error="Wrong cron trigger - midnight UK is not within the valid window.")
                return
            
            logging.info("*** MIDNIGHT REACHED - GO GO GO! ***")
        else:
            reason = "TEST MODE" if test_mode else "MANUAL DISPATCH"
            logging.info(f"*** {reason} - Skipping midnight wait, booking immediately ***")
        
        # ================================================================
        # Phase 3: Book courts with cascading time blocks
        # ================================================================
        logging.info("=" * 60)
        logging.info("PHASE 3: Booking courts")
        logging.info("=" * 60)
        
        booking_date = calculate_booking_date()
        formatted_date = booking_date.strftime('%Y-%m-%d')
        
        # Navigate User1 to the target booking date
        logging.info("Navigating User1 to booking date...")
        if not navigate_to_correct_date(page1, booking_date):
            # Session may have expired during midnight wait - try re-login
            login_btn = page1.locator('button[name="idp"][value="LTA2"]')
            if login_btn.is_visible(timeout=2000):
                logging.warning("Session expired during wait. Re-authenticating User1...")
                username = os.getenv('LTA_USERNAME')
                password = os.getenv('LTA_PASSWORD')
                perform_login(page1, username, password)
                if not navigate_to_correct_date(page1, booking_date):
                    raise Exception("Failed to navigate to booking date after re-authentication")
            else:
                raise Exception("Failed to navigate User1 to booking date")
        
        # Try cascading time blocks for User1
        first_booking_result = None
        
        for block_idx, (first_slot, second_slot) in enumerate(TIME_BLOCKS):
            block_label = "primary" if block_idx == 0 else "fallback"
            logging.info(f"--- Trying {block_label} block: {first_slot} + {second_slot} ---")
            
            # Try User1 at the first slot of this block
            success, details = find_and_select_court(page1, formatted_date, first_slot)
            details['actual_username'] = os.getenv('LTA_USERNAME', 'Unknown')
            details['error'] = None
            booking_results_list.append(details)
            
            if success:
                first_booking_result = details
                block_used = block_label
                logging.info(f"User1 booked {first_slot} on {details['booked_court']}!")
                break
            
            logging.info(f"{block_label} block: {first_slot} not available. Moving to next block...")
            
            # Reload the page before trying next time block to clear any stale state
            if block_idx < len(TIME_BLOCKS) - 1:
                page1.reload(wait_until='networkidle')
                page1.wait_for_timeout(500)
        
        # Clean up User1 session - booking complete or all blocks exhausted
        cleanup_session(pw1, browser1)
        pw1, browser1, page1 = None, None, None
        
        # ================================================================
        # Phase 4: Book User2 for the second slot (if User1 succeeded)
        # ================================================================
        if first_booking_result and first_booking_result['status'] == 'Success':
            # Find the matching second slot for the block that worked
            user2_slot = None
            for first_slot, second_slot in TIME_BLOCKS:
                if first_slot == first_booking_result['time']:
                    user2_slot = second_slot
                    break
            
            if user2_slot:
                logging.info("=" * 60)
                logging.info(f"PHASE 4: Booking User2 at {user2_slot}")
                logging.info("=" * 60)
                
                pw2, browser2, page2 = None, None, None
                
                try:
                    pw2, browser2, page2 = setup_and_login('LTA_USERNAME2', 'LTA_PASSWORD2')
                    
                    if navigate_to_correct_date(page2, booking_date):
                        success2, details2 = find_and_select_court(
                            page2, formatted_date, user2_slot,
                            preferred_court=first_booking_result.get('booked_court')
                        )
                        details2['actual_username'] = os.getenv('LTA_USERNAME2', 'Unknown')
                        details2['error'] = None
                        booking_results_list.append(details2)
                        
                        if success2:
                            logging.info(f"User2 booked {user2_slot} on {details2['booked_court']}!")
                        else:
                            logging.error(f"User2 could not book any court at {user2_slot}")
                            page2.screenshot(path=f"no-courts-user2-{datetime.now().strftime('%Y%m%d-%H%M%S')}.png")
                    else:
                        logging.error("Failed to navigate User2 to booking date")
                        booking_results_list.append({
                            'actual_username': os.getenv('LTA_USERNAME2', 'Unknown'),
                            'time': user2_slot,
                            'date': formatted_date,
                            'status': 'Failed',
                            'error': 'Navigation to booking date failed',
                            'courts_checked': [],
                            'booked_court': None
                        })
                except Exception as e:
                    logging.error(f"Error booking User2: {e}")
                    booking_results_list.append({
                        'actual_username': os.getenv('LTA_USERNAME2', 'Unknown'),
                        'time': user2_slot,
                        'date': formatted_date,
                        'status': 'Failed',
                        'error': str(e),
                        'courts_checked': [],
                        'booked_court': None
                    })
                finally:
                    cleanup_session(pw2, browser2)
        else:
            logging.error("User1 could not book any slot in any time block. Skipping User2.")
        
        # ================================================================
        # Write results
        # ================================================================
        write_results(booking_results_list, block_used)
        
    except Exception as e:
        logging.error(f"Fatal error in main: {e}")
        write_results(booking_results_list, block_used, error=str(e))
    finally:
        # Ensure cleanup in case of unexpected exit
        if pw1:
            cleanup_session(pw1, browser1)


if __name__ == "__main__":
    main()
