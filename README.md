# Tennis Court Booking Automation

This repository contains an automated system for booking tennis courts at Telford Park Tennis Club. The system uses GitHub Actions to automatically book courts every Thursday and Saturday for two weeks in advance.

## Schedule

The system runs automatically at the following times:

### Thursday Bookings
- User 1: Books a court for 7 PM (two weeks ahead)
- User 2: Books a court for 8 PM (two weeks ahead)

### Saturday Bookings
- User 1: Books a court for 11 AM (two weeks ahead)
- User 2: Books a court for 12 PM (two weeks ahead)

## Setup

### 1. Create a GitHub Repository
1. Go to [github.com](https://github.com) and sign in (or create an account if you don't have one)
2. Click the "+" icon in the top right corner
3. Select "New repository"
4. Name it something like "tennis-court-booker"
5. Make it Private (to keep your credentials secure)
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
2. You should see the "Tennis Court Booking" workflow
3. Click "Enable workflow"

The GitHub Actions workflow will now automatically run at 7:00 AM UTC on Thursdays and Saturdays.

## Email Notifications

After each run (successful or failed), the system will send an email containing:
- The day of booking (Thursday/Saturday)
- Attempted booking times
- Results of each booking attempt
- Link to the detailed GitHub Actions logs

## Manual Trigger

You can also trigger the booking process manually:
1. Go to the "Actions" tab in your repository
2. Select the "Tennis Court Booking" workflow
3. Click "Run workflow"

## Logs

The workflow logs will show:
- Login attempts
- Court availability
- Booking confirmations
- Any errors that occur during the process

## Court Preferences

The system tries to book courts in the following order:
1. Court 5 (preferred)
2. Court 4
3. Court 3

For the second booking (8 PM Thursday/12 PM Saturday), it will attempt to book the same court as the first booking if possible.

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
- Ensure the Gmail account has "Less secure app access" enabled 