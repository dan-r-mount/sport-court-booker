from playwright.sync_api import sync_playwright
import logging
from dotenv import load_dotenv
import os
from datetime import datetime, timedelta
import time

# Configure detailed logging to track the booking process
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def calculate_booking_date():
    """
    Calculates a booking date exactly two weeks from today.
    Uses midnight as the reference time for consistent date calculations.
    """
    current_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    booking_date = current_date + timedelta(weeks=2)
    
    logging.info(f"""
    Date calculation details:
    Current date: {current_date.strftime('%Y-%m-%d')}
    Booking date (2 weeks ahead): {booking_date.strftime('%Y-%m-%d')}
    Days difference: {(booking_date - current_date).days} days
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

def navigate_to_correct_date(page, target_date):
    """
    Navigates to the correct booking date by modifying the URL directly.
    Handles potential authentication loss during navigation.
    """
    logging.info(f"Navigating to date: {target_date.strftime('%Y-%m-%d')}")
    
    try:
        # Format the date for the URL (YYYY-MM-DD)
        formatted_date = target_date.strftime('%Y-%m-%d')
        
        # Take a screenshot before navigation
        page.screenshot(path=f"pre-navigation-{datetime.now().strftime('%Y%m%d-%H%M%S')}.png")
        
        # Add session check before navigation
        page.wait_for_load_state('networkidle')
        page.wait_for_timeout(3000)
        
        # Navigate directly to the date using the full URL
        base_url = os.getenv('BOOKING_URL', 'https://telfordparktennisclub.co.uk')
        full_url = f"{base_url}/Booking/BookByDate#?date={formatted_date}&role=member"
        
        # Use softer navigation
        page.goto(full_url, wait_until='networkidle')
        page.wait_for_timeout(5000)
        
        # Take a screenshot after initial navigation
        page.screenshot(path=f"post-navigation-initial-{datetime.now().strftime('%Y%m%d-%H%M%S')}.png")
        
        # Check if we're still on the login page
        login_button = page.locator('button[name="idp"][value="LTA2"]')
        if login_button.is_visible(timeout=2000):
            logging.warning("Still on login page after navigation, session might be lost")
            return False
            
        # Wait for the booking sheet to be visible (updated selector)
        booking_sheet = page.locator('.booking-sheet')
        if not booking_sheet.is_visible(timeout=10000):
            logging.error("Booking sheet not visible after navigation")
            page.screenshot(path=f"no-booking-sheet-{datetime.now().strftime('%Y%m%d-%H%M%S')}.png")
            return False
            
        # Take a final screenshot
        page.screenshot(path=f"post-navigation-final-{datetime.now().strftime('%Y%m%d-%H%M%S')}.png")
        
        # Verify we're on the correct date by checking URL and content
        current_url = page.url
        if formatted_date in current_url and booking_sheet.is_visible():
            logging.info(f"Successfully navigated to date {formatted_date}")
            return True
        else:
            logging.error(f"Navigation failed - URL doesn't contain target date or booking sheet not visible. Current URL: {current_url}")
            return False
            
    except Exception as e:
        logging.error(f"Error navigating to date: {str(e)}")
        # Take error screenshot
        page.screenshot(path=f"navigation-error-{datetime.now().strftime('%Y%m%d-%H%M%S')}.png")
        return False

def find_and_select_court(page, formatted_date, time_slot, preferred_court=None):
    """
    Attempts to find and book a court for the specified time slot.
    If preferred_court is specified, tries that court first.
    Then checks Court 5, 4, then 3 in order (skipping the preferred if already tried).
    Returns (success, booking_details) tuple.
    """
    # Convert time (e.g., "19:00") to minutes since midnight for the booking system
    hour = int(time_slot.split(':')[0])
    minutes_since_midnight = hour * 60
    
    logging.info(f"Starting court selection process for {time_slot} slot...")
    if preferred_court:
        logging.info(f"Will try {preferred_court} first as it was booked by the first user")
    
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
            ('Court 3', '3af2c6ce-1577-45c4-9cd3-764bb6f3f0f8')
        ]
        
        # If we have a preferred court, try it first
        courts_to_try = []
        if preferred_court:
            # Find the preferred court details
            preferred_court_details = next((court for court in standard_courts if court[0] == preferred_court), None)
            if preferred_court_details:
                courts_to_try.append(preferred_court_details)
        
        # Add remaining courts in standard order (excluding the preferred court if it exists)
        courts_to_try.extend([court for court in standard_courts if court[0] not in [c[0] for c in courts_to_try]])
        
        for court_name, court_id in courts_to_try:
            booking_details['courts_checked'].append(court_name)
            logging.info(f"\nChecking {court_name} availability...")
            
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
                        page.wait_for_timeout(2000)
                        
                        # Click the final confirm button
                        confirm_button = page.get_by_role("button", name="Confirm")
                        if confirm_button.is_visible():
                            logging.info("Clicking final confirm button...")
                            confirm_button.click()
                            
                            # Wait for confirmation
                            page.wait_for_timeout(2000)
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
        
        logging.info(f"\nNo courts available for booking at {time_slot}")
        return False, booking_details
        
    except Exception as e:
        logging.error(f"Error during court selection: {str(e)}")
        page.screenshot(path=f"error-booking-{datetime.now().strftime('%Y%m%d-%H%M%S')}.png")
        return False, booking_details

def attempt_booking(username_env_var, password_env_var, time_slot, preferred_court=None):
    """
    Attempts to make a booking for a specific user and time slot.
    Returns booking details dictionary.
    """
    booking_details = {
        'username': username_env_var,
        'actual_username': os.getenv(username_env_var, 'Unknown'),  # Store actual username
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
        logging.error(f"Missing credentials for {username_env_var}")
        booking_details['error'] = 'Missing credentials'
        return booking_details

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, slow_mo=1000)
        context = browser.new_context()
        page = context.new_page()
        
        try:
            # Calculate target booking date
            booking_date = calculate_booking_date()
            formatted_date = booking_date.strftime('%Y-%m-%d')
            booking_details['date'] = formatted_date
            
            def perform_login():
                """Helper function to perform login"""
                logging.info("Starting login process...")
                page.wait_for_load_state('networkidle')
                
                # Take screenshot before login attempt
                page.screenshot(path=f"pre-login-{datetime.now().strftime('%Y%m%d-%H%M%S')}.png")
                
                logging.info("Clicking LTA login button...")
                lta_login_button = page.locator('button[name="idp"][value="LTA2"]')
                if not lta_login_button.is_visible(timeout=5000):
                    page.screenshot(path=f"no-login-button-{datetime.now().strftime('%Y%m%d-%H%M%S')}.png")
                    raise Exception("Login button not visible")
                
                lta_login_button.click()
                
                # After clicking login button
                page.wait_for_load_state('networkidle')
                page.wait_for_timeout(5000)  # Increased wait time
                
                # Take screenshot of login form
                page.screenshot(path=f"login-form-{datetime.now().strftime('%Y%m%d-%H%M%S')}.png")
                
                logging.info("Entering login credentials...")
                username_input = page.locator('input[placeholder="Username"]')
                if not username_input.is_visible(timeout=5000):
                    page.screenshot(path=f"no-username-field-{datetime.now().strftime('%Y%m%d-%H%M%S')}.png")
                    raise Exception("Username field not visible")
                
                username_input.fill(username)
                page.wait_for_timeout(1000)
                
                password_input = page.locator('input[placeholder="Password"]')
                if not password_input.is_visible(timeout=5000):
                    page.screenshot(path=f"no-password-field-{datetime.now().strftime('%Y%m%d-%H%M%S')}.png")
                    raise Exception("Password field not visible")
                
                password_input.fill(password)
                page.wait_for_timeout(1000)
                
                # Take screenshot before submitting
                page.screenshot(path=f"pre-submit-{datetime.now().strftime('%Y%m%d-%H%M%S')}.png")
                
                logging.info("Submitting login form...")
                login_button = page.get_by_role("button", name="Log in")
                if not login_button.is_visible(timeout=5000):
                    page.screenshot(path=f"no-submit-button-{datetime.now().strftime('%Y%m%d-%H%M%S')}.png")
                    raise Exception("Submit button not visible")
                
                login_button.click()
                
                # After submitting credentials
                page.wait_for_load_state('networkidle')
                page.wait_for_timeout(5000)  # Increased wait time
                
                # Take screenshot after login attempt
                page.screenshot(path=f"post-login-{datetime.now().strftime('%Y%m%d-%H%M%S')}.png")
                
                # Verify login success
                if page.locator('button[name="idp"][value="LTA2"]').is_visible(timeout=2000):
                    page.screenshot(path=f"login-failed-{datetime.now().strftime('%Y%m%d-%H%M%S')}.png")
                    raise Exception("Login failed - still on login page. Please check your credentials are correct and not wrapped in quotes.")
                
                logging.info("Login successful")
            
            # Start with the base URL for login
            base_url = os.getenv('BOOKING_URL', 'https://telfordparktennisclub.co.uk')
            login_url = f"{base_url}/Booking/BookByDate"
            logging.info(f"Starting booking attempt for {username_env_var} at {time_slot}")
            page.goto(login_url)
            
            # Initial login
            perform_login()
            
            # After login completes, navigate to the correct date
            logging.info("Authentication complete, navigating to target date...")
            if not navigate_to_correct_date(page, booking_date):
                # Check if we need to re-authenticate
                login_button = page.locator('button[name="idp"][value="LTA2"]')
                if login_button.is_visible(timeout=2000):
                    logging.info("Session expired, performing re-authentication...")
                    perform_login()
                    # Try navigation again after re-auth
                    if not navigate_to_correct_date(page, booking_date):
                        raise Exception("Failed to navigate to target date after re-authentication")
                else:
                    raise Exception("Failed to navigate to target date")
            
            # Now proceed with court selection
            success, court_details = find_and_select_court(page, formatted_date, time_slot, preferred_court)
            booking_details.update(court_details)
            
            if success:
                logging.info(f"Court booking successful for {username_env_var} at {time_slot}!")
                booking_details['status'] = 'Success'
            else:
                logging.error(f"Could not book any preferred courts for {username_env_var} at {time_slot}")
                page.screenshot(path=f"no-courts-available-{username_env_var}.png")
            
            return booking_details
            
        except Exception as e:
            logging.error(f"An error occurred for {username_env_var}: {str(e)}")
            page.screenshot(path=f"error-{datetime.now().strftime('%Y%m%d-%H%M%S')}.png")
            booking_details['error'] = str(e)
            return booking_details
        finally:
            page.wait_for_timeout(2000)
            browser.close()

def main():
    """
    Main function that coordinates multiple booking attempts.
    Schedule:
    - Thursday: 19:00 and 20:00
    - Saturday: 11:00 and 12:00
    """
    load_dotenv()
    
    # Get current date information
    current_date = datetime.now()
    current_day = current_date.weekday() + 1  # 1-based weekday (1=Monday, 7=Sunday)
    
    # Set time slots based on the day
    if current_day == 6:  # Saturday
        time_slot1 = '11:00'  # 11 AM
        time_slot2 = '12:00'  # 12 PM
        day_name = "Saturday"
    elif current_day == 4:  # Thursday
        time_slot1 = '19:00'  # 7 PM
        time_slot2 = '20:00'  # 8 PM
        day_name = "Thursday"
    else:
        logging.info("Not Thursday or Saturday - no bookings needed")
        return
    
    logging.info(f"Running bookings for {day_name}")
    logging.info(f"Time slots: {time_slot1} and {time_slot2}")
    
    # Store all booking results
    booking_results = []
    
    # First booking attempt
    first_booking = attempt_booking('LTA_USERNAME', 'LTA_PASSWORD', time_slot1)
    booking_results.append(first_booking)
    logging.info(f"First booking attempt result: {first_booking['status']}")
    
    # Get the court that was booked in the first attempt (if successful)
    preferred_court = first_booking.get('booked_court') if first_booking['status'] == 'Success' else None
    if preferred_court:
        logging.info(f"First user booked {preferred_court}, second user will try this court first")
    
    # Add a small delay between attempts
    time.sleep(2)
    
    # Second booking attempt with preferred court information
    second_booking = attempt_booking('LTA_USERNAME2', 'LTA_PASSWORD2', time_slot2, preferred_court)
    booking_results.append(second_booking)
    logging.info(f"Second booking attempt result: {second_booking['status']}")
    
    # Write results to a file for the GitHub Action to read
    with open('booking_results.txt', 'w') as f:
        f.write("Sport Court Booking Results:\n\n")
        for result in booking_results:
            f.write(f"LTA Username: {result['actual_username']}\n")
            f.write(f"Date: {result['date']}\n")
            f.write(f"Time: {result['time']}\n")
            f.write(f"Status: {result['status']}\n")
            if result['booked_court']:
                f.write(f"Booked Court: {result['booked_court']}\n")
            else:
                f.write("Courts checked but unavailable: " + ", ".join(result['courts_checked']) + "\n")
            if result['error']:
                f.write(f"Error: {result['error']}\n")
            f.write("\n")

if __name__ == "__main__":
    main()