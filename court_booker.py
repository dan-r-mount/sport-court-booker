from playwright.sync_api import sync_playwright
import logging
from dotenv import load_dotenv
import os
from datetime import datetime, timedelta
import time
from concurrent.futures import ProcessPoolExecutor, as_completed

# Configure detailed logging to track the booking process
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)


def calculate_booking_date():
    """
    Calculates a booking date exactly two weeks from the effective booking day.
    Script is scheduled for Saturday at midnight UTC (00:00 GMT Saturday),
    but GitHub Actions cron can fire slightly early (late Friday 23:xx UTC).
    Handles both cases for robust date calculation.
    
    Returns:
        datetime: The booking date (always a Saturday, 2 weeks from now)
    """
    current_time = datetime.now()  # UTC on GitHub runner
    base_date_for_calc = current_time

    # Handle edge case: if cron fires slightly before midnight on Friday,
    # treat it as Saturday for the booking date calculation
    if current_time.weekday() == 4 and current_time.hour >= 23:
        logging.info(
            f"Running at {current_time.strftime('%Y-%m-%d %H:%M:%S')} (Friday 23:xx UTC). "
            f"Adjusting base date to Saturday for booking calculation."
        )
        base_date_for_calc = current_time + timedelta(days=1)

    # Normalize to midnight for the two-week calculation
    base_date = base_date_for_calc.replace(hour=0, minute=0, second=0, microsecond=0)
    booking_date = base_date + timedelta(weeks=2)
    
    logging.info(f"""
    Date calculation details:
    Actual current time (UTC on runner): {current_time.strftime('%Y-%m-%d %H:%M:%S')}
    Base date used for calculation (normalized to midnight): {base_date.strftime('%Y-%m-%d')}
    Target booking date (2 weeks from base): {booking_date.strftime('%Y-%m-%d')}
    """)
    
    return booking_date


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
            page.wait_for_timeout(1000)
    except Exception as e:
        logging.warning(f"Cookie consent handling: {str(e)}")


def navigate_to_correct_date(page, target_date, user_label=""):
    """
    Navigates to the correct booking date with retry logic for reliability.
    Retries up to 3 times if navigation fails.
    """
    max_retries = 3
    formatted_date = target_date.strftime('%Y-%m-%d')

    for attempt in range(max_retries):
        logging.info(f"[{user_label}] Navigation attempt {attempt + 1}/{max_retries} to date: {formatted_date}")
        
        try:
            page.screenshot(path=f"pre-navigation-{user_label}-attempt{attempt+1}.png")
            
            page.wait_for_load_state('networkidle')
            page.wait_for_timeout(2000)
            
            # Navigate directly to the date using the full URL
            base_url = os.getenv('BOOKING_URL', 'https://telfordparktennisclub.co.uk')
            full_url = f"{base_url}/Booking/BookByDate#?date={formatted_date}&role=member"
            
            page.goto(full_url, wait_until='networkidle')
            page.wait_for_timeout(3000)
            
            page.screenshot(path=f"post-navigation-{user_label}-attempt{attempt+1}.png")
            
            # Check if we're still on the login page
            login_button = page.locator('button[name="idp"][value="LTA2"]')
            if login_button.is_visible(timeout=2000):
                logging.warning(f"[{user_label}] Still on login page after navigation, session might be lost")
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
                logging.error(f"[{user_label}] Navigation verification failed. Current URL: {current_url}")
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
        # Define our courts in order of preference
        standard_courts = [
            ('Court 5', '7669fa63-1862-48a6-98ac-59527ed398f9'),
            ('Court 4', '8cce54b0-bef5-4258-a732-6c20bed0953c'),
            ('Court 3', '3af2c6ce-1577-45c4-9cd3-764bb6f3f0f8'),
            ('Court 2', '0ba85731-b946-4101-9427-c9ed310ad8b9'),
            ('Court 1', 'e541557c-c72f-4cef-adb3-285b2bf99f02')
        ]
        
        # If we have a preferred court, try it first
        courts_to_try = []
        if preferred_court:
            preferred_court_details = next(
                (court for court in standard_courts if court[0] == preferred_court), None
            )
            if preferred_court_details:
                courts_to_try.append(preferred_court_details)
        
        # Add remaining courts in standard order
        courts_to_try.extend(
            [court for court in standard_courts if court[0] not in [c[0] for c in courts_to_try]]
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
                        page.wait_for_timeout(2000)
                        
                        # Click the final confirm button
                        confirm_button = page.get_by_role("button", name="Confirm")
                        if confirm_button.is_visible():
                            logging.info(f"[{user_label}] Clicking final confirm button...")
                            confirm_button.click()
                            
                            # Wait for confirmation
                            page.wait_for_timeout(2000)
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


def attempt_booking(username_env_var, password_env_var, time_slot, preferred_court=None):
    """
    Attempts to make a booking for a specific user and time slot.
    Each call creates its own browser instance for full isolation.
    Returns booking details dictionary.
    """
    actual_username = os.getenv(username_env_var, 'Unknown')
    user_label = actual_username  # Use the actual LTA username as label for logs/screenshots
    
    booking_details = {
        'username': username_env_var,
        'actual_username': actual_username,
        'time': time_slot,
        'status': 'Failed',
        'error': None,
        'courts_checked': [],
        'booked_court': None,
        'date': None
    }
    
    # Get login credentials
    username = os.getenv(username_env_var)
    password = os.getenv(password_env_var)
    
    if not username or not password:
        logging.error(f"[{user_label}] Missing credentials for {username_env_var}")
        booking_details['error'] = 'Missing credentials'
        return booking_details

    # Calculate target booking date
    booking_date = calculate_booking_date()

    with sync_playwright() as playwright:
        # Reduced slow_mo from 1000 to 100 for much faster execution
        # while still giving pages time to respond
        browser = playwright.chromium.launch(headless=True, slow_mo=100)
        context = browser.new_context()
        page = context.new_page()
        
        try:
            formatted_date = booking_date.strftime('%Y-%m-%d')
            booking_details['date'] = formatted_date
            
            def perform_login():
                """Helper function to perform login"""
                logging.info(f"[{user_label}] Starting login process...")
                page.wait_for_load_state('networkidle')
                
                page.screenshot(path=f"pre-login-{user_label}.png")
                
                logging.info(f"[{user_label}] Clicking LTA login button...")
                lta_login_button = page.locator('button[name="idp"][value="LTA2"]')
                if not lta_login_button.is_visible(timeout=5000):
                    page.screenshot(path=f"no-login-button-{user_label}.png")
                    raise Exception("Login button not visible")
                
                lta_login_button.click()
                
                # After clicking login button
                page.wait_for_load_state('networkidle')
                page.wait_for_timeout(3000)
                
                page.screenshot(path=f"login-form-{user_label}.png")
                
                logging.info(f"[{user_label}] Entering login credentials...")
                username_input = page.locator('input[placeholder="Username"]')
                if not username_input.is_visible(timeout=5000):
                    page.screenshot(path=f"no-username-field-{user_label}.png")
                    raise Exception("Username field not visible")
                
                username_input.fill(username)
                page.wait_for_timeout(500)
                
                password_input = page.locator('input[placeholder="Password"]')
                if not password_input.is_visible(timeout=5000):
                    page.screenshot(path=f"no-password-field-{user_label}.png")
                    raise Exception("Password field not visible")
                
                password_input.fill(password)
                page.wait_for_timeout(500)
                
                page.screenshot(path=f"pre-submit-{user_label}.png")
                
                logging.info(f"[{user_label}] Submitting login form...")
                login_button = page.get_by_role("button", name="Log in")
                if not login_button.is_visible(timeout=5000):
                    page.screenshot(path=f"no-submit-button-{user_label}.png")
                    raise Exception("Submit button not visible")
                
                login_button.click()
                
                # After submitting credentials
                page.wait_for_load_state('networkidle')
                page.wait_for_timeout(3000)
                
                page.screenshot(path=f"post-login-{user_label}.png")
                
                # Verify login success
                if page.locator('button[name="idp"][value="LTA2"]').is_visible(timeout=2000):
                    page.screenshot(path=f"login-failed-{user_label}.png")
                    raise Exception(
                        "Login failed - still on login page. "
                        "Please check credentials are correct and not wrapped in quotes."
                    )
                
                logging.info(f"[{user_label}] Login successful")
            
            # Start with the base URL for login
            base_url = os.getenv('BOOKING_URL', 'https://telfordparktennisclub.co.uk')
            login_url = f"{base_url}/Booking/BookByDate"
            logging.info(f"[{user_label}] Starting booking attempt for {time_slot}")
            page.goto(login_url)
            
            # Initial login
            perform_login()
            
            # After login completes, navigate to the correct date
            logging.info(f"[{user_label}] Authentication complete, navigating to target date...")
            if not navigate_to_correct_date(page, booking_date, user_label):
                # Check if we need to re-authenticate
                login_button = page.locator('button[name="idp"][value="LTA2"]')
                if login_button.is_visible(timeout=2000):
                    logging.info(f"[{user_label}] Session expired, performing re-authentication...")
                    perform_login()
                    # Try navigation again after re-auth
                    if not navigate_to_correct_date(page, booking_date, user_label):
                        raise Exception("Navigation to booking date failed after re-authentication")
                else:
                    raise Exception("Navigation to booking date failed")
            
            # Now proceed with court selection
            success, court_details = find_and_select_court(
                page, formatted_date, time_slot, user_label, preferred_court
            )
            booking_details.update(court_details)
            
            if success:
                logging.info(f"[{user_label}] Court booking successful for {time_slot}!")
                booking_details['status'] = 'Success'
            else:
                logging.error(f"[{user_label}] Could not book any court for {time_slot}")
                page.screenshot(path=f"no-courts-available-{user_label}.png")
            
            return booking_details
            
        except Exception as e:
            logging.error(f"[{user_label}] An error occurred: {str(e)}")
            page.screenshot(path=f"error-{user_label}.png")
            booking_details['error'] = str(e)
            return booking_details
        finally:
            page.wait_for_timeout(1000)
            browser.close()


def run_booking_task(args):
    """
    Wrapper function for running a booking in a separate process.
    Must be defined at module level so it can be pickled by ProcessPoolExecutor.
    Each process gets its own Playwright instance for full isolation.
    """
    username_env, password_env, time_slot = args
    return attempt_booking(username_env, password_env, time_slot)


def main():
    """
    Main function that coordinates booking attempts for two users in parallel.
    
    Schedule:
    - Saturday: User 1 books 11:00, User 2 books 12:00 (in parallel)
    
    Both users run simultaneously in separate processes, each with their own
    browser instance, for maximum reliability and speed.
    """
    load_dotenv()

    # Get effective booking day and times from environment variables set by the workflow
    env_booking_day = os.getenv('BOOKING_DAY')
    env_time_slot1 = os.getenv('BOOKING_TIME1')
    env_time_slot2 = os.getenv('BOOKING_TIME2')

    use_env_vars = env_booking_day and env_time_slot1 and env_time_slot2

    if use_env_vars:
        day_name_for_logging = env_booking_day
        actual_time_slot1 = env_time_slot1
        actual_time_slot2 = env_time_slot2
        logging.info(f"Using booking config from workflow environment variables:")
        logging.info(f"Day: {day_name_for_logging}, Slot 1: {actual_time_slot1}, Slot 2: {actual_time_slot2}")
    else:
        logging.warning("Booking environment variables not found. Using fallback logic.")
        
        current_date_utc = datetime.now()  # UTC on runner
        py_weekday = current_date_utc.weekday()  # Monday:0, ..., Friday:4, Saturday:5

        # Accept both late Friday (cron fired early) and Saturday
        if py_weekday == 4 and current_date_utc.hour >= 23:
            day_name_for_logging = "Saturday (fallback, running late Friday UTC)"
            actual_time_slot1 = "11:00"
            actual_time_slot2 = "12:00"
        elif py_weekday == 5:  # Saturday
            day_name_for_logging = "Saturday (fallback)"
            actual_time_slot1 = "11:00"
            actual_time_slot2 = "12:00"
        else:
            logging.info(
                f"Fallback: Not a recognized booking day "
                f"(UTC: {current_date_utc.strftime('%A %H:%M')}). No bookings will be attempted."
            )
            with open('booking_results.txt', 'w') as f:
                f.write("Sport Court Booking Results\n")
                f.write("=" * 40 + "\n\n")
                f.write("No booking attempted: Not a recognized booking day.\n")
            return
        logging.info(f"Fallback: {day_name_for_logging}, Slot 1: {actual_time_slot1}, Slot 2: {actual_time_slot2}")

    logging.info(f"--- Running bookings for {day_name_for_logging} ---")
    logging.info(
        f"Booking {actual_time_slot1} (User 1) and {actual_time_slot2} (User 2) "
        f"in parallel with separate accounts and browser instances"
    )

    # Define booking tasks: each user gets their own time slot
    # User 1 (LTA_USERNAME) books the first slot, User 2 (LTA_USERNAME2) books the second
    tasks = [
        ('LTA_USERNAME', 'LTA_PASSWORD', actual_time_slot1),
        ('LTA_USERNAME2', 'LTA_PASSWORD2', actual_time_slot2),
    ]
    
    # Run both bookings in parallel using separate processes
    # Each process gets its own Playwright browser instance for full isolation
    booking_results_list = []
    with ProcessPoolExecutor(max_workers=2) as executor:
        future_to_task = {
            executor.submit(run_booking_task, task): task 
            for task in tasks
        }
        for future in as_completed(future_to_task):
            task = future_to_task[future]
            try:
                result = future.result(timeout=300)  # 5-minute timeout per booking
                booking_results_list.append(result)
                logging.info(
                    f"Booking result for {os.getenv(task[0], task[0])}: "
                    f"{result['status']} - {result['time']}"
                )
            except Exception as e:
                logging.error(f"Booking process failed for {task[0]}: {str(e)}")
                booking_results_list.append({
                    'username': task[0],
                    'actual_username': os.getenv(task[0], 'Unknown'),
                    'time': task[2],
                    'status': 'Failed',
                    'error': f'Process error: {str(e)}',
                    'courts_checked': [],
                    'booked_court': None,
                    'date': None,
                })
    
    # Sort results by time slot for consistent output
    booking_results_list.sort(key=lambda x: x.get('time', ''))
    
    # Determine overall success
    successful_bookings = [r for r in booking_results_list if r['status'] == 'Success']
    
    # Write results to a file for the GitHub Action to read
    with open('booking_results.txt', 'w') as f:
        f.write("Sport Court Booking Results\n")
        f.write("=" * 40 + "\n\n")
        
        if len(successful_bookings) == 2:
            courts = set(r.get('booked_court', 'Unknown') for r in successful_bookings)
            times = ', '.join(r['time'] for r in successful_bookings)
            court_str = ', '.join(courts)
            if len(courts) == 1:
                f.write(f"Summary: Successfully booked 2-hour session ({times}) on {court_str}\n\n")
            else:
                f.write(f"Summary: Successfully booked both slots ({times}) on {court_str}\n\n")
        elif len(successful_bookings) == 1:
            r = successful_bookings[0]
            f.write(
                f"Summary: Partial booking - {r['time']} on "
                f"{r.get('booked_court', 'Unknown')}\n\n"
            )
        else:
            f.write("Summary: No bookings were made\n\n")
        
        f.write("Booking Details:\n")
        f.write("-" * 40 + "\n")
        for result in booking_results_list:
            f.write(f"LTA Username: {result['actual_username']}\n")
            f.write(f"Date: {result['date']}\n")
            f.write(f"Time: {result['time']}\n")
            f.write(f"Status: {result['status']}\n")
            if result['booked_court']:
                f.write(f"Booked Court: {result['booked_court']}\n")
            if result.get('courts_checked'):
                f.write(f"Courts checked: {', '.join(result['courts_checked'])}\n")
            if result['error']:
                f.write(f"Error: {result['error']}\n")
            f.write("\n")


if __name__ == "__main__":
    main()
