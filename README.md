# Sport Court Booking Automation

This repository contains an automated system for booking tennis courts at Telford Park Tennis Club. The system uses GitHub Actions to automatically book courts every Saturday for two weeks in advance.

## Schedule

The system runs automatically at the following times:

### Saturday Bookings
- Runs at 11:00 PM UTC Friday (12:00 AM BST/GMT Saturday)
- Attempts 11:00 first; if unavailable, attempts 12:00. At most one booking is made.

## System Design

### Scheduling and Validation
The system uses two mechanisms to ensure bookings happen correctly:

1. **GitHub Actions Cron Schedule**:
   - Determines when the workflow runs
   - Saturday schedule: `cron: '0 23 * * 5'` (11:00 PM UTC Friday / 12:00 AM BST Saturday)

2. **Day Validation Check**:
   - Acts as a secondary safeguard to verify the correct day
   - Sets the appropriate booking times based on the day
   - Handles time zone differences (Friday night UTC = Saturday morning BST)
   - Enables safe manual triggering through the GitHub Actions interface on Saturday only
   - Prevents incorrect bookings if someone modifies the schedule

This dual-layer approach ensures maximum reliability and flexibility, allowing both automated and manual booking attempts.

## Setup

### 1. Create a GitHub Repository
1. Go to [github.com](https://github.com) and sign in (or create an account if you don't have one)
2. Click the "+" icon in the top right corner
3. Select "New repository"
4. Name it something like "sport-court-booker"
5. Make it Public (to enable easier monitoring of GitHub Actions)
6. Click "Create repository"
7. Once created, upload all the files from this project to your new repository:
   - `court_booker.py`
   - `.github/workflows/court-booking.yml`
   - `README.md`

### 2. Configure Repository Secrets
1. In your new repository, click on "Settings" (top navigation bar)
2. In the left sidebar, click on "Secrets and variables"
3. Select "Actions"
4. Click the "New repository secret" button
5. Add each of these secrets one by one:

   #### LTA Credentials
   - `LTA_USERNAME`: First user's LTA username
   - `LTA_PASSWORD`: First user's LTA password
   - `LTA_USERNAME2`: Second user's LTA username
   - `LTA_PASSWORD2`: Second user's LTA password

   #### Email Notification Settings
   - `EMAIL_USERNAME`: Gmail address to send notifications from
   - `EMAIL_PASSWORD`: Gmail app password (not your regular password)
   - `NOTIFICATION_EMAILS`: Comma-separated list of email addresses to receive notifications (e.g., `user1@example.com,user2@example.com`)

   #### Setting up Gmail App Password:
   1. Go to your Google Account settings
   2. Navigate to Security
   3. Under "Signing in to Google," select 2-Step Verification
   4. At the bottom of the page, select "App passwords"
   5. Generate a new app password for "Mail"
   6. Use this generated password for the `EMAIL_PASSWORD` secret

### 3. Enable GitHub Actions
1. Go to the "Actions" tab in your repository
2. You should see the "Sport Court Booking" workflow
3. Click "Enable workflow"

The GitHub Actions workflow will now automatically run at the scheduled time with a random delay between 10 and 30 seconds for the actual booking attempt.

## Email Notifications

After each run (successful or failed), the system will send an email containing:
- The day of booking (Saturday)
- A summary line indicating which hour was booked (11:00 or 12:00), or that no booking was made
- The date that the court has been booked for
- The court number that has been booked (if applicable)
- The actual LTA username that booked the court
- If any courts couldn't be booked, which courts were considered

## Manual Trigger

You can also trigger the booking process manually:
1. Go to the "Actions" tab in your repository
2. Select the "Sport Court Booking" workflow
3. Click "Run workflow"

When manually triggered, the day checker will verify the current day and only proceed if it is Saturday. If it's any other day, the workflow will exit without attempting to book.

## Logs

The workflow logs will show:
- Login attempts
- Court availability
- Booking confirmations
- Any errors that occur during the process

## Court Preferences

The system uses a smart court selection strategy for a single booking:

1. Book 11:00 first.
2. If 11:00 fails, try 12:00.
3. At most one booking will be made on Saturday.

## Troubleshooting

If the workflow fails:
1. Check the workflow logs in the Actions tab
2. Verify that your LTA credentials are correct
3. Ensure the repository has the necessary permissions to run GitHub Actions
4. Check your email settings if you're not receiving notifications

### Common Email Issues:
- Make sure you're using an App Password, not your regular Gmail password
- Verify the email addresses in `NOTIFICATION_EMAILS` are correctly formatted
- Check your spam folder for notifications 