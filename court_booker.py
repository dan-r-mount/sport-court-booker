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
    """
    logging.info(f"Navigating to date: {target_date.strftime('%Y-%m-%d')}")
    
    try:
        # Format the date for the URL (YYYY-MM-DD)
        formatted_date = target_date.strftime('%Y-%m-%d')
        
        # Wait for the booking page to be fully loaded first
        page.wait_for_selector('h2.pull-left', timeout=10000)
        page.wait_for_load_state('networkidle')
        page.wait_for_timeout(2000)
        
        # Use evaluate to modify the URL and trigger the date change
        js_code = f"""
        window.location.hash = '?date={formatted_date}&role=member';
        """
        page.evaluate(js_code)
        
        # Wait for the page to update
        page.wait_for_load_state('networkidle')
        page.wait_for_timeout(2000)
        
        # The date has been updated through the URL hash change
        # We'll consider this successful as we saw the date update visually
        return True
            
    except Exception as e:
        logging.error(f"Error navigating to date: {str(e)}")
        page.screenshot(path="date-navigation-error.png")
        return False

def find_and_select_court(page, formatted_date, time_slot):
    """
    Attempts to find and book a court for the specified time slot.
    Checks Court 5 first, then 4, then 3 if necessary.
    """
    # Convert time (e.g., "19:00") to minutes since midnight for the booking system
    hour = int(time_slot.split(':')[0])
    minutes_since_midnight = hour * 60
    
    logging.info(f"Starting court selection process for {time_slot} slot...")
    
    try:
        # Define our courts in order of preference
        courts_to_try = [
            ('Court 5', '7669fa63-1862-48a6-98ac-59527ed398f9'),
            ('Court 4', '8cce54b0-bef5-4258-a732-6c20bed0953c'),
            ('Court 3', '3af2c6ce-1577-45c4-9cd3-764bb6f3f0f8')
        ]
        
        for court_name, court_id in courts_to_try:
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
                            return True
                        else:
                            logging.warning("Final confirm button not visible")
                    else:
                        logging.warning("Continue booking button not visible")
                else:
                    logging.info(f"{court_name} not available at {time_slot}")
                    
            except Exception as e:
                logging.warning(f"Error checking {court_name}: {str(e)}")
                continue
        
        logging.info(f"\nNo preferred courts available for booking at {time_slot}")
        return False
        
    except Exception as e:
        logging.error(f"Error during court selection: {str(e)}")
        page.screenshot(path=f"error-booking-{datetime.now().strftime('%Y%m%d-%H%M%S')}.png")
        return False

def attempt_booking(username_env_var, password_env_var, time_slot):
    """
    Attempts to make a booking for a specific user and time slot.
    """
    # Get login credentials
    username = os.getenv(username_env_var)
    password = os.getenv(password_env_var)
    
    if not username or not password:
        logging.error(f"Missing credentials for {username_env_var}")
        return False

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False, slow_mo=1000)
        context = browser.new_context()
        page = context.new_page()
        
        try:
            # Calculate target booking date
            booking_date = calculate_booking_date()
            formatted_date = booking_date.strftime('%Y-%m-%d')
            
            # Start with the base URL for login
            base_url = "https://telfordparktennisclub.co.uk/Booking/BookByDate"
            logging.info(f"Starting booking attempt for {username_env_var} at {time_slot}")
            page.goto(base_url)
            
            # Handle login process
            logging.info("Starting login process...")
            page.wait_for_load_state('networkidle')
            
            # Click LTA login button
            logging.info("Clicking LTA login button...")
            lta_login_button = page.locator('button[name="idp"][value="LTA2"]')
            lta_login_button.click()
            
            # Enter credentials
            logging.info("Entering login credentials...")
            page.wait_for_load_state('networkidle')
            page.wait_for_timeout(2000)
            
            username_input = page.locator('input[placeholder="Username"]')
            username_input.fill(username)
            page.wait_for_timeout(1000)
            
            password_input = page.locator('input[placeholder="Password"]')
            password_input.fill(password)
            page.wait_for_timeout(1000)
            
            # Submit login
            logging.info("Submitting login form...")
            login_button = page.get_by_role("button", name="Log in")
            login_button.click()
            
            # Wait for login completion
            page.wait_for_load_state('networkidle')
            page.wait_for_timeout(3000)
            
            # After login completes, navigate to the correct date
            logging.info("Authentication complete, navigating to target date...")
            if not navigate_to_correct_date(page, booking_date):
                raise Exception("Failed to navigate to target date")
            
            # Now proceed with court selection
            success = find_and_select_court(page, formatted_date, time_slot)
            if success:
                logging.info(f"Court booking successful for {username_env_var} at {time_slot}!")
            else:
                logging.error(f"Could not book any preferred courts for {username_env_var} at {time_slot}")
                page.screenshot(path=f"no-courts-available-{username_env_var}.png")
            
            return success
            
        except Exception as e:
            logging.error(f"An error occurred for {username_env_var}: {str(e)}")
            page.screenshot(path=f"error-{datetime.now().strftime('%Y%m%d-%H%M%S')}.png")
            return False
        finally:
            page.wait_for_timeout(2000)
            browser.close()

def main():
    """
    Main function that coordinates multiple booking attempts.
    Uses environment variables for time slots which are set by GitHub Actions.
    """
    load_dotenv()
    
    # Get time slots from environment (set by GitHub Actions)
    time_slot1 = os.getenv('BOOKING_TIME1', '19:00')  # Default to 19:00 if not set
    time_slot2 = os.getenv('BOOKING_TIME2', '20:00')  # Default to 20:00 if not set
    
    # Define booking configurations
    booking_configs = [
        {
            'username_env': 'LTA_USERNAME',
            'password_env': 'LTA_PASSWORD',
            'time_slot': time_slot1
        },
        {
            'username_env': 'LTA_USERNAME2',
            'password_env': 'LTA_PASSWORD2',
            'time_slot': time_slot2
        }
    ]
    
    # Attempt bookings for each configuration
    first_booking_court = None
    for config in booking_configs:
        success = attempt_booking(
            config['username_env'],
            config['password_env'],
            config['time_slot']
        )
        logging.info(f"Booking attempt for {config['username_env']} at {config['time_slot']}: {'Success' if success else 'Failed'}")
        # Add a small delay between attempts
        time.sleep(2)

if __name__ == "__main__":
    main()