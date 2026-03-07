from playwright.sync_api import sync_playwright
import logging
from dotenv import load_dotenv
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import time
from concurrent.futures import ProcessPoolExecutor, as_completed

# Configure detailed logging to track the booking process
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# UK timezone for all time calculations
UK_TZ = ZoneInfo('Europe/London')


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


def perform_login(page, username, password, user_label=""):
    """
    Perform the LTA login flow on the given page.
    Raises Exception if login fails.
    """
    logging.info(f"[{user_label}] Starting login process...")
    page.wait_for_load_state('networkidle')
    
    page.screenshot(path=f"pre-login-{user_label}.png")
    
    logging.info(f"[{user_label}] Clicking LTA login button...")
    lta_login_button = page.locator('button[name="idp"][value="LTA2"]')
    if not lta_login_button.is_visible(timeout=5000):
        page.screenshot(path=f"no-login-button-{user_label}.png")
        raise Exception("Login button not visible")
    
    lta_login_button.click()
    
    # Wait for login form to load
    page.wait_for_load_state('networkidle')
    page.wait_for_timeout(1000)
    
    page.screenshot(path=f"login-form-{user_label}.png")
    
    logging.info(f"[{user_label}] Entering login credentials...")
    username_input = page.locator('input[placeholder="Username"]')
    if not username_input.is_visible(timeout=5000):
        page.screenshot(path=f"no-username-field-{user_label}.png")
        raise Exception("Username field not visible")
    
    username_input.fill(username)
    page.wait_for_timeout(300)
    
    password_input = page.locator('input[placeholder="Password"]')
    if not password_input.is_visible(timeout=5000):
        page.screenshot(path=f"no-password-field-{user_label}.png")
        raise Exception("Password field not visible")
    
    password_input.fill(password)
    page.wait_for_timeout(300)
    
    page.screenshot(path=f"pre-submit-{user_label}.png")
    
    logging.info(f"[{user_label}] Submitting login form...")
    login_button = page.get_by_role("button", name="Log in")
    if not login_button.is_visible(timeout=5000):
        page.screenshot(path=f"no-submit-button-{user_label}.png")
        raise Exception("Submit button not visible")
    
    login_button.click()
    
    # Wait for login to complete
    page.wait_for_load_state('networkidle')
    page.wait_for_timeout(1000)
    
    page.screenshot(path=f"post-login-{user_label}.png")
    
    # Verify login success - if we still see the login button, login failed
    if page.locator('button[name="idp"][value="LTA2"]').is_visible(timeout=2000):
        page.screenshot(path=f"login-failed-{user_label}.png")
        raise Exception("Login failed - still on login page. Check credentials are correct and not wrapped in quotes.")
    
    logging.info(f"[{user_label}] Login successful")


def navigate_to_correct_date(page, target_date, user_label=""):
    """
    Navigates to the correct booking date with retry logic for reliability.
    
    IMPORTANT: The booking site is an SPA with hash-based routing (#?date=...).
    After login we're already on /Booking/BookByDate, so we MUST use JavaScript
    to change the hash fragment instead of page.goto() — a full HTTP request
    would destroy the authenticated session.
    
    Retries up to 3 times if navigation fails.
    """
    max_retries = 3
    formatted_date = target_date.strftime('%Y-%m-%d')
    target_hash = f"?date={formatted_date}&role=member"

    for attempt in range(max_retries):
        logging.info(f"[{user_label}] Navigation attempt {attempt + 1}/{max_retries} to date: {formatted_date}")
        
        try:
            current_url = page.url
            page.screenshot(path=f"pre-navigation-{user_label}-attempt{attempt+1}.png")
            logging.info(f"[{user_label}] Current URL before navigation: {current_url}")
            
            # Brief wait for page stability
            page.wait_for_load_state('networkidle')
            page.wait_for_timeout(500)
            
            if '/Booking/BookByDate' in current_url:
                # Already on the booking page — use SPA hash navigation to preserve session
                logging.info(f"[{user_label}] On booking page, using hash navigation (preserves session)")
                page.evaluate(f'window.location.hash = "{target_hash}"')
                page.wait_for_timeout(3000)  # Give the SPA time to load the new date
            else:
                # Not on booking page at all — need full navigation
                logging.info(f"[{user_label}] Not on booking page, using full navigation")
                base_url = os.getenv('BOOKING_URL', 'https://telfordparktennisclub.co.uk')
                full_url = f"{base_url}/Booking/BookByDate#{target_hash}"
                page.goto(full_url, wait_until='networkidle')
                page.wait_for_timeout(2000)
            
            page.screenshot(path=f"post-navigation-{user_label}-attempt{attempt+1}.png")
            
            # Check if we ended up on the login page (session lost)
            login_button = page.locator('button[name="idp"][value="LTA2"]')
            if login_button.is_visible(timeout=2000):
                logging.warning(f"[{user_label}] Session lost - login page visible after navigation")
                if attempt < max_retries - 1:
                    logging.info(f"[{user_label}] Retrying navigation...")
                    page.wait_for_timeout(2000)
                    continue
                return False
                
            # Wait for the booking sheet to be visible
            booking_sheet = page.locator('.booking-sheet')
            if not booking_sheet.is_visible(timeout=15000):
                logging.error(f"[{user_label}] Booking sheet not visible after navigation")
                page.screenshot(path=f"no-booking-sheet-{user_label}-attempt{attempt+1}.png")
                if attempt < max_retries - 1:
                    logging.info(f"[{user_label}] Retrying navigation...")
                    page.wait_for_timeout(2000)
                    continue
                return False
                
            # Verify we're on the correct date
            current_url = page.url
            if formatted_date in current_url and booking_sheet.is_visible():
                logging.info(f"[{user_label}] Successfully navigated to date {formatted_date}")
                page.screenshot(path=f"navigation-success-{user_label}.png")
                return True
            else:
                logging.error(f"[{user_label}] Date verification failed. Current URL: {current_url}")
                page.screenshot(path=f"wrong-date-{user_label}-attempt{attempt+1}.png")
                if attempt < max_retries - 1:
                    logging.info(f"[{user_label}] Retrying navigation...")
                    page.wait_for_timeout(2000)
                    continue
                return False
                
        except Exception as e:
            logging.error(f"[{user_label}] Error navigating (attempt {attempt + 1}): {str(e)}")
            page.screenshot(path=f"navigation-error-{user_label}-attempt{attempt+1}.png")
            if attempt < max_retries - 1:
                page.wait_for_timeout(2000)
                continue
            return False
    
    return False


def find_and_select_court(page, formatted_date, time_slot, user_label="", preferred_court=None):
    """
    Attempts to find and book a court for the specified time slot.
    If preferred_court is specified, tries that court first.
    Then checks courts in order of preference: 5, 4, 3, 2, 1
    Returns (success, booking_details) tuple.
    """
    # Convert time (e.g., "11:00") to minutes since midnight for the booking system
    hour = int(time_slot.split(':')[0])
    minutes_since_midnight = hour * 60
    
    logging.info(f"[{user_label}] Starting court selection for {time_slot} slot...")
    if preferred_court:
        logging.info(f"[{user_label}] Will try {preferred_court} first")
    
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
            preferred_court_details = next(
                (c for c in standard_courts if c[0] == preferred_court), None
            )
            if preferred_court_details:
                courts_to_try.append(preferred_court_details)
        
        courts_to_try.extend(
            [c for c in standard_courts if c[0] not in [ct[0] for ct in courts_to_try]]
        )
        
        for court_name, court_id in courts_to_try:
            booking_details['courts_checked'].append(court_name)
            logging.info(f"[{user_label}] Checking {court_name} availability...")
            
            try:
                booking_selector = (
                    f'a.book-interval.not-booked[data-test-id='
                    f'"booking-{court_id}|{formatted_date}|{minutes_since_midnight}"]'
                )
                
                booking_element = page.locator(booking_selector)
                
                if booking_element.is_visible():
                    logging.info(f"[{user_label}] {court_name} is available! Attempting to book...")
                    booking_element.click()
                    
                    # Wait for booking dialog
                    page.wait_for_selector('text="Make a booking"', timeout=5000)
                    logging.info(f"[{user_label}] Booking dialog opened")
                    
                    # Click continue booking
                    continue_button = page.get_by_text("Continue booking")
                    if continue_button.is_visible():
                        logging.info(f"[{user_label}] Confirming booking for {court_name}")
                        continue_button.click()
                        
                        # Wait for the booking details page
                        page.wait_for_timeout(1000)
                        
                        # Click the final confirm button
                        confirm_button = page.get_by_role("button", name="Confirm")
                        if confirm_button.is_visible():
                            logging.info(f"[{user_label}] Clicking final confirm button...")
                            confirm_button.click()
                            
                            # Wait for confirmation
                            page.wait_for_timeout(1000)
                            booking_details['booked_court'] = court_name
                            booking_details['status'] = 'Success'
                            page.screenshot(path=f"booking-confirmed-{user_label}-{court_name}.png")
                            return True, booking_details
                        else:
                            logging.warning(f"[{user_label}] Final confirm button not visible")
                    else:
                        logging.warning(f"[{user_label}] Continue booking button not visible")
                else:
                    logging.info(f"[{user_label}] {court_name} not available at {time_slot}")
                    
            except Exception as e:
                logging.warning(f"[{user_label}] Error checking {court_name}: {str(e)}")
                continue
        
        logging.info(f"[{user_label}] No courts available for booking at {time_slot}")
        return False, booking_details
        
    except Exception as e:
        logging.error(f"[{user_label}] Error during court selection: {str(e)}")
        page.screenshot(path=f"error-court-selection-{user_label}.png")
        return False, booking_details


def write_results(booking_results_list, error=None):
    """
    Write booking results to file for the GitHub Action to read.
    """
    # Sort results by time slot for consistent output
    booking_results_list.sort(key=lambda x: x.get('time', ''))
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
            court_info = (
                f"on {booked[0]['booked_court']}" if same_court
                else f"on {booked[0]['booked_court']} and {booked[1]['booked_court']}"
            )
            f.write(f"Summary: Successfully booked 2-hour session ({times}) {court_info}\n\n")
        elif len(booked) == 1:
            f.write(
                f"Summary: Partial booking - {booked[0]['time']} on "
                f"{booked[0].get('booked_court', '?')}\n\n"
            )
        else:
            f.write("Summary: No bookings made\n\n")
        
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


def booking_worker(args):
    """
    Complete booking workflow for a single user, running in its own process.
    
    Each worker independently:
      1. Logs in to the booking site
      2. Waits for midnight UK time (all workers wait in parallel)
      3. Navigates to the booking date
      4. Attempts to book a court
    
    This provides full process isolation - each user gets their own browser
    instance and Playwright server, eliminating any shared-state issues.
    
    Must be defined at module level so it can be pickled by ProcessPoolExecutor.
    """
    username_env, password_env, time_slot, skip_midnight_wait = args
    
    # Load env vars in child process (needed for local .env file testing)
    load_dotenv()
    
    username = os.getenv(username_env)
    password = os.getenv(password_env)
    user_label = username or username_env
    
    result = {
        'actual_username': username or 'Unknown',
        'time': time_slot,
        'date': None,
        'status': 'Failed',
        'error': None,
        'courts_checked': [],
        'booked_court': None,
    }
    
    if not username or not password:
        result['error'] = f'Missing credentials for {username_env}'
        logging.error(f"[{user_label}] {result['error']}")
        return result
    
    pw = None
    browser = None
    
    try:
        # Phase 1: Login (pre-warm before midnight)
        logging.info(f"[{user_label}] Starting browser session...")
        pw = sync_playwright().start()
        browser = pw.chromium.launch(headless=True)
        page = browser.new_context().new_page()
        
        base_url = os.getenv('BOOKING_URL', 'https://telfordparktennisclub.co.uk')
        login_url = f"{base_url}/Booking/BookByDate"
        logging.info(f"[{user_label}] Navigating to {login_url}")
        page.goto(login_url)
        
        handle_cookie_consent(page)
        perform_login(page, username, password, user_label)
        logging.info(f"[{user_label}] Session pre-warmed and ready")
        
        # Phase 2: Wait for midnight (all workers wait in parallel)
        if not skip_midnight_wait:
            logging.info(f"[{user_label}] Waiting for midnight UK time...")
            if not wait_until_midnight_uk():
                result['error'] = 'Wrong cron trigger - midnight UK not in valid window'
                logging.info(f"[{user_label}] {result['error']}")
                return result
            logging.info(f"[{user_label}] *** MIDNIGHT - GO! ***")
        else:
            logging.info(f"[{user_label}] Skipping midnight wait (test/manual mode)")
        
        # Phase 3: Navigate to booking date
        booking_date = calculate_booking_date()
        formatted_date = booking_date.strftime('%Y-%m-%d')
        result['date'] = formatted_date
        
        logging.info(f"[{user_label}] Navigating to booking date {formatted_date}...")
        if not navigate_to_correct_date(page, booking_date, user_label):
            # Session may have expired during midnight wait - try full re-login
            logging.warning(f"[{user_label}] Navigation failed. Attempting full re-login...")
            
            # Reload the base booking page to get a clean login state
            base_url = os.getenv('BOOKING_URL', 'https://telfordparktennisclub.co.uk')
            page.goto(f"{base_url}/Booking/BookByDate", wait_until='networkidle')
            page.wait_for_timeout(1000)
            
            login_btn = page.locator('button[name="idp"][value="LTA2"]')
            if login_btn.is_visible(timeout=3000):
                logging.info(f"[{user_label}] Login page found. Re-authenticating...")
                handle_cookie_consent(page)
                perform_login(page, username, password, user_label)
                if not navigate_to_correct_date(page, booking_date, user_label):
                    raise Exception("Navigation to booking date failed after re-authentication")
            else:
                # Not on login page but navigation still failed — might be a different error
                raise Exception("Navigation to booking date failed and no login page found")
        
        # Phase 4: Book a court
        success, details = find_and_select_court(page, formatted_date, time_slot, user_label)
        result.update(details)
        result['actual_username'] = username  # Restore after update
        
        if success:
            result['status'] = 'Success'
            logging.info(f"[{user_label}] Successfully booked {time_slot} on {details.get('booked_court')}!")
        else:
            logging.error(f"[{user_label}] Could not book any court for {time_slot}")
            page.screenshot(path=f"no-courts-{user_label}.png")
        
        return result
        
    except Exception as e:
        logging.error(f"[{user_label}] Error: {str(e)}")
        result['error'] = str(e)
        return result
    finally:
        try:
            if browser:
                browser.close()
        except Exception:
            pass
        try:
            if pw:
                pw.stop()
        except Exception:
            pass


def main():
    """
    Main function that coordinates booking for two users in parallel.
    
    Architecture:
      - Two separate processes run simultaneously via ProcessPoolExecutor
      - Each process handles one user's complete flow independently:
        1. Login (pre-warm session before midnight)
        2. Wait for midnight UK time (both wait in parallel)
        3. Navigate to booking date (both go at the same instant)
        4. Book a court
      - Results are collected and written as a single summary
    
    This parallel approach ensures:
      - Full process isolation (separate browsers, no shared state)
      - Both users book at the same instant after midnight
      - If one user fails, the other is completely unaffected
    """
    load_dotenv()
    
    test_mode = os.getenv('TEST_MODE', 'false').lower() == 'true'
    trigger_event = os.getenv('TRIGGER_EVENT', 'unknown')
    is_manual = trigger_event == 'workflow_dispatch'
    skip_midnight_wait = test_mode or is_manual
    
    logging.info(f"Trigger event: {trigger_event}, Test mode: {test_mode}, Manual: {is_manual}")
    
    if skip_midnight_wait:
        reason = "TEST MODE" if test_mode else "MANUAL DISPATCH"
        logging.info(f"*** {reason} - Will skip midnight wait, booking immediately ***")
    
    # Time slots for each user
    time_slot1 = "11:00"
    time_slot2 = "12:00"
    
    logging.info(f"Booking plan: User1 → {time_slot1}, User2 → {time_slot2} (in parallel)")
    
    # Define booking tasks: (username_env, password_env, time_slot, skip_midnight_wait)
    tasks = [
        ('LTA_USERNAME', 'LTA_PASSWORD', time_slot1, skip_midnight_wait),
        ('LTA_USERNAME2', 'LTA_PASSWORD2', time_slot2, skip_midnight_wait),
    ]
    
    # Run both bookings in parallel using separate processes
    # Each process gets its own Playwright browser for full isolation
    booking_results_list = []
    
    logging.info("=" * 60)
    logging.info("Launching parallel booking workers...")
    logging.info("=" * 60)
    
    with ProcessPoolExecutor(max_workers=2) as executor:
        future_to_task = {
            executor.submit(booking_worker, task): task
            for task in tasks
        }
        for future in as_completed(future_to_task):
            task = future_to_task[future]
            try:
                result = future.result(timeout=600)  # 10-minute timeout per worker
                booking_results_list.append(result)
                logging.info(
                    f"Worker result for {os.getenv(task[0], task[0])}: "
                    f"{result['status']} - {result['time']}"
                )
            except Exception as e:
                logging.error(f"Worker process failed for {task[0]}: {str(e)}")
                booking_results_list.append({
                    'actual_username': os.getenv(task[0], 'Unknown'),
                    'time': task[2],
                    'date': None,
                    'status': 'Failed',
                    'error': f'Process error: {str(e)}',
                    'courts_checked': [],
                    'booked_court': None,
                })
    
    # Write consolidated results
    logging.info("=" * 60)
    logging.info("All workers complete. Writing results...")
    logging.info("=" * 60)
    
    write_results(booking_results_list)


if __name__ == "__main__":
    main()
